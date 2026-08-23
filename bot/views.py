"""Webhook do WhatsApp (Meta Cloud API).

GET  -> validação do webhook (hub.challenge).
POST -> recepção de mensagens, processadas pela máquina de estados.
"""

import json
import logging
from pathlib import Path
import hmac
import hashlib
import os

import httpx
from django.core.cache import cache
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .fluxo import processar_mensagem
from .whatsapp import enviar_mensagem, enviar_texto

logger = logging.getLogger(__name__)


def _extrair_mensagem(dados: dict):
    """Extrai (telefone, texto, nome, tipo) da primeira mensagem do payload, se houver."""
    try:
        value = dados["entry"][0]["changes"][0]["value"]
        mensagens = value.get("messages")
        if not mensagens:
            return None  # provavelmente um status (entregue/lido)
        msg = mensagens[0]
        telefone = msg["from"]
        tipo = msg.get("type", "")
        msg_id = msg.get("id", "")
        texto = ""
        if tipo == "text":
            texto = msg.get("text", {}).get("body", "")
        elif tipo == "interactive":
            inter = msg.get("interactive") or {}
            if inter.get("type") == "list_reply":
                texto = (inter.get("list_reply") or {}).get("id", "")
            elif inter.get("type") == "button_reply":
                texto = (inter.get("button_reply") or {}).get("id", "")
            elif inter.get("type") == "nfm_reply":
                from bot.flows import parse_nfm_reply
                ids = parse_nfm_reply((inter.get("nfm_reply") or {}).get("response_json", ""))
                texto = "multi:" + ",".join(ids) if ids else ""
        nome = ""
        contatos = value.get("contacts") or []
        if contatos:
            nome = contatos[0].get("profile", {}).get("name", "")
            
        bot_number = value.get("metadata", {}).get("display_phone_number", "")
        if bot_number:
            # limpa o número (remove +, -, espaços)
            bot_number = "".join(filter(str.isdigit, bot_number))
            
        return telefone, texto, nome, tipo, bot_number, msg_id
    except (KeyError, IndexError, TypeError):
        return None


