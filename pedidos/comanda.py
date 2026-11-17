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


# --------------------------------------------------------------------------
# Encomenda de Natal e Ano Novo: mesma impressora, mesma fila e mesmas duas vias.
# Não tem total (os itens são pesados depois de prontos): o que importa na loja é
# quem é, o que separar e QUANDO a pessoa vem buscar.
_DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]


def _fone(telefone: str) -> str:
    d = "".join(c for c in telefone or "" if c.isdigit())
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    return f"({d[:2]}) {d[2:-4]}-{d[-4:]}" if len(d) in (10, 11) else (telefone or "-")


def gerar_comanda_encomenda(enc) -> str:
    cfg = ConfiguracaoLoja.get()
    linhas = [LINHA, _centro(cfg.nome_loja.upper()), _centro(cfg.slogan), LINHA,
              _centro("*** ENCOMENDA NATAL E ANO NOVO ***"), LINHA]
    feita = timezone.localtime(enc.criado_em).strftime("%d/%m %H:%M")
    linhas.append(f"ENCOMENDA #{enc.pk}".ljust(LARGURA - len(feita)) + feita)
    linhas.append(f"Cliente: {enc.nome}")
    linhas.append(f"Tel: {_fone(enc.telefone)}")
    linhas.append(SUBLINHA)

    if enc.recebe == enc.Recebe.ENTREGA:
        linhas.append("ENTREGA:")
        if enc.endereco:
            linhas.append(enc.endereco)
    else:
        linhas.append("RETIRADA NA LOJA:")
    if enc.data_entrega:
        dia = f"{_DIAS[enc.data_entrega.weekday()]} {enc.data_entrega:%d/%m/%Y}"
        linhas.append(_centro(f">>> {dia}" + (f" AS {enc.horario.upper()}" if enc.horario else "") + " <<<"))
    else:
        linhas.append("Data: a combinar")
    linhas.append(SUBLINHA)

    linhas.append("ITENS:")
    if enc.itens:
        for it in enc.itens:
            cada = f" (~{it['cada']} cada)" if it.get("cada") else ""
            linhas.append(f"- {it.get('rotulo', '')} {it.get('nome', '')}{cada}")
    else:
        for linha in (enc.pedido or "-").splitlines():
            linhas.append(linha.replace("•", "-").replace("—", "-"))
    if enc.observacoes:
        linhas.append(SUBLINHA)
        linhas.append("OBS: " + enc.observacoes)
    linhas.append(SUBLINHA)

    sinal = _moeda(enc.sinal_valor)
    if enc.sinal_pago_em:
        onde = "PIX" if enc.forma_sinal == "PIX" else "NA LOJA"
        situacao = f"SINAL {sinal} PAGO ({onde})"
    elif enc.forma_sinal == "LOJA":
        prazo = f" ATE {cfg.ceia_natal_ate:%d/%m}" if cfg.ceia_natal_ate else ""
        situacao = f"SINAL {sinal} A PAGAR NA LOJA{prazo}"
    elif enc.forma_sinal == "PIX":
        situacao = f"SINAL {sinal} - PIX AGUARDANDO"
    else:
        situacao = f"SINAL {sinal} - A COMBINAR"
    linhas.append(situacao)
    if enc.valor_total:
        linhas.append(("TOTAL:").ljust(20) + _moeda(enc.valor_total).rjust(LARGURA - 20))
    else:
        linhas.append("VALOR FINAL: PELO PESO, DEPOIS DE PRONTO")
    linhas.append(LINHA)
    linhas.append("")
    linhas.append("")
    # A impressora usa cp850: travessão e marcador viram "?". Troca por hífen.
    return "\n".join(linhas).replace("—", "-").replace("•", "-")


def comanda_encomenda_para_impressao(enc, vias: int = VIAS_COMANDA) -> str:
    return CORTE.join([gerar_comanda_encomenda(enc)] * max(1, vias))
