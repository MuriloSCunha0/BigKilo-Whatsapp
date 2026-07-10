"""Pix nativo WhatsApp (order_details) + fallback texto."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from bot.mensagens import T, pix_order
from pedidos.models import ConfiguracaoLoja


def _moeda(v) -> str:
    return f"R$ {Decimal(str(v)):.2f}".replace(".", ",")


def _centavos(valor) -> int:
    return int(Decimal(str(valor)) * 100)


def _tipo_chave_pix(chave: str) -> str:
    chave = (chave or "").strip()
    if "@" in chave:
        return "EMAIL"
    digitos = "".join(c for c in chave if c.isdigit())
    if len(digitos) == 11:
        return "CPF"
    if len(digitos) == 14:
        return "CNPJ"
    if len(digitos) >= 10:
        return "PHONE"
    return "EVP"


def pix_nativo_habilitado() -> bool:
    if settings.MODO_SIMULACAO:
        return False
    if not getattr(settings, "META_PIX_NATIVO", False):
        return False
    return bool(settings.META_ACCESS_TOKEN and settings.META_PHONE_NUMBER_ID)


def montar_order_parameters(pedido, pix_copia_cola: str) -> dict | None:
    cfg = ConfiguracaoLoja.get()
    chave = (cfg.chave_pix or "").strip()
    if not chave or not pix_copia_cola:
        return None

    items = []
    for item in pedido.itens.select_related("produto"):
        nome = item.produto.nome if item.produto_id else "Item"
        if item.variacao:
            nome = f"{nome} ({item.variacao})"
        valor_item = _centavos(item.subtotal)
        items.append(
            {
                "retailer_id": str(item.pk),
                "name": nome[:100],
                "amount": {"value": valor_item, "offset": 100},
                "quantity": int(item.quantidade or 1),
            }
        )

    total = _centavos(pedido.valor_total)
    return {
        "reference_id": f"pedido_{pedido.pk}",
        "type": "digital-goods",
        "payment_type": "br",
        "currency": "BRL",
        "total_amount": {"value": total, "offset": 100},
        "payment_settings": [
            {
                "type": "pix_dynamic_code",
                "pix_dynamic_code": {
                    "code": pix_copia_cola,
                    "merchant_name": (cfg.nome_loja or "Big Kilo")[:25],
                    "key": chave,
                    "key_type": _tipo_chave_pix(chave),
                },
            }
        ],
        "order": {
            "status": "pending",
            "items": items,
            "subtotal": {"value": total, "offset": 100},
        },
    }


def montar_mensagens_pix(pedido, dados_asaas: dict) -> list:
    """Retorna mensagens de checkout Pix (nativo ou fallback texto)."""
    cfg = ConfiguracaoLoja.get()
    copia = dados_asaas.get("pix_copia_cola") or ""
    taxa = pedido.taxa_entrega or Decimal("0")
    subtotal = pedido.valor_total
    total = subtotal + taxa
    corpo = (
        f"Pedido #{pedido.pk} pronto para pagamento!\n"
        f"Produtos (pague no Pix): {_moeda(subtotal)}\n"
        f"Taxa de entrega (ao entregador): {_moeda(taxa)}\n"
        f"Total: {_moeda(total)}"
    )
    params = montar_order_parameters(pedido, copia)
    usar_nativo = pix_nativo_habilitado() and params is not None

    if usar_nativo or settings.MODO_SIMULACAO:
        return [
            pix_order(
                corpo=corpo,
                pedido_id=pedido.pk,
                subtotal_centavos=_centavos(subtotal),
                taxa_centavos=_centavos(taxa),
                pix_copia_cola=copia,
                merchant_name=cfg.nome_loja or "Big Kilo",
                reference_id=f"pedido_{pedido.pk}",
                order_parameters=params or {},
                nativo=usar_nativo,
            ),
            T("Assim que o pagamento cair, seu pedido vai para a cozinha! 🍽️"),
        ]

    return [
        T("💸 Pague com o Pix copia e cola abaixo:"),
        T(copia or "(payload indisponível)"),
        T("Assim que o pagamento cair, seu pedido vai para a cozinha! 🍽️"),
    ]
