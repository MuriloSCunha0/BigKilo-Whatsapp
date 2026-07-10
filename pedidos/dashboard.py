"""Dados do dashboard inicial do painel (KPIs + mais/menos vendidos)."""

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from .loja_pronta import checklist_loja
from .models import ItemPedido, Pedido

PAGOS = [Pedido.Status.PREPARANDO, Pedido.Status.CONCLUIDO]


def _moeda(v) -> str:
    return f"R$ {Decimal(str(v or 0)):.2f}".replace(".", ",")


def dashboard_callback(request, context):
    from .models import PerfilFluxo
    PerfilFluxo.ensure_perfil_padrao()

    hoje = timezone.localdate()
    pedidos_hoje = Pedido.objects.filter(criado_em__date=hoje)
    pagos_hoje = pedidos_hoje.filter(status__in=PAGOS)

    fat = pagos_hoje.aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
    qtd_pagos = pagos_hoje.count()
    aguardando = pedidos_hoje.filter(status=Pedido.Status.AGUARDANDO_PAGAMENTO).count()
    preparando = Pedido.objects.filter(status=Pedido.Status.PREPARANDO).count()
    comandas_pendentes = Pedido.objects.filter(
        status=Pedido.Status.PREPARANDO, comanda_impressa=False,
    ).count()
    ticket = (fat / qtd_pagos) if qtd_pagos else Decimal("0")

    base = (
        ItemPedido.objects.filter(pedido__criado_em__date=hoje, pedido__status__in=PAGOS)
        .values("produto__nome")
        .annotate(qtd=Sum("quantidade"))
        .order_by("-qtd")
    )
    ranking = [{"nome": r["produto__nome"], "qtd": r["qtd"] or 0} for r in base]
    topo = max((r["qtd"] for r in ranking), default=1) or 1
    for r in ranking:
        r["pct"] = round(100 * r["qtd"] / topo)

    mostrar_menos = len(ranking) > 8
    ck = checklist_loja()

    context.update({
        "bk_cards": [
            {"titulo": "Pedidos hoje", "valor": pedidos_hoje.count(), "icone": "receipt_long"},
            {"titulo": "Faturamento hoje", "valor": _moeda(fat), "icone": "payments"},
            {"titulo": "Aguardando pagamento", "valor": aguardando, "icone": "hourglass_top"},
            {"titulo": "Em preparo (cozinha)", "valor": preparando, "icone": "restaurant"},
        ],
        "bk_mais_vendidos": ranking[:8],
        "bk_menos_vendidos": list(reversed(ranking))[:5] if mostrar_menos else [],
        "bk_mostrar_menos": mostrar_menos,
        "bk_checklist": ck,
        "bk_comandas_pendentes": comandas_pendentes,
        "bk_ticket": _moeda(ticket),
    })
    return context