@csrf_exempt
async def webhook_whatsapp(request):
    # ---- Validação (GET) ----
    if request.method == "GET":
        modo = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if modo == "subscribe" and token == settings.META_VERIFY_TOKEN:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("Token de verificação inválido.")

    if request.method != "POST":
        return HttpResponse(status=405)

    app_secret = os.getenv("META_APP_SECRET", "")
    if app_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if signature.startswith("sha256="):
            signature = signature[7:]
        expected = hmac.new(app_secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return HttpResponseForbidden("Assinatura invalida")

    # ---- Recepção (POST) ----
    try:
        dados = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json inválido"}, status=400)

    extraido = _extrair_mensagem(dados)
    if not extraido:
        return JsonResponse({"ok": True})  # status/sem mensagem

    telefone, texto, nome, tipo, bot_number, msg_id = extraido

    if msg_id:
        cache_key = f"wa_msg_{msg_id}"
        if cache.get(cache_key):
            return JsonResponse({"ok": True, "duplicada": True})
        cache.set(cache_key, True, 3600)  # Deduplica por 1 hora

    if bot_number:
        from clientes.models import Cliente
        from django.db import connection
        
        # Como estamos no async handler, precisamos rodar queries síncronas usando sync_to_async
        # Mas connection.set_tenant não é thread safe se misturado no async.
        # Felizmente o bot inteiro processa chamadas de banco no sync_to_async ou threads.
        # Vamos usar sync_to_async para buscar o tenant e setá-lo na connection local
        @sync_to_async
        def set_tenant_from_number(number):
            tenant = Cliente.objects.filter(telefone_whatsapp=number).first()
            if tenant:
                connection.set_tenant(tenant)
                return True
            return False

        has_tenant = await set_tenant_from_number(bot_number)
        if not has_tenant:
            logger.error("Nenhum inquilino encontrado para o número do bot: %s", bot_number)
            return JsonResponse({"ok": True})

    if tipo not in ("text", "interactive"):
        try:
            await enviar_texto(
                telefone,
                "Por enquanto eu só consigo ler *texto* ou *opções do menu*. "
                "Pode digitar ou usar os botões, por favor? 🙂",
            )
        except Exception as exc:
            logger.error("Falha ao responder mídia de %s: %s", telefone, exc)
        return JsonResponse({"ok": True})

    if not (texto or "").strip():
        return JsonResponse({"ok": True})

    try:
        respostas = await processar_mensagem(telefone, texto, nome)
        for msg in respostas:
            await enviar_mensagem(telefone, msg)
    except Exception as exc:
        logger.exception("Erro ao processar mensagem de %s: %s", telefone, exc)
        # Não propaga erro para a Meta (evita reenvios em loop).

    return JsonResponse({"ok": True})


# ===================== Webhook Evolution API (WhatsApp não-oficial) =====================
def _extrair_evolution(dados: dict):
    """Extrai (telefone, texto, nome) de um evento MESSAGES_UPSERT da Evolution."""
    try:
        evento = (dados.get("event") or "").replace(".", "_").lower()
        if evento != "messages_upsert":
            return None
        data = dados.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        key = data.get("key") or {}
        if key.get("fromMe"):
            return None  # mensagem enviada por nós
        jid = key.get("remoteJid") or ""
        if not jid or jid.endswith("@g.us") or "status@broadcast" in jid:
            return None  # grupo / status: ignora
        telefone = jid.split("@")[0].split(":")[0]
        msg = data.get("message") or {}
        texto = (
            msg.get("conversation")
            or (msg.get("extendedTextMessage") or {}).get("text")
            or (msg.get("buttonsResponseMessage") or {}).get("selectedButtonId")
            or ((msg.get("listResponseMessage") or {}).get("singleSelectReply") or {}).get("selectedRowId")
            or ""
        )
        nome = data.get("pushName") or ""
        return telefone, texto, nome
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


@csrf_exempt
async def webhook_evolution(request):
    """Recebe as mensagens da Evolution API e responde pela máquina de estados."""
    if request.method != "POST":
        return HttpResponse(status=405)

    if settings.EVOLUTION_WEBHOOK_TOKEN:
        enviado = request.headers.get("apikey") or request.GET.get("token")
        if enviado != settings.EVOLUTION_WEBHOOK_TOKEN:
            return HttpResponseForbidden("token inválido")

    try:
        dados = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json inválido"}, status=400)

    extraido = _extrair_evolution(dados)
    if not extraido:
        return JsonResponse({"ok": True})  # evento sem mensagem de texto útil

    telefone, texto, nome = extraido
    if not (texto or "").strip():
        return JsonResponse({"ok": True})

    try:
        respostas = await processar_mensagem(telefone, texto, nome)
        for msg in respostas:
            await enviar_mensagem(telefone, msg)
    except Exception as exc:
        logger.exception("Erro ao processar mensagem (Evolution) de %s: %s", telefone, exc)

    return JsonResponse({"ok": True})


# ===================== Conexão do WhatsApp (Evolution) — aba no painel =========
def _evo_cfg():
    return (
        (settings.EVOLUTION_API_URL or "").rstrip("/"),
        settings.EVOLUTION_API_KEY or "",
        settings.EVOLUTION_INSTANCE or "bigkilo",
    )


def _evo_configurada() -> bool:
    base, key, _ = _evo_cfg()
    return bool(base and key and getattr(settings, "WHATSAPP_PROVIDER", "meta") == "evolution")


@staff_member_required
def whatsapp_conexao(request):
    """Página (aba do painel) para conectar/monitorar o WhatsApp via Evolution."""
    contexto = admin.site.each_context(request)
    contexto["title"] = "Conexão do WhatsApp"
    contexto["evo_configurada"] = _evo_configurada()
    return render(request, "whatsapp_conexao.html", contexto)


@staff_member_required
def whatsapp_status(request):
    """Estado da conexão (open/connecting/close) + número/nome quando conectado."""
    base, key, inst = _evo_cfg()
    if not (base and key):
        return JsonResponse({"ok": False, "erro": "Evolution não configurada."})
    try:
        with httpx.Client(timeout=15) as http:
            resp = http.get(f"{base}/instance/fetchInstances", headers={"apikey": key})
        dados = resp.json() if resp.status_code < 300 else []
        if isinstance(dados, dict):
            dados = dados.get("instances") or [dados]
        alvo = next((x for x in dados if (x.get("name") or x.get("instanceName")) == inst), None)
        if not alvo:
            return JsonResponse({"ok": True, "state": "close"})
        jid = alvo.get("ownerJid") or ""
        return JsonResponse({
            "ok": True,
            "state": alvo.get("connectionStatus") or alvo.get("state") or "close",
            "numero": jid.split("@")[0] if jid else "",
            "nome": alvo.get("profileName") or "",
        })
    except Exception as exc:
        return JsonResponse({"ok": False, "erro": str(exc)})


@staff_member_required
def whatsapp_qr(request):
    """Gera/atualiza o QR code para escanear (base64 da imagem)."""
    base, key, inst = _evo_cfg()
    if not (base and key):
        return JsonResponse({"ok": False, "erro": "Evolution não configurada."})
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.get(f"{base}/instance/connect/{inst}", headers={"apikey": key})
        dados = resp.json() if resp.status_code < 300 else {}
        b64 = dados.get("base64") or (dados.get("qrcode") or {}).get("base64") or ""
        return JsonResponse({"ok": True, "base64": b64, "connected": not b64})
    except Exception as exc:
        return JsonResponse({"ok": False, "erro": str(exc)})


@staff_member_required
@require_POST
def whatsapp_logout(request):
    """Desconecta o WhatsApp (logout da instância)."""
    base, key, inst = _evo_cfg()
    if not (base and key):
        return JsonResponse({"ok": False, "erro": "Evolution não configurada."})
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.request("DELETE", f"{base}/instance/logout/{inst}", headers={"apikey": key})
        return JsonResponse({"ok": resp.status_code < 300})
    except Exception as exc:
        return JsonResponse({"ok": False, "erro": str(exc)})


# ===================== Atendimento humano (inbox estilo WhatsApp) =============
_AVISO_ATENDENTE = (
    "👋 Um atendente do Big Kilo assumiu a conversa e vai te ajudar por aqui. Pode falar!"
)
_AVISO_ENCERRADO = (
    "✅ Atendimento encerrado. Se precisar de algo, é só mandar uma mensagem que te atendo de novo. 🙂"
)


@staff_member_required
def atendimento_inbox(request):
    """Aba 'Atendimento' — lista as conversas (estilo WhatsApp) e permite o
    atendente humano assumir e responder o cliente."""
    contexto = admin.site.each_context(request)
    contexto["title"] = "Atendimento"
    return render(request, "atendimento_inbox.html", contexto)


@staff_member_required
def atendimento_conversas(request):
    """JSON com a lista de conversas (última mensagem, nome, se está em atendimento)."""
    from pedidos.models import Cliente, LogMensagem, SessaoBot

    ultimas = list(LogMensagem.objects.order_by("telefone", "-criado_em").distinct("telefone"))
    ultimas.sort(key=lambda m: m.criado_em, reverse=True)
    ultimas = ultimas[:100]
    tels = [m.telefone for m in ultimas]
    nomes = {c.telefone: c.nome_whatsapp for c in Cliente.objects.filter(telefone__in=tels)}
    estados = {s.telefone: s.estado_atual for s in SessaoBot.objects.filter(telefone__in=tels)}

    conversas = []
    for m in ultimas:
        prefixo = "" if m.direcao == LogMensagem.Direcao.ENTRADA else "Você: "
        conversas.append({
            "telefone": m.telefone,
            "nome": nomes.get(m.telefone) or m.telefone,
            "ultima": (prefixo + (m.texto or "").replace("\n", " "))[:70],
            "quando": timezone.localtime(m.criado_em).strftime("%d/%m %H:%M"),
            "em_atendimento": estados.get(m.telefone) == SessaoBot.Estado.ATENDIMENTO_HUMANO,
        })
    return JsonResponse({"ok": True, "conversas": conversas})


@staff_member_required
def atendimento_mensagens(request):
    """JSON com o histórico de uma conversa (para o painel de chat)."""
    from pedidos.models import Cliente, LogMensagem, SessaoBot

    tel = (request.GET.get("telefone") or "").strip()
    if not tel:
        return JsonResponse({"ok": False, "erro": "Telefone ausente."})
    msgs = LogMensagem.objects.filter(telefone=tel).order_by("criado_em")[:400]
    sess = SessaoBot.objects.filter(telefone=tel).first()
    cli = Cliente.objects.filter(telefone=tel).first()
    return JsonResponse({
        "ok": True,
        "nome": (cli.nome_whatsapp if cli and cli.nome_whatsapp else tel),
        "em_atendimento": bool(sess and sess.estado_atual == SessaoBot.Estado.ATENDIMENTO_HUMANO),
        "mensagens": [{
            "de": ("nos" if m.direcao == LogMensagem.Direcao.SAIDA else "cliente"),
            "texto": m.texto,
            "quando": timezone.localtime(m.criado_em).strftime("%d/%m %H:%M"),
        } for m in msgs],
    })


def _num_do_body(request):
    try:
        return (json.loads(request.body or b"{}").get("telefone") or "").strip()
    except (ValueError, TypeError):
        return ""


@staff_member_required
@require_POST
def atendimento_abrir(request):
    """Pausa o bot e coloca a conversa em atendimento humano; avisa o cliente."""
    from pedidos.models import LogMensagem, SessaoBot
    from .whatsapp import enviar_texto_sync

    tel = _num_do_body(request)
    if not tel:
        return JsonResponse({"ok": False, "erro": "Telefone ausente."})
    sess, _ = SessaoBot.objects.get_or_create(telefone=tel)
    sess.estado_atual = SessaoBot.Estado.ATENDIMENTO_HUMANO
    sess.save()
    try:
        enviar_texto_sync(tel, _AVISO_ATENDENTE)
    except Exception:
        logger.exception("Falha ao avisar cliente do atendimento humano")
    LogMensagem.objects.create(telefone=tel, direcao=LogMensagem.Direcao.SAIDA, texto=_AVISO_ATENDENTE)
    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
def atendimento_encerrar(request):
    """Devolve a conversa ao bot (próxima mensagem do cliente reinicia o atendimento automático)."""
    from pedidos.models import LogMensagem, SessaoBot
    from .whatsapp import enviar_texto_sync

    tel = _num_do_body(request)
    if not tel:
        return JsonResponse({"ok": False, "erro": "Telefone ausente."})
    sess = SessaoBot.objects.filter(telefone=tel).first()
    if sess:
        sess.estado_atual = SessaoBot.Estado.MENU_PRINCIPAL
        sess.carrinho_json = {}
        sess.save()
    try:
        enviar_texto_sync(tel, _AVISO_ENCERRADO)
    except Exception:
        logger.exception("Falha ao avisar cliente do encerramento")
    LogMensagem.objects.create(telefone=tel, direcao=LogMensagem.Direcao.SAIDA, texto=_AVISO_ENCERRADO)
    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
def atendimento_enviar(request):
    """Envia uma mensagem do atendente para o cliente (garante o modo atendimento humano)."""
    from pedidos.models import LogMensagem, SessaoBot
    from .whatsapp import enviar_texto_sync

    try:
        dados = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        dados = {}
    tel = (dados.get("telefone") or "").strip()
    texto = (dados.get("texto") or "").strip()
    if not tel or not texto:
        return JsonResponse({"ok": False, "erro": "Telefone e mensagem são obrigatórios."})
    sess, _ = SessaoBot.objects.get_or_create(telefone=tel)
    if sess.estado_atual != SessaoBot.Estado.ATENDIMENTO_HUMANO:
        sess.estado_atual = SessaoBot.Estado.ATENDIMENTO_HUMANO
        sess.save()
    try:
        enviar_texto_sync(tel, texto)
    except Exception as exc:
        logger.exception("Falha ao enviar mensagem do atendente")
        return JsonResponse({"ok": False, "erro": f"Falha ao enviar: {exc}"})
    LogMensagem.objects.create(telefone=tel, direcao=LogMensagem.Direcao.SAIDA, texto=texto)
    return JsonResponse({"ok": True, "quando": timezone.localtime().strftime("%d/%m %H:%M")})


# ===================== Impressão automática (download do programa) ============
_PRINT_EXE = Path(settings.BASE_DIR) / "download" / "BigKiloImpressora.exe"


def impressao_pagina(request):
    """Página pública (instalação única, sem login) para baixar o programa de impressão."""
    return render(request, "impressao.html", {"programa_disponivel": _PRINT_EXE.exists()})


def impressao_baixar(request):
    """Entrega o .exe do agente de impressão (Windows). Público — instalação única."""
    if not _PRINT_EXE.exists():
        raise Http404("Programa de impressão não encontrado.")
    return FileResponse(open(_PRINT_EXE, "rb"), as_attachment=True, filename="BigKiloImpressora.exe")


# ===================== Simulador de testes (sem WhatsApp) =====================
@staff_member_required
def simulador(request):
    """Aba do simulador embutida no painel (testar o bot sem o WhatsApp real).

    Permite selecionar qualquer fluxo cadastrado para testes em tempo real.
    """
    from pedidos.models import PerfilFluxo

    contexto = admin.site.each_context(request)
    contexto["title"] = "Simulador"
    PerfilFluxo.ensure_perfil_padrao()
    perfis = list(PerfilFluxo.objects.all())
    contexto["perfis"] = perfis
    
    perfil_req = PerfilFluxo.objects.filter(id=request.GET.get("perfil")).first() if request.GET.get("perfil") else None
    perfil_ativo = PerfilFluxo.ativo_atual()
    perfil_sel = perfil_req or perfil_ativo or (perfis[0] if perfis else None)

    contexto["perfil_preview_id"] = perfil_sel.id if perfil_sel else ""
    contexto["perfil_preview_nome"] = perfil_sel.nome if perfil_sel else ""
    contexto["sim_tel"] = request.GET.get("tel") or "5521999990000"
    return render(request, "simulador_embed.html", contexto)


@csrf_exempt
async def simulador_msg(request):
    """Recebe uma mensagem do simulador e devolve as respostas do bot."""
    dados = json.loads(request.body or b"{}")
    telefone = (dados.get("telefone") or "5521999990000").strip()
    texto = dados.get("texto", "")
    nome = dados.get("nome", "Cliente Teste")
    perfil_id = dados.get("perfil_id") or None
    respostas = await processar_mensagem(telefone, texto, nome, perfil_id=perfil_id, registrar=False)
    return JsonResponse({"mensagens": respostas})


@csrf_exempt
async def simulador_reset(request):
    """Reinicia a sessão do telefone (sem poluir o histórico) e devolve a saudação limpa."""
    from pedidos.models import SessaoBot

    dados = json.loads(request.body or b"{}")
    telefone = (dados.get("telefone") or "5521999990000").strip()
    perfil_id = dados.get("perfil_id") or None

    @sync_to_async
    def _zerar():
        SessaoBot.objects.update_or_create(
            telefone=telefone,
            defaults={"estado_atual": SessaoBot.Estado.MENU_PRINCIPAL, "carrinho_json": {}},
        )

    await _zerar()
    respostas = await processar_mensagem(telefone, "oi", "Cliente Teste", perfil_id=perfil_id, registrar=False)
    return JsonResponse({"mensagens": respostas})


@csrf_exempt
def simulador_pagar(request):
    """Simula a confirmação do Pix: marca o pedido como PREPARANDO e imprime a comanda."""
    from pedidos.comanda import gerar_comanda_texto
    from pedidos.models import Pedido, PerfilFluxo, SessaoBot, mensagem

    dados = json.loads(request.body or b"{}")
    telefone = (dados.get("telefone") or "").strip()
    pedido = (
        Pedido.objects.filter(cliente__telefone=telefone, status=Pedido.Status.AGUARDANDO_PAGAMENTO)
        .order_by("-criado_em")
        .first()
    )
    if not pedido:
        return JsonResponse({"ok": False, "erro": "Nenhum pedido aguardando pagamento."})

    pedido.status = Pedido.Status.PREPARANDO
    pedido.save(update_fields=["status", "atualizado_em"])

    # Simula a impressão automática da comanda (modo arquivo).
    try:
        destino = Path(settings.BASE_DIR) / "comandas"
        destino.mkdir(exist_ok=True)
        (destino / f"pedido_{pedido.pk}.txt").write_text(gerar_comanda_texto(pedido), encoding="utf-8")
        pedido.comanda_impressa = True
        pedido.impressa_em = timezone.now()
        pedido.status = Pedido.Status.CONCLUIDO
        pedido.save(update_fields=["comanda_impressa", "impressa_em", "status"])
    except Exception as exc:
        logger.error("Falha ao imprimir comanda do pedido #%s: %s", pedido.pk, exc)

    perfil = PerfilFluxo.objects.filter(id=dados.get("perfil_id")).first() if dados.get("perfil_id") else None
    confirmacao = mensagem("PAGAMENTO_CONFIRMADO", pedido.cliente, perfil=perfil)

    # Pago: a conversa volta ao início (não fica presa em "aguardando pagamento")
    # e registramos o aviso no histórico para o lojista acompanhar.
    SessaoBot.objects.filter(telefone=telefone).update(
        estado_atual=SessaoBot.Estado.MENU_PRINCIPAL, carrinho_json={}
    )
    return JsonResponse({"ok": True, "pedido": pedido.pk, "mensagem": confirmacao})
