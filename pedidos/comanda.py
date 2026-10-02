"""Geração do texto da comanda (cupom) impressa na cozinha."""

from django.utils import timezone

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

    data = timezone.localtime(pedido.criado_em).strftime("%d/%m %H:%M")
    linhas.append(f"PEDIDO #{pedido.pk}".ljust(LARGURA - len(data)) + data)
    linhas.append(f"Cliente: {pedido.cliente.nome_whatsapp or '-'} ({pedido.cliente.telefone})")
    if pedido.data_agendada:
        linhas.append(LINHA)
        linhas.append(_centro(f"*** ENCOMENDA {pedido.data_agendada.strftime('%d/%m/%Y')} ***"))
        linhas.append(_centro("NAO PREPARAR HOJE"))
        linhas.append(LINHA)
    linhas.append(SUBLINHA)

    # No lojista o destino e uma loja de shopping. Sem esta secao a comanda sairia
    # sem endereco nenhum, porque os campos de rua ficam vazios de proposito.
    if pedido.canal == Pedido.Canal.LOJISTA:
        linhas.append(LINHA)
        linhas.append(_centro("*** LOJISTA ***"))
        linhas.append(f"Local: {pedido.ponto_lojista.nome if pedido.ponto_lojista else '-'}")
        linhas.append(f"Loja:  {pedido.loja_lojista or '-'}")
        linhas.append(LINHA)
    elif pedido.endereco_entrega:
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

    # O pedido so esta pago se o bot cobrou (Pix) E o pagamento foi confirmado.
    # Sem isso, quem entrega precisa saber que ainda vai receber na porta.
    cartao = pedido.forma_pagamento == Pedido.FormaPagamento.CARTAO
    pago = not cartao and pedido.pago_em is not None

    linhas.append(SUBLINHA)
    linhas.append(("TOTAL:").ljust(20) + _moeda(pedido.valor_total).rjust(LARGURA - 20))
    if pedido.taxa_entrega and pedido.taxa_entrega > 0:
        linhas.append("Taxa entrega:")
        linhas.append(_moeda(pedido.taxa_entrega).rjust(LARGURA))
    if cartao:
        rotulo = "COBRAR NO CARTAO:"
    elif pago:
        rotulo = "PAGO PELO CLIENTE:"
    else:
        rotulo = "TOTAL DO PIX:"        # nao e "a receber": quem recebe e o Pix, nao o entregador
    linhas.append(rotulo.ljust(20) + _moeda(pedido.valor_a_cobrar).rjust(LARGURA - 20))

    # Forma de pagamento explicita: quem monta e quem entrega precisa ler de relance
    # se ja foi pago ou se leva a maquininha.
    if cartao:
        forma = "CARTAO (cobrar na entrega)"
    elif pago:
        forma = "PIX (pago)"
    else:
        forma = "PIX (aguardando)"
    linhas.append("PAGAMENTO: ".ljust(12) + forma)
    if pedido.observacoes:
        linhas.append(SUBLINHA)
        linhas.append("OBS: " + pedido.observacoes)

    linhas.append(LINHA)
    # "COBRAR NA ENTREGA" so no cartao. No Pix o entregador nao cobra nada: ou ja
    # foi pago, ou o pagamento ainda esta sendo confirmado -- mandar cobrar ali
    # fazia o entregador pedir dinheiro de quem ja tinha pagado.
    if cartao:
        aviso = "LEVAR MAQUININHA - COBRAR NA ENTREGA"
    elif pago:
        aviso = "PAGO VIA PIX - PREPARAR"
    else:
        aviso = "PIX - AGUARDANDO CONFIRMACAO"
    linhas.append(_centro(aviso))
    linhas.append(LINHA)
    linhas.append("")  # avanço de papel
    linhas.append("")
    return "\n".join(linhas)


# --------------------------------------------------------------------------
# Duas vias: uma vai com o entregador, a outra fica de controle na loja.
#
# O corte vai DENTRO do texto, e não em dois envios separados, porque o agente
# de impressão já instalado no PC do restaurante manda a comanda inteira num
# job só e corta apenas no fim. Emendando o comando de corte no meio, as duas
# vias saem em tiras separadas sem que ninguém precise reinstalar nada lá.
#
# Os bytes são os mesmos que o agente usa no fim do cupom (ESC d 4 = avança 4
# linhas para dar folga; GS V 1 = corte parcial) e atravessam o cp850 intactos,
# porque caracteres de controle têm o mesmo valor nessa codepage.
VIAS_COMANDA = 2
CORTE = "\n" + "\x1b" + "d" + "\x04" + "\x1d" + "V" + "\x01"


def comanda_para_impressao(pedido: Pedido, vias: int = VIAS_COMANDA) -> str:
    """A comanda repetida N vezes, com corte de papel entre uma via e outra."""
    texto = gerar_comanda_texto(pedido)
    return CORTE.join([texto] * max(1, vias))
