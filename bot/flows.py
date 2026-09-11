"""WhatsApp Flow — acompanhamentos multi-select."""

from __future__ import annotations

import json
import secrets

from django.conf import settings

from bot.mensagens import _trunc, flow_acompanhamentos, multi_select


def _usar_flow_whatsapp(lim: int = 2) -> bool:
    """O Flow so vale a pena quando ha mais de um acompanhamento a escolher.

    Com lim == 1 nao existe multiplo a marcar, e um CheckboxGroup com
    max-selected-items = 1 e justamente o caso que a Meta recusa em tempo de
    execucao ("Ocorreu um erro. Tente novamente mais tarde"). Nesse caso a lista
    nativa resolve melhor: um toque e pronto.
    """
    if lim < 2:
        return False
    return bool(
        not settings.MODO_SIMULACAO
        and settings.META_ACCESS_TOKEN
        and settings.META_PHONE_NUMBER_ID
        and getattr(settings, "META_FLOW_ACOMPANHAMENTOS_ID", "")
    )


def montar_tela_acompanhamentos(
    corpo: str,
    opcoes: list[dict],
    mapa: dict,
    lim: int,
    minimo: int = 1,
    escolhidos: list[str] | None = None,
    pagina: int = 0,
):
    """Retorna mensagem flow (WhatsApp) ou multi_select (simulador/dev)."""
    if _usar_flow_whatsapp(lim):
        token = secrets.token_hex(16)
        # Só id e título: "description" vazio no data-source quebra a renderização
        # do Flow, e o nome do prato já basta.
        rows = [
            {"id": str(op["id"]), "title": _trunc(str(op.get("titulo", "")), 30)}
            for op in opcoes
        ]
        payload = {
            "screen": "SELECT_ACOMP",
            "data": {
                "options": rows,
                "min_items": minimo,
                "max_items": lim,
            },
        }
        msg = flow_acompanhamentos(
            corpo,
            settings.META_FLOW_ACOMPANHAMENTOS_ID,
            "Escolher acomp.",
            payload,
            token,
        )
        return msg, mapa, token
    return (
        multi_select(
            corpo, opcoes, minimo=minimo, maximo=lim, escolhidos=escolhidos, pagina=pagina
        ),
        mapa,
        None,
    )


def parse_resposta_acompanhamentos(texto: str) -> list[str] | None:
    if not texto:
        return None
    if texto.startswith("multi:"):
        partes = [p.strip() for p in texto[6:].split(",") if p.strip()]
        return partes or None
    if texto.startswith("{"):
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            return None
        raw = data.get("acompanhamentos") or data.get("selected") or []
        if isinstance(raw, str):
            raw = [raw]
        return [str(x) for x in raw] if raw else None
    return None


def parse_nfm_reply(response_json: str) -> list[str] | None:
    if not response_json:
        return None
    try:
        data = json.loads(response_json)
    except json.JSONDecodeError:
        return None
    raw = data.get("acompanhamentos") or data.get("selected") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    if not isinstance(raw, list):
        raw = [raw]
    return [str(x) for x in raw if x]
