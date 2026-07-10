"""Views do app pedidos: criação de perfil de fluxo + editor interativo de
mensagens (reutilizado para perfis de fluxo e para personalizar por contato)."""

import json

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .comanda import gerar_comanda_texto
from .models import (
    FLUXO_ETAPAS,
    FLUXO_GRUPOS,
    MENSAGENS_PADRAO,
    PREVIEW_AMOSTRAS,
    VARIAVEIS_DESC,
    VARIAVEIS_MENSAGEM,
    AreaEntrega,
    ChaveMensagem,
    Cliente,
    LogMensagem,
    MensagemCliente,
    MensagemFluxo,
    Pedido,
    PerfilFluxo,
    SessaoBot,
    mensagem,
)

CHAVE_LABEL = dict(ChaveMensagem.choices)


@staff_member_required
@require_POST
def area_salvar(request):
    """Cria uma área de entrega a partir do modal (bairro + faixa de CEP)."""
    dados = json.loads(request.body or b"{}")
    bairro = (dados.get("bairro") or "").strip()
    if not bairro:
        return JsonResponse({"ok": False, "erro": "Informe o bairro."})
    AreaEntrega.objects.create(
        bairro=bairro,
        cep_inicio=(dados.get("cep_inicio") or "").strip(),
        cep_fim=(dados.get("cep_fim") or "").strip(),
        ativo=bool(dados.get("ativo", True)),
    )
    return JsonResponse({"ok": True})


def _variaveis(chave):
    labels = {
        "{bairro}": "Nome do bairro",
        "{lim}": "Quantidade máxima",
        "{data}": "Data da encomenda",
    }
    return [
        {"tok": v, "desc": VARIAVEIS_DESC.get(v, ""), "label": labels.get(v, v)}
        for v in VARIAVEIS_MENSAGEM.get(chave, [])
    ]


def _montar_etapas_editor(perfil_ou_cliente_getter):
    etapas_map = {}
    for chave, quando in FLUXO_ETAPAS:
        etapas_map[chave] = {
            "chave": chave,
            "label": CHAVE_LABEL.get(chave, chave),
            "quando": quando,
            "texto": perfil_ou_cliente_getter(chave),
            "base": MENSAGENS_PADRAO.get(chave, ""),
            "variaveis": _variaveis(chave),
        }
    grupos = []
    vistos = set()
    for gid, titulo, chaves in FLUXO_GRUPOS:
        items = [etapas_map[c] for c in chaves if c in etapas_map]
        vistos.update(c for c in chaves if c in etapas_map)
        if items:
            grupos.append({"id": gid, "titulo": titulo, "etapas": items})
    restantes = [etapas_map[c] for c, _ in FLUXO_ETAPAS if c in etapas_map and c not in vistos]
    if restantes:
        grupos.append({"id": "outros", "titulo": "Outras mensagens", "etapas": restantes})
    return grupos, list(etapas_map.values())


def _valida_variaveis(mensagens):
    """Retorna mensagem de erro se faltar alguma variável obrigatória; senão ''."""
    for chave, obrig in VARIAVEIS_MENSAGEM.items():
        texto = mensagens.get(chave)
        if texto is not None:
            faltando = [v for v in obrig if v not in texto]
            if faltando:
                return f"A mensagem '{CHAVE_LABEL.get(chave)}' precisa conter {', '.join(faltando)}."
    return ""


# ===================== Perfis de fluxo =====================
@staff_member_required
def perfilfluxo_salvar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    dados = json.loads(request.body or b"{}")
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"ok": False, "erro": "Informe o nome do fluxo."})
    perfil = PerfilFluxo.objects.create(nome=nome, ativo=bool(dados.get("ativo")))
    base = PerfilFluxo.objects.filter(ativo=True).exclude(pk=perfil.pk).first()
    for chave, _ in FLUXO_ETAPAS:
        texto = base.texto_de(chave) if base else MENSAGENS_PADRAO.get(chave, "")
        MensagemFluxo.objects.create(perfil=perfil, chave=chave, texto=texto)
    return JsonResponse({"ok": True, "redirect": f"/pedidos/fluxo/{perfil.id}/editar/"})


@staff_member_required
def fluxo_editar(request, perfil_id):
    perfil = get_object_or_404(PerfilFluxo, id=perfil_id)
    grupos, etapas = _montar_etapas_editor(perfil.texto_de)
    ctx = admin.site.each_context(request)
    ctx.update({
        "title": f"Editar fluxo: {perfil.nome}",
        "titulo": f"✏️ {perfil.nome}",
        "subtitulo": "Aqui você muda as *frases* que o cliente lê. O caminho do pedido continua o mesmo.",
        "grupos": grupos,
        "etapas": etapas,
        "preview_amostras_json": json.dumps(PREVIEW_AMOSTRAS, ensure_ascii=False),
        "save_url": f"/pedidos/fluxo/{perfil.id}/editar/salvar/",
        "voltar_url": "/admin/pedidos/perfilfluxo/",
        "testar_url": f"/simulador/?perfil={perfil.id}",
        "mostrar_ativar": True, "ativo": perfil.ativo,
        "base_label": "Texto padrão",
    })
    return render(request, "fluxo_editar.html", ctx)


