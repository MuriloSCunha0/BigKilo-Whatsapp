"""Integração com a API do Asaas (cobranças Pix).

Fluxo: garante um cliente no Asaas -> cria a cobrança PIX -> obtém o
"copia e cola" (payload do QR Code dinâmico) e grava no Pedido.

Docs: https://docs.asaas.com/reference/criar-nova-cobranca
      https://docs.asaas.com/reference/obter-qr-code-para-pagamentos-via-pix
"""

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone


class AsaasError(Exception):
    pass


def _headers():
    if not settings.ASAAS_API_KEY:
        raise AsaasError("ASAAS_API_KEY não configurada.")
    return {
        "access_token": settings.ASAAS_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "BigKilo/1.0",
    }


def _so_digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


async def _obter_ou_criar_cliente(http: httpx.AsyncClient, cliente) -> str:
    """Retorna o id do cliente no Asaas, criando-o se necessário."""
    if cliente.asaas_cliente_id:
        return cliente.asaas_cliente_id

    payload = {
        "name": cliente.nome_whatsapp or f"Cliente {cliente.telefone}",
        "mobilePhone": _so_digitos(cliente.telefone),
    }
    cpf = _so_digitos(settings.ASAAS_DEFAULT_CPF_CNPJ)
    if cpf:
        payload["cpfCnpj"] = cpf

    resp = await http.post(f"{settings.ASAAS_BASE_URL}/customers", json=payload, headers=_headers())
    if resp.status_code >= 300:
        raise AsaasError(f"Falha ao criar cliente Asaas: {resp.status_code} {resp.text}")
    asaas_id = resp.json()["id"]

    cliente.asaas_cliente_id = asaas_id
    await sync_to_async(cliente.save)(update_fields=["asaas_cliente_id"])
    return asaas_id


def _pix_simulado(pedido) -> str:
    """Gera um 'copia e cola' fake (apenas para testes, NÃO é pagável)."""
    valor = f"{pedido.valor_total:.2f}"
    return (
        "00020126SIMULADO-BIG-KILO5204000053039865802BR"
        f"5913BIG KILO TESTE6009SAO PAULO62070503***"
        f"54{len(valor):02d}{valor}6304SIM{pedido.pk:04d}"
    )


async def criar_cobranca_pix(pedido) -> dict:
    """Cria a cobrança PIX para o pedido e grava id + copia e cola.

    Retorna um dict com {cobranca_id, pix_copia_cola, qr_base64}.
    Em MODO_SIMULACAO (ou sem ASAAS_API_KEY), gera um Pix fake para testes.
    """
    valor = float(pedido.valor_total)
    if valor <= 0:
        raise AsaasError("Pedido sem valor para cobrança.")

    if settings.MODO_SIMULACAO or not settings.ASAAS_API_KEY:
        cobranca_id = f"pay_sim_{pedido.pk}"
        copia_cola = _pix_simulado(pedido)
        pedido.asaas_cobranca_id = cobranca_id
        pedido.asaas_pix_copia_cola = copia_cola
        await sync_to_async(pedido.save)(update_fields=["asaas_cobranca_id", "asaas_pix_copia_cola"])
        return {"cobranca_id": cobranca_id, "pix_copia_cola": copia_cola, "qr_base64": "", "simulado": True}

    cliente = await sync_to_async(lambda: pedido.cliente)()

    async with httpx.AsyncClient(timeout=20) as http:
        customer_id = await _obter_ou_criar_cliente(http, cliente)

        cobranca = {
            "customer": customer_id,
            "billingType": "PIX",
            "value": valor,
            "dueDate": timezone.localdate().isoformat(),
            "description": f"Pedido #{pedido.pk} - Big Kilo",
            "externalReference": str(pedido.pk),
        }
        resp = await http.post(f"{settings.ASAAS_BASE_URL}/payments", json=cobranca, headers=_headers())
        if resp.status_code >= 300:
            raise AsaasError(f"Falha ao criar cobrança: {resp.status_code} {resp.text}")
        cobranca_id = resp.json()["id"]

        # Obter o copia e cola (payload do QR Code dinâmico)
        qr = await http.get(
            f"{settings.ASAAS_BASE_URL}/payments/{cobranca_id}/pixQrCode", headers=_headers()
        )
        if qr.status_code >= 300:
            raise AsaasError(f"Falha ao obter QR Code: {qr.status_code} {qr.text}")
        dados = qr.json()
        copia_cola = dados.get("payload", "")

    pedido.asaas_cobranca_id = cobranca_id
    pedido.asaas_pix_copia_cola = copia_cola
    await sync_to_async(pedido.save)(update_fields=["asaas_cobranca_id", "asaas_pix_copia_cola"])

    return {
        "cobranca_id": cobranca_id,
        "pix_copia_cola": copia_cola,
        "qr_base64": dados.get("encodedImage", ""),
    }
