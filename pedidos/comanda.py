"""Geração do texto da comanda (cupom) impressa na cozinha."""

from .models import ConfiguracaoLoja, ItemPedido, Pedido

LARGURA = 40  # colunas típicas de impressora térmica 80mm
LINHA = "=" * LARGURA
SUBLINHA = "-" * LARGURA


def _centro(texto: str) -> str:
    return texto.center(LARGURA)


def _moeda(valor) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def gerar_comanda_texto(pedido: Pedido) -> str:
    cfg = ConfiguracaoLoja.get()
    linhas = [LINHA, _centro(cfg.nome_loja.upper()), _centro(cfg.slogan), LINHA]

    data = pedido.criado_em.strftime("%d/%m %H:%M")
    linhas.append(f"PEDIDO #{pedido.pk}".ljust(LARGURA - len(data)) + data)
    linhas.append(f"Cliente: {pedido.cliente.nome_whatsapp or '-'} ({pedido.cliente.telefone})")
    if pedido.data_agendada:
        linhas.append(LINHA)
        linhas.append(_centro(f"*** ENCOMENDA {pedido.data_agendada.strftime('%d/%m/%Y')} ***"))
        linhas.append(_centro("NAO PREPARAR HOJE"))
        linhas.append(LINHA)
    linhas.append(SUBLINHA)

    if pedido.endereco_entrega:
        linhas.append("ENTREGA:")
        linhas.append(pedido.endereco_entrega)
        if pedido.bairro:
            linhas.append(f"Bairro: {pedido.bairro}")
        linhas.append(SUBLINHA)

    linhas.append("ITENS:")
    for item in pedido.itens.all():
        if item.modo == ItemPedido.Modo.FIXO:
            var = f" ({item.variacao})" if item.variacao else ""
            titulo = f"{item.quantidade}x {item.produto.nome}{var}"
        else:
            titulo = f"{item.quantidade}x {item.get_modo_display()} {item.peso_g or '?'}g - {item.produto.nome}"
        linhas.append(titulo)
        acomp = [a.produto.nome for a in item.acompanhamentos.all()]
        if acomp:
            linhas.append("   + " + ", ".join(acomp))
        if item.observacoes:
            linhas.append(f"   obs: {item.observacoes}")
        linhas.append("   " + _moeda(item.subtotal).rjust(LARGURA - 3))

    linhas.append(SUBLINHA)
    linhas.append(("TOTAL:").ljust(20) + _moeda(pedido.valor_total).rjust(LARGURA - 20))
    if pedido.taxa_entrega and pedido.taxa_entrega > 0:
        linhas.append("Taxa entrega (ao entregador):")
        linhas.append(_moeda(pedido.taxa_entrega).rjust(LARGURA))
    if pedido.observacoes:
        linhas.append(SUBLINHA)
        linhas.append("OBS: " + pedido.observacoes)

    linhas.append(LINHA)
    linhas.append(_centro("PAGO VIA PIX - PREPARAR"))
    linhas.append(LINHA)
    linhas.append("")  # avanço de papel
    linhas.append("")
    return "\n".join(linhas)