@staff_member_required
def fluxo_editar_salvar(request, perfil_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    perfil = get_object_or_404(PerfilFluxo, id=perfil_id)
    dados = json.loads(request.body or b"{}")
    mensagens = dados.get("mensagens", {})
    erro = _valida_variaveis(mensagens)
    if erro:
        return JsonResponse({"ok": False, "erro": erro})
    for chave, texto in mensagens.items():
        if chave in CHAVE_LABEL:
            MensagemFluxo.objects.update_or_create(perfil=perfil, chave=chave, defaults={"texto": texto})
    if dados.get("ativar"):
        perfil.ativo = True
        perfil.save()
    return JsonResponse({"ok": True, "redirect": "/admin/pedidos/perfilfluxo/"})


# ===================== Mensagens por contato =====================
@staff_member_required
def contato_mensagens(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    def getter(chave):
        return mensagem(chave, cliente, bairro="{bairro}")

    grupos, etapas = _montar_etapas_editor(getter)
    ctx = admin.site.each_context(request)
    ctx.update({
        "title": f"Mensagens de {cliente.nome_whatsapp or cliente.telefone}",
        "titulo": f"👤 {cliente.nome_whatsapp or cliente.telefone}",
        "subtitulo": "Personalize as mensagens só para este contato. Toque em cada etapa para editar.",
        "grupos": grupos,
        "etapas": etapas,
        "preview_amostras_json": json.dumps(PREVIEW_AMOSTRAS, ensure_ascii=False),
        "save_url": f"/pedidos/contato/{cliente.id}/mensagens/salvar/",
        "voltar_url": f"/admin/pedidos/cliente/{cliente.id}/change/",
        "testar_url": f"/simulador/?tel={cliente.telefone}",
        "mostrar_ativar": False, "ativo": False,
        "base_label": "O que os outros recebem",
    })
    return render(request, "fluxo_editar.html", ctx)


@staff_member_required
def contato_mensagens_salvar(request, cliente_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    cliente = get_object_or_404(Cliente, id=cliente_id)
    dados = json.loads(request.body or b"{}")
    mensagens = dados.get("mensagens", {})
    erro = _valida_variaveis(mensagens)
    if erro:
        return JsonResponse({"ok": False, "erro": erro})
    for chave, texto in mensagens.items():
        if chave not in CHAVE_LABEL:
            continue
        base = mensagem(chave, None, bairro="{bairro}")
        if texto.strip() and texto != base:
            MensagemCliente.objects.update_or_create(cliente=cliente, chave=chave, defaults={"texto": texto})
        else:  # igual ao padrão -> não personaliza
            MensagemCliente.objects.filter(cliente=cliente, chave=chave).delete()
    return JsonResponse({"ok": True, "redirect": f"/admin/pedidos/cliente/{cliente.id}/change/"})


@staff_member_required
def sessao_reiniciar(request, telefone):
    """Reinicia uma conversa do bot (ação no detalhe da sessão)."""
    from django.contrib import messages
    from django.shortcuts import redirect

    sessao = SessaoBot.objects.filter(telefone=telefone).first()
    if sessao:
        sessao.estado_atual = SessaoBot.Estado.MENU_PRINCIPAL
        sessao.carrinho_json = {}
        sessao.save(update_fields=["estado_atual", "carrinho_json"])
        messages.success(request, f"Conversa de {telefone} reiniciada.")
    return redirect("admin:pedidos_sessaobot_change", telefone)


@staff_member_required
@require_POST
def sessao_enviar_mensagem(request, telefone):
    """Envia mensagem manual ao cliente pelo WhatsApp (painel do lojista)."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from bot.whatsapp import WhatsAppError, enviar_texto_sync

    texto = (request.POST.get("texto") or "").strip()
    if not texto:
        messages.error(request, "Digite a mensagem antes de enviar.")
        return redirect("admin:pedidos_sessaobot_change", telefone)

    try:
        enviar_texto_sync(telefone, texto)
        LogMensagem.objects.create(
            telefone=telefone, direcao=LogMensagem.Direcao.SAIDA, texto=f"[Atendente] {texto}",
        )
        if settings.MODO_SIMULACAO:
            messages.warning(
                request,
                "MODO_SIMULACAO ativo: mensagem registrada no histórico, mas não foi enviada ao WhatsApp real.",
            )
        else:
            messages.success(request, "Mensagem enviada ao cliente.")
    except WhatsAppError as exc:
        messages.error(request, f"Não foi possível enviar: {exc}")

    return redirect("admin:pedidos_sessaobot_change", telefone)


# ===================== API de impressão (agente no PC do restaurante) =====================
def _print_token_ok(request):
    esperado = settings.IMPRESSAO_API_TOKEN
    return bool(esperado) and request.headers.get("X-Print-Token") == esperado


@csrf_exempt
def impressao_pendentes(request):
    """Lista pedidos pagos (PREPARANDO) ainda não impressos, com a comanda pronta."""
    if not _print_token_ok(request):
        return JsonResponse({"erro": "token inválido ou ausente"}, status=401)
    pedidos = (
        Pedido.objects.filter(status=Pedido.Status.PREPARANDO, comanda_impressa=False)
        .order_by("criado_em")[:20]
    )
    data = [{"id": p.id, "comanda": gerar_comanda_texto(p)} for p in pedidos]
    return JsonResponse({"pedidos": data})


@csrf_exempt
@require_POST
def impressao_marcar(request):
    """Marca um pedido como impresso (chamado pelo agente após imprimir)."""
    if not _print_token_ok(request):
        return JsonResponse({"erro": "token inválido ou ausente"}, status=401)
    body = json.loads(request.body or b"{}")
    pedido_id = body.get("pedido_id")
    n = Pedido.objects.filter(
        id=pedido_id, status=Pedido.Status.PREPARANDO, comanda_impressa=False,
    ).update(
        comanda_impressa=True,
        impressa_em=timezone.now(),
        status=Pedido.Status.CONCLUIDO,
    )
    return JsonResponse({"ok": bool(n)})
