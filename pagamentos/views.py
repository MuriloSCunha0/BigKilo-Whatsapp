"""Webhook do Asaas: confirma pagamentos e dispara a cozinha + aviso ao cliente."""

import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
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
        return False
    return request.headers.get("asaas-access-token") == esperado


@sync_to_async
def _confirmar_pagamento(cobranca_id: str):
    """Pago = pedido CONCLUÍDO automaticamente (sem etapa manual). Retorna (id, telefone) ou None."""
    with transaction.atomic():
        pedido = (
            Pedido.objects.select_related("cliente")
            .select_for_update()
            .filter(asaas_cobranca_id=cobranca_id)
            .first()
        )
        if not pedido:
            return _confirmar_sinal_natal(cobranca_id)
        # O status nao serve como sinal de pagamento: com "imprimir ao fechar" o
        # pedido ja nasce em PREPARANDO, e a confirmacao nunca disparava.
        if pedido.pago_em is None:
            campos = ["pago_em", "atualizado_em"]
            pedido.pago_em = timezone.now()
            if pedido.status == Pedido.Status.AGUARDANDO_PAGAMENTO:
                pedido.status = Pedido.Status.PREPARANDO
                campos.append("status")
            pedido.save(update_fields=campos)
            telefone = pedido.cliente.telefone
            texto = mensagem("PAGAMENTO_CONFIRMADO", pedido.cliente)
            # Conversa volta ao início e o aviso entra no histórico.
            SessaoBot.objects.filter(telefone=telefone).update(
                estado_atual=SessaoBot.Estado.MENU_PRINCIPAL, carrinho_json={}
            )
            LogMensagem.objects.create(telefone=telefone, direcao=LogMensagem.Direcao.SAIDA, texto=texto)
            return (pedido.pk, telefone, texto)
        return None


def _confirmar_sinal_natal(cobranca_id: str):
    """Sinal da encomenda de Natal e Ano Novo pago: reserva e avisa o cliente.

    Não mexe na sessão do bot nem na impressão: a encomenda não é um pedido do dia.
    """
    from pedidos.models import EncomendaNatal

    enc = (EncomendaNatal.objects.select_for_update()
           .filter(sinal_cobranca_id=cobranca_id).first())
    if not enc or enc.sinal_pago_em:
        return None
    enc.sinal_pago_em = timezone.now()
    enc.valor_pago = (enc.valor_pago or 0) + enc.sinal_valor
    enc.forma_sinal = "PIX"
    if enc.status in (EncomendaNatal.Status.NOVO, EncomendaNatal.Status.AGUARDANDO_SINAL):
        enc.status = EncomendaNatal.Status.RESERVADO
    campos = ["sinal_pago_em", "valor_pago", "forma_sinal", "status", "atualizado_em"]
    if not enc.impressa_em:
        enc.na_fila_impressao = True     # a comanda sai na impressora da loja
        campos.append("na_fila_impressao")
    enc.save(update_fields=campos)
    primeiro = (enc.nome or "").split()[0] if (enc.nome or "").strip() else ""
    quando = enc.data_entrega.strftime("%d/%m") if enc.data_entrega else "a data combinada"
    valor = f"R$ {enc.sinal_valor:.2f}".replace(".", ",")
    texto = (f"Oi{' ' + primeiro if primeiro else ''}! 🎄 Recebemos o sinal de {valor}. "
             f"Sua encomenda nº {enc.pk} está *reservada* para retirada em {quando}"
             + (f" às {enc.horario}" if enc.horario else "") + ". Obrigado! 😊")
    LogMensagem.objects.create(telefone=enc.telefone, direcao=LogMensagem.Direcao.SAIDA, texto=texto)
    return (f"natal-{enc.pk}", enc.telefone, texto)


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
