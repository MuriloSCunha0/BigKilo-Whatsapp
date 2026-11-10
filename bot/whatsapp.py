"""Cliente da Meta Cloud API (WhatsApp) — envio de mensagens.

Usado pelo webhook do Asaas (aviso de pagamento) e, na Fase 3, pela máquina
de estados do bot.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import logging

import httpx
from django.conf import settings

from bot.mensagens import multi_para_lista, texto_numerado, texto_plano

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


# ===================== Provedor (Meta oficial x Evolution não-oficial) =====================
def _provider() -> str:
    """'evolution' se configurado; senão 'meta'."""
    if (getattr(settings, "WHATSAPP_PROVIDER", "meta") == "evolution"
            and settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY):
        return "evolution"
    return "meta"


def _evolution_url() -> str:
    return f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE}"


def _evolution_headers() -> dict:
    return {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}


async def _evolution_enviar(telefone: str, texto: str) -> dict:
    payload = {"number": _so_digitos(telefone), "text": texto}
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_evolution_url(), json=payload, headers=_evolution_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar (Evolution): {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede (Evolution): {exc}")
    return resp.json()


def _evolution_enviar_sync(telefone: str, texto: str) -> dict:
    payload = {"number": _so_digitos(telefone), "text": texto}
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.post(_evolution_url(), json=payload, headers=_evolution_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar (Evolution): {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede (Evolution): {exc}")
    return resp.json()


async def enviar_texto(telefone: str, texto: str) -> dict:
    """Envia uma mensagem de texto simples para um número (E.164, só dígitos)."""
    # Evolution envia sempre que configurado (independe de MODO_SIMULACAO, que passa
    # a controlar só o Asaas). Assim dá pra ter WhatsApp real + Pix simulado.
    if _provider() == "evolution":
        return await _evolution_enviar(telefone, texto)
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
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_url(), json=payload, headers=headers)
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede: {exc}")
    return resp.json()


def enviar_texto_sync(telefone: str, texto: str) -> dict:
    """Versão síncrona para views do admin (painel do lojista)."""
    if _provider() == "evolution":
        return _evolution_enviar_sync(telefone, texto)
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
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.post(_url(), json=payload, headers=headers)
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede: {exc}")
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
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_url(), json=payload, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar lista WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
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
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_url(), json=payload, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar botões WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
    return resp.json()



def _payload_flow(corpo: str, flow_id: str, cta: str, payload: dict, token: str = "") -> dict:
    params = {
        "flow_message_version": "3",
        "flow_id": flow_id,
        "flow_cta": cta,
        "flow_action": "navigate",
        "flow_action_payload": payload,
    }
    if token:
        params["flow_token"] = token
    return {
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {"text": corpo},
            "action": {"name": "flow", "parameters": params},
        },
    }


async def enviar_flow(telefone: str, corpo: str, flow_id: str, cta: str, payload: dict, token: str = "") -> dict:
    msg = {"tipo": "flow", "corpo": corpo, "flow_id": flow_id, "cta": cta, "payload": payload}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    body = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_flow(corpo, flow_id, cta, payload, token),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_url(), json=body, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar Flow WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
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
    footer = "Taxa de entrega incluida no total"
    body = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_pix_order(msg.get("corpo", ""), params, footer),
    }
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(_url(), json=body, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar Pix nativo: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
    return resp.json()

async def enviar_mensagem(telefone: str, msg: dict) -> dict:
    if (msg or {}).get("tipo") == "imagem":
        from asgiref.sync import sync_to_async
        return await sync_to_async(enviar_foto_sync)(telefone, msg)
    # Evolution/texto puro: converte listas/botões em menu numerado e envia como texto.
    if _provider() == "evolution":
        return await enviar_texto(telefone, texto_numerado(msg))
    tipo = (msg or {}).get("tipo", "texto")
    if tipo == "texto":
        return await enviar_texto(telefone, msg.get("corpo", ""))
    if tipo == "lista":
        return await enviar_lista(telefone, msg["corpo"], msg["botao"], msg["linhas"])
    if tipo == "botoes":
        return await enviar_botoes(telefone, msg["corpo"], msg["opcoes"])
    if tipo == "flow":
        return await enviar_flow(
            telefone, msg["corpo"], msg["flow_id"], msg["cta"], msg["payload"], msg.get("token", "")
        )
    if tipo == "multi_select":
        # A Cloud API só tem multi-select dentro de Flow. Sem Flow publicado, a lista
        # nativa é o caminho tocável: multi_para_lista pagina para caber em 10 linhas,
        # então o cliente escolhe tudo no toque, sem digitar nada.
        lst = multi_para_lista(msg)
        return await enviar_lista(telefone, lst["corpo"], lst["botao"], lst["linhas"])
    if tipo == "pix_order":
        if msg.get("nativo") and msg.get("order_parameters"):
            return await enviar_pix_order(telefone, msg)
        corpo = msg.get("corpo", "")
        pix = msg.get("pix_copia_cola", "")
        if corpo:
            await enviar_texto(telefone, corpo)
        if pix:
            return await enviar_texto(telefone, pix)
        return {"ok": True}
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
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.post(_url(), json=payload, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar lista WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
    return resp.json()


def enviar_flow_sync(telefone: str, corpo: str, flow_id: str, cta: str, payload: dict, token: str = "") -> dict:
    msg = {"tipo": "flow", "corpo": corpo, "flow_id": flow_id, "cta": cta, "payload": payload}
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        return _simulacao(telefone, msg)
    body = {
        "messaging_product": "whatsapp",
        "to": _so_digitos(telefone),
        **_payload_flow(corpo, flow_id, cta, payload, token),
    }
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.post(_url(), json=body, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar Flow WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
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
    try:
        with httpx.Client(timeout=20) as http:
            resp = http.post(_url(), json=payload, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar botões WhatsApp: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f'Falha de rede: {exc}')
    return resp.json()


def enviar_mensagem_sync(telefone: str, msg: dict) -> dict:
    if (msg or {}).get("tipo") == "imagem":
        return enviar_foto_sync(telefone, msg)
    if _provider() == "evolution":
        return enviar_texto_sync(telefone, texto_numerado(msg))
    tipo = (msg or {}).get("tipo", "texto")
    if tipo == "texto":
        return enviar_texto_sync(telefone, msg.get("corpo", ""))
    if tipo == "lista":
        return enviar_lista_sync(telefone, msg["corpo"], msg["botao"], msg["linhas"])
    if tipo == "botoes":
        return enviar_botoes_sync(telefone, msg["corpo"], msg["opcoes"])
    if tipo == "pix_order":
        corpo = msg.get("corpo", "")
        pix = msg.get("pix_copia_cola", "")
        if corpo:
            enviar_texto_sync(telefone, corpo)
        if pix:
            return enviar_texto_sync(telefone, pix)
        return {"ok": True}
    if tipo == "multi_select":
        lst = multi_para_lista(msg)
        return enviar_lista_sync(telefone, lst["corpo"], lst["botao"], lst["linhas"])
    if tipo == "flow":
        return enviar_flow_sync(
            telefone, msg["corpo"], msg["flow_id"], msg["cta"], msg["payload"], msg.get("token", "")
        )
    return enviar_texto_sync(telefone, texto_plano(msg))


# ===================== Fotos (cardápio, Ceia de Natal) =====================
def _url_midia() -> str:
    return (f"https://graph.facebook.com/{settings.META_API_VERSION}"
            f"/{settings.META_PHONE_NUMBER_ID}/media")


def _subir_midia_sync(conteudo: bytes, tipo: str) -> str:
    """Sobe a foto para a Meta e devolve o id (vale 30 dias)."""
    try:
        with httpx.Client(timeout=60) as http:
            resp = http.post(
                _url_midia(),
                headers={"Authorization": f"Bearer {settings.META_ACCESS_TOKEN}"},
                data={"messaging_product": "whatsapp", "type": tipo},
                files={"file": ("cardapio.jpg", conteudo, tipo)},
            )
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao subir foto: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede ao subir foto: {exc}")
    return resp.json()["id"]


def _postar_imagem_meta(telefone: str, media_id: str, legenda: str):
    imagem = {"id": media_id}
    if legenda:
        imagem["caption"] = legenda[:1000]
    payload = {"messaging_product": "whatsapp", "to": _so_digitos(telefone),
               "type": "image", "image": imagem}
    try:
        with httpx.Client(timeout=30) as http:
            resp = http.post(_url(), json=payload, headers=_headers())
        if resp.status_code >= 300:
            raise WhatsAppError(f"Falha ao enviar foto: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        raise WhatsAppError(f"Falha de rede ao enviar foto: {exc}")
    return resp.json()


def enviar_imagem_sync(telefone: str, conteudo: bytes, tipo: str = "image/jpeg",
                       legenda: str = "", media_id: str = "") -> str:
    """Envia uma foto. Devolve o id de mídia usado na Meta ("" fora dela), para reaproveitar."""
    if _provider() == "evolution":
        import base64
        payload = {"number": _so_digitos(telefone), "mediatype": "image", "mimetype": tipo,
                   "caption": legenda or "", "fileName": "cardapio.jpg",
                   "media": base64.b64encode(conteudo).decode()}
        url = f"{settings.EVOLUTION_API_URL}/message/sendMedia/{settings.EVOLUTION_INSTANCE}"
        try:
            with httpx.Client(timeout=60) as http:
                resp = http.post(url, json=payload, headers=_evolution_headers())
            if resp.status_code >= 300:
                raise WhatsAppError(f"Falha ao enviar foto (Evolution): {resp.status_code} {resp.text}")
        except httpx.RequestError as exc:
            raise WhatsAppError(f"Falha de rede (Evolution): {exc}")
        return ""
    if settings.MODO_SIMULACAO or not (settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID):
        logger.info("[SIMULA WhatsApp] -> %s: [foto %d bytes] %s", telefone, len(conteudo), legenda)
        return ""
    if media_id:
        try:
            _postar_imagem_meta(telefone, media_id, legenda)
            return media_id
        except WhatsAppError:
            logger.warning("Id de mídia %s recusado; subindo a foto de novo", media_id)
    novo = _subir_midia_sync(conteudo, tipo)
    _postar_imagem_meta(telefone, novo, legenda)
    return novo


def enviar_foto_sync(telefone: str, msg: dict) -> dict:
    """Envia uma FotoCardapio (mensagem {"tipo": "imagem", "foto_id": ...})."""
    from django.utils import timezone

    from cardapio.models import FotoCardapio

    foto = FotoCardapio.objects.filter(id=msg.get("foto_id")).first()
    if not foto:
        logger.warning("Foto %s não existe mais; mensagem ignorada", msg.get("foto_id"))
        return {"ignorado": True}
    usado = enviar_imagem_sync(telefone, bytes(foto.conteudo), foto.tipo,
                               msg.get("legenda") or "", foto.media_valida())
    if usado and usado != foto.meta_media_id:
        FotoCardapio.objects.filter(id=foto.id).update(meta_media_id=usado, meta_media_em=timezone.now())
    return {"ok": True}
