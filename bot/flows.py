"""WhatsApp Flow — acompanhamentos multi-select."""

from __future__ import annotations

import json
import secrets

from django.conf import settings

from bot.mensagens import _trunc, flow_acompanhamentos, multi_select


def _usar_flow_whatsapp() -> bool:
    return bool(
        not settings.MODO_SIMULACAO
        and settings.META_ACCESS_TOKEN
        and settings.META_PHONE_NUMBER_ID
        and getattr(settings, "META_FLOW_ACOMPANHAMENTOS_ID", "")
    )


def montar_tela_acompanhamentos(corpo: str, opcoes: list[dict], mapa: dict, lim: int, minimo: int = 1):
    """Retorna mensagem flow (WhatsApp) ou multi_select (simulador/dev)."""
    if _usar_flow_whatsapp():
        token = secrets.token_hex(16)
        rows = [
            {
                "id": str(op["id"]),
                "title": _trunc(str(op.get("titulo", "")), 24),
                "description": _trunc(str(op.get("descricao", "") or ""), 72),
            }
            for op in opcoes
        ]
        payload = {
            "screen": "SELECT_ACOMP",
            "data": {
                "options": rows,
                "min_items": minimo,
                "max_items": lim,
                "flow_token": token,
            },
        }
        msg = flow_acompanhamentos(
            corpo,
            settings.META_FLOW_ACOMPANHAMENTOS_ID,
            "Escolher acomp.",
            payload,
        )
        return msg, mapa, token
    return multi_select(corpo, opcoes, minimo=minimo, maximo=lim), mapa, None


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
