"""Cliente da Meta Cloud API (WhatsApp) — envio de mensagens.

Usado pelo webhook do Asaas (aviso de pagamento) e, na Fase 3, pela máquina
de estados do bot.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import logging

import httpx
from django.conf import settings

from bot.mensagens import texto_plano

logger = logging.getLogger(__name__)


class WhatsAppError(Exception):
    pass


def _url() -> str:
    return (
        f"https://graph.facebook.com/{settings.META_API_VERSION}"
        f"/{settings.META_PHONE_NUMBER_ID}/messages"
    )


def _so_digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


async def enviar_texto(telefone: str, texto: str) -> dict:
    """Envia uma mensagem de texto simples para um número (E.164, só dígitos)."""
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        logger.info("[SIMULA WhatsApp] -> %s: %s", telefone, texto.replace("\n", " / "))
        return {"simulado": True}

    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
    headers = {
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(_url(), json=payload, headers=headers)
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


def enviar_texto_sync(telefone: str, texto: str) -> dict:
    """Versão síncrona para views do admin (painel do lojista)."""
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        logger.info("[SIMULA WhatsApp] -> %s: %s", telefone, texto.replace("\n", " / "))
        return {"simulado": True}

    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
    headers = {
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=20) as http:
        resp = http.post(_url(), json=payload, headers=headers)
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


def _headers():
    return {
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _simulacao(telefone: str, msg) -> dict:
    logger.info("[SIMULA WhatsApp] -> %s: %s", telefone, texto_plano(msg).replace("\n", " / "))
    return {"simulado": True}


def _payload_lista(corpo: str, botao: str, linhas: list[dict]) -> dict:
    rows = []
    for row in linhas:
        item = {"id": str(row["id"]), "title": row["titulo"]}
        if row.get("descricao"):
            item["description"] = row["descricao"]
        rows.append(item)
    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": corpo},
            "action": {
                "button": botao,
                "sections": [{"title": "Opções", "rows": rows}],
            },
        },
    }


def _payload_botoes(corpo: str, opcoes: list[dict]) -> dict:
    buttons = [
        {"type": "reply", "reply": {"id": str(op["id"]), "title": op["titulo"]}}
        for op in opcoes[:3]
    ]
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": corpo},
            "action": {"buttons": buttons},
        },
    }


async def enviar_lista(telefone: str, corpo: str, botao: str, linhas: list[dict]) -> dict:
    msg = {"tipo": "lista", "corpo": corpo, "botao": botao, "linhas": linhas}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_lista(corpo, botao, linhas),
    }
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(_url(), json=payload, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar lista WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


async def enviar_botoes(telefone: str, corpo: str, opcoes: list[dict]) -> dict:
    msg = {"tipo": "botoes", "corpo": corpo, "opcoes": opcoes}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_botoes(corpo, opcoes),
    }
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(_url(), json=payload, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar botões WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()



def _payload_flow(corpo: str, flow_id: str, cta: str, payload: dict) -> dict:
    params = {
        "flow_message_version": "3",
        "flow_id": flow_id,
        "flow_cta": cta,
        "flow_action": "navigate",
        "flow_action_payload": payload,
    }
    if payload.get("data", {}).get("flow_token"):
        params["flow_token"] = payload["data"]["flow_token"]
    return {
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {"text": corpo},
            "action": {"name": "flow", "parameters": params},
        },
    }


async def enviar_flow(telefone: str, corpo: str, flow_id: str, cta: str, payload: dict) -> dict:
    msg = {"tipo": "flow", "corpo": corpo, "flow_id": flow_id, "cta": cta, "payload": payload}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    body = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_flow(corpo, flow_id, cta, payload),
    }
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(_url(), json=body, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar Flow WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


def _payload_pix_order(corpo: str, order_parameters: dict, footer: str = "") -> dict:
    interactive = {
        "type": "order_details",
        "body": {"text": corpo[:1024]},
        "action": {"name": "review_and_pay", "parameters": order_parameters},
    }
    if footer:
        interactive["footer"] = {"text": footer[:60]}
    return {"type": "interactive", "interactive": interactive}


async def enviar_pix_order(telefone: str, msg: dict) -> dict:
    params = msg.get("order_parameters") or {}
    if not params:
        return await enviar_texto(telefone, msg.get("pix_copia_cola") or msg.get("corpo", ""))
    footer = "Taxa de entrega paga ao entregador"
    body = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_pix_order(msg.get("corpo", ""), params, footer),
    }
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    async with httpx.AsyncClient(timeout=20) as http:
        resp = await http.post(_url(), json=body, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar Pix nativo: {resp.status_code} {resp.text}")
    return resp.json()

async def enviar_mensagem(telefone: str, msg: dict) -> dict:
    tipo = (msg or {}).get("tipo", "texto")
    if tipo == "texto":
        return await enviar_texto(telefone, msg.get("corpo", ""))
    if tipo == "lista":
        return await enviar_lista(telefone, msg["corpo"], msg["botao"], msg["linhas"])
    if tipo == "botoes":
        return await enviar_botoes(telefone, msg["corpo"], msg["opcoes"])
    if tipo == "flow":
        return await enviar_flow(telefone, msg["corpo"], msg["flow_id"], msg["cta"], msg["payload"])
    if tipo == "multi_select":
        return await enviar_texto(telefone, texto_plano(msg))
    if tipo == "pix_order":
        if msg.get("nativo") and msg.get("order_parameters"):
            return await enviar_pix_order(telefone, msg)
        return await enviar_texto(telefone, msg.get("pix_copia_cola") or msg.get("corpo", ""))
    return await enviar_texto(telefone, texto_plano(msg))


def enviar_lista_sync(telefone: str, corpo: str, botao: str, linhas: list[dict]) -> dict:
    msg = {"tipo": "lista", "corpo": corpo, "botao": botao, "linhas": linhas}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_lista(corpo, botao, linhas),
    }
    with httpx.Client(timeout=20) as http:
        resp = http.post(_url(), json=payload, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar lista WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


def enviar_botoes_sync(telefone: str, corpo: str, opcoes: list[dict]) -> dict:
    msg = {"tipo": "botoes", "corpo": corpo, "opcoes": opcoes}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    payload = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_botoes(corpo, opcoes),
    }
    with httpx.Client(timeout=20) as http:
        resp = http.post(_url(), json=payload, headers=_headers())
    if resp.status_code >= 300:
        raise WhatsAppError(f"Falha ao enviar botões WhatsApp: {resp.status_code} {resp.text}")
    return resp.json()


def enviar_mensagem_sync(telefone: str, msg: dict) -> dict:
    tipo = (msg or {}).get("tipo", "texto")
    if tipo == "texto":
        return enviar_texto_sync(telefone, msg.get("corpo", ""))
    if tipo == "lista":
        return enviar_lista_sync(telefone, msg["corpo"], msg["botao"], msg["linhas"])
    if tipo == "botoes":
        return enviar_botoes_sync(telefone, msg["corpo"], msg["opcoes"])
    if tipo == "pix_order":
        return enviar_texto_sync(telefone, msg.get("pix_copia_cola") or msg.get("corpo", ""))
    if tipo in ("flow", "multi_select"):
        return enviar_texto_sync(telefone, texto_plano(msg))
    return enviar_texto_sync(telefone, texto_plano(msg))
