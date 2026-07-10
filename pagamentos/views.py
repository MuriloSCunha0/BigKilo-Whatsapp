"""Webhook do Asaas: confirma pagamentos e dispara a cozinha + aviso ao cliente."""

import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bot.whatsapp import enviar_texto
from pedidos.models import LogMensagem, Pedido, SessaoBot, mensagem

logger = logging.getLogger(__name__)

# Eventos do Asaas que indicam pagamento efetivado.
EVENTOS_PAGO = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}


def _token_valido(request) -> bool:
    """Valida o token do webhook se ASAAS_WEBHOOK_TOKEN estiver configurado."""
    esperado = settings.ASAAS_WEBHOOK_TOKEN
    if not esperado:
        return True  # sem token configurado, não valida (apenas dev)
    return request.headers.get("asaas-access-token") == esperado


@sync_to_async
def _confirmar_pagamento(cobranca_id: str):
    """Pago = pedido CONCLUÍDO automaticamente (sem etapa manual). Retorna (id, telefone) ou None."""
    pedido = (
        Pedido.objects.select_related("cliente")
        .filter(asaas_cobranca_id=cobranca_id)
        .first()
    )
    if not pedido:
        return None
    if pedido.status == Pedido.Status.AGUARDANDO_PAGAMENTO:
        pedido.status = Pedido.Status.PREPARANDO
        pedido.save(update_fields=["status", "atualizado_em"])
    telefone = pedido.cliente.telefone
    texto = mensagem("PAGAMENTO_CONFIRMADO", pedido.cliente)
    # Conversa volta ao início e o aviso entra no histórico.
    SessaoBot.objects.filter(telefone=telefone).update(
        estado_atual=SessaoBot.Estado.MENU_PRINCIPAL, carrinho_json={}
    )
    LogMensagem.objects.create(telefone=telefone, direcao=LogMensagem.Direcao.SAIDA, texto=texto)
    return (pedido.pk, telefone, texto)


@csrf_exempt
@require_POST
async def webhook_asaas(request):
    if not _token_valido(request):
        return JsonResponse({"erro": "token inválido"}, status=401)

    try:
        dados = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json inválido"}, status=400)

    evento = dados.get("event")
    pagamento = dados.get("payment") or {}
    cobranca_id = pagamento.get("id")

    if evento not in EVENTOS_PAGO or not cobranca_id:
        # Outros eventos são ignorados (mas confirmados com 200).
        return JsonResponse({"ok": True, "ignorado": evento})

    resultado = await _confirmar_pagamento(cobranca_id)
    if not resultado:
        logger.warning("Webhook Asaas: pedido não encontrado para cobrança %s", cobranca_id)
        return JsonResponse({"ok": True, "pedido": None})

    pedido_id, telefone, texto = resultado
    try:
        await enviar_texto(telefone, texto)
    except Exception as exc:  # não falha o webhook por erro de envio
        logger.error("Falha ao avisar cliente do pedido #%s: %s", pedido_id, exc)

    return JsonResponse({"ok": True, "pedido": pedido_id, "atualizado_em": timezone.now().isoformat()})
