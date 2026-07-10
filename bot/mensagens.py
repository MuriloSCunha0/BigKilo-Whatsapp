"""Mensagens estruturadas para WhatsApp (Meta Cloud API — interativas)."""

from __future__ import annotations


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def T(corpo: str) -> dict:
    return {"tipo": "texto", "corpo": corpo}


def lista(corpo: str, botao: str, linhas: list[dict]) -> dict:
    rows = []
    for row in (linhas or [])[:10]:
        item = {
            "id": str(row["id"]),
            "titulo": _trunc(str(row.get("titulo", "")), 24),
        }
        if row.get("descricao"):
            item["descricao"] = _trunc(str(row["descricao"]), 72)
        rows.append(item)
    return {
        "tipo": "lista",
        "corpo": corpo,
        "botao": _trunc(botao, 20),
        "linhas": rows,
    }


def botoes(corpo: str, opcoes: list[dict]) -> dict:
    opts = []
    for op in opcoes[:3]:
        opts.append(
            {
                "id": str(op["id"]),
                "titulo": _trunc(str(op.get("titulo", "")), 20),
            }
        )
    return {"tipo": "botoes", "corpo": corpo, "opcoes": opts}



def multi_select(corpo: str, opcoes: list[dict], minimo: int = 1, maximo: int = 10) -> dict:
    """Multi-select para simulador (checkboxes). opcoes: [{id, titulo, descricao?}]."""
    opts = []
    for op in opcoes:
        item = {"id": str(op["id"]), "titulo": _trunc(str(op.get("titulo", "")), 40)}
        if op.get("descricao"):
            item["descricao"] = _trunc(str(op["descricao"]), 72)
        opts.append(item)
    return {
        "tipo": "multi_select",
        "corpo": corpo,
        "opcoes": opts,
        "minimo": minimo,
        "maximo": maximo,
        "botao": "Confirmar escolha",
    }


def flow_acompanhamentos(corpo: str, flow_id: str, cta: str, payload: dict) -> dict:
    return {
        "tipo": "flow",
        "corpo": corpo,
        "flow_id": flow_id,
        "cta": _trunc(cta, 20),
        "payload": payload,
    }



def pix_order(
    corpo: str,
    pedido_id: int,
    subtotal_centavos: int,
    taxa_centavos: int,
    pix_copia_cola: str,
    merchant_name: str,
    reference_id: str,
    order_parameters: dict,
    nativo: bool = False,
) -> dict:
    return {
        "tipo": "pix_order",
        "corpo": corpo,
        "pedido_id": pedido_id,
        "subtotal_centavos": subtotal_centavos,
        "taxa_centavos": taxa_centavos,
        "pix_copia_cola": pix_copia_cola,
        "merchant_name": merchant_name,
        "reference_id": reference_id,
        "order_parameters": order_parameters,
        "nativo": nativo,
    }


def texto_plano(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if not isinstance(msg, dict):
        return str(msg)
    tipo = msg.get("tipo", "texto")
    if tipo == "texto":
        return msg.get("corpo", "")
    if tipo == "lista":
        linhas = []
        for row in msg.get("linhas") or []:
            linha = row.get("titulo", "")
            if row.get("descricao"):
                linha += f" — {row['descricao']}"
            linhas.append(linha)
        botao = msg.get("botao", "")
        cab = msg.get("corpo", "")
        extra = f"\n[{botao}] " + " | ".join(linhas) if linhas else ""
        return cab + extra
    if tipo == "multi_select":
        ops = ", ".join(o.get("titulo", "") for o in (msg.get("opcoes") or []))
        return f"{msg.get('corpo', '')}\n[multi-select: {ops}]"
    if tipo == "flow":
        return f"{msg.get('corpo', '')}\n[Flow: {msg.get('cta', 'Abrir')}]"
    if tipo == "pix_order":
        return f"{msg.get('corpo', '')}\n[Pix nativo: pedido #{msg.get('pedido_id')}]"
    if tipo == "botoes":
        ops = " | ".join(o.get("titulo", "") for o in (msg.get("opcoes") or []))
        return f"{msg.get('corpo', '')}\n[botões: {ops}]"
    return str(msg)


def normalizar_mensagens(mensagens: list) -> list[dict]:
    out: list[dict] = []
    for m in mensagens or []:
        if isinstance(m, str):
            out.append(T(m))
        elif isinstance(m, dict) and m.get("tipo"):
            out.append(m)
        else:
            out.append(T(str(m)))
    return out
