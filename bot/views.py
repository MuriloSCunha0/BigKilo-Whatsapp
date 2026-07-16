"""Webhook do WhatsApp (Meta Cloud API).

GET  -> validação do webhook (hub.challenge).
POST -> recepção de mensagens, processadas pela máquina de estados.
"""

import json
import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

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
            
        return telefone, texto, nome, tipo, bot_number
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

    # ---- Recepção (POST) ----
    try:
        dados = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json inválido"}, status=400)

    extraido = _extrair_mensagem(dados)
    if not extraido:
        return JsonResponse({"ok": True})  # status/sem mensagem

    telefone, texto, nome, tipo, bot_number = extraido

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


# ===================== Simulador de testes (sem WhatsApp) =====================
@staff_member_required
def simulador(request):
    """Aba do simulador embutida no painel (testar o bot sem o WhatsApp real).

    Com ?perfil=<id>, testa um fluxo específico (preview), sem precisar ativá-lo.
    """
    from pedidos.models import PerfilFluxo

    contexto = admin.site.each_context(request)
    contexto["title"] = "Simulador"
    PerfilFluxo.ensure_perfil_padrao()
    perfil = PerfilFluxo.objects.filter(id=request.GET.get("perfil")).first() if request.GET.get("perfil") else None
    contexto["perfil_preview_id"] = perfil.id if perfil else ""
    contexto["perfil_preview_nome"] = perfil.nome if perfil else ""
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
