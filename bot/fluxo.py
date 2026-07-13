"""
Máquina de estados do bot do Big Kilo (mensagens pré-definidas, sem IA).

Fluxo: saudação -> CEP -> menu -> montagem -> confirmação -> resumo carrinho
-> adicionar (bebida/sobremesa/refeição) -> endereço completo -> Pix.
"""

from decimal import ROUND_HALF_UP, Decimal

from asgiref.sync import sync_to_async

from bot.flows import montar_tela_acompanhamentos, parse_resposta_acompanhamentos
from bot.mensagens import T, botoes, lista, normalizar_mensagens, texto_plano

from cardapio.models import Categoria, Produto
from pedidos.models import (
    AreaEntrega, Cliente, ConfiguracaoLoja, ItemAcompanhamento, ItemPedido, Pedido, PerfilFluxo,
    SessaoBot, mensagem, preco_para, promocoes_exclusivas_ativas,
)


def _cliente(sessao):
    return Cliente.objects.filter(telefone=sessao.telefone).first()


def _ha_promo_global() -> bool:
    return Produto.objects.filter(ativo=True, desconto_percentual__gt=0).exists()


CENTAVO = Decimal("0.01")
PESOS_COMPLETA = {"1": 300, "2": 500, "3": 700}
PESOS_PROTEINA = {"1": 300, "2": 500, "3": 700, "4": 1000}

SAUDACOES = {
    "oi", "oii", "olá", "ola", "opa", "eai", "e ai", "menu", "início", "inicio",
    "voltar", "bom dia", "boa tarde", "boa noite",
}

MENU_CATEGORIAS = {
    "4": (Categoria.Tipo.SANDUICHE, "Sanduíches"),
    "5": (Categoria.Tipo.SOPA, "Sopas"),
}

ESTADOS_TEXTO_LIVRE = {
    SessaoBot.Estado.PEDINDO_CEP,
    SessaoBot.Estado.PEDINDO_ENDERECO_COMPLETO,
}

_MSG_INTERATIVO = T("Toque em uma das opções acima para continuar.")
_ERR_LISTA = "Opção inválida. Toque em uma opção da lista."
_ERR_BOTOES = "Opção inválida. Use um dos botões abaixo."

_PRONTO = {"pronto", "ok", "continuar", "fim", "terminar"}
_SIM = {"1", "sim", "s", "ok", "confirmar", "certo"}
_NAO = {"2", "nao", "não", "n", "fechar", "finalizar"}
_CORRIGIR = {"2", "corrigir", "errado"}
_PULAR_BEBIDA = {"0", "nao", "não", "pular", "continuar", "n"}


def _moeda(v) -> str:
    return f"R$ {Decimal(str(v)):.2f}".replace(".", ",")


def _carrinho_vazio() -> dict:
    return {"endereco": {}, "itens": [], "montagem": {}, "fixo": {}, "_menu": {}, "encomenda": {}}


def _parse_data_futura(texto: str):
    """Interpreta dia/mês (ou dia/mês/ano) e devolve uma date futura, ou None."""
    from datetime import date
    from django.utils import timezone

    hoje = timezone.localdate()
    limpo = (texto or "").replace("-", "/").replace(".", "/").replace(" ", "")
    partes = [p for p in limpo.split("/") if p.isdigit()]
    try:
        if len(partes) == 2:
            dia, mes = int(partes[0]), int(partes[1])
            alvo = date(hoje.year, mes, dia)
            if alvo <= hoje:  # se a data deste ano já passou, assume o próximo
                alvo = date(hoje.year + 1, mes, dia)
        elif len(partes) == 3:
            dia, mes, ano = int(partes[0]), int(partes[1]), int(partes[2])
            if ano < 100:
                ano += 2000
            alvo = date(ano, mes, dia)
        else:
            return None
    except ValueError:
        return None
    return alvo if alvo > hoje else None


def _cep_validado(carrinho: dict) -> bool:
    end = (carrinho or {}).get("endereco") or {}
    return bool(end.get("cep") and end.get("area_id"))


def _endereco_completo(carrinho: dict) -> bool:
    end = (carrinho or {}).get("endereco") or {}
    return bool(end.get("rua") and end.get("cep"))


def _normalizar_cep(cep: str) -> str:
    digitos = "".join(c for c in (cep or "") if c.isdigit())
    if len(digitos) == 8:
        return f"{digitos[:5]}-{digitos[5:]}"
    return digitos


def _set_menu(sessao, mapa: dict):
    sessao.carrinho_json["_menu"] = {str(k): v for k, v in mapa.items()}


def _resolver(sessao, texto: str):
    return sessao.carrinho_json.get("_menu", {}).get(texto.strip())


def _disponiveis(tipo: str):
    qs = Produto.objects.filter(categoria__tipo=tipo, ativo=True).select_related("categoria")
    return [p for p in qs if p.disponivel_agora]


def _lista(produtos, com_preco=False, cliente=None):
    linhas, mapa = [], {}
    for i, p in enumerate(produtos, start=1):
        mapa[str(i)] = p.id
        preco = ""
        if com_preco:
            if p.modo_venda == Produto.ModoVenda.FAIXA:
                f = p.faixas.first()
                preco = f" (a partir de {_moeda(f.preco)})" if f else ""
            else:
                preco = f" ({_moeda(preco_para(p, cliente))})"
        linhas.append(f"{i} - {p.nome}{preco}")
    return "\n".join(linhas), mapa


def _rows_produtos(produtos, com_preco=False, cliente=None, max_rows=10):
    rows, mapa = [], {}
    for i, p in enumerate(produtos[:max_rows], start=1):
        kid = str(i)
        mapa[kid] = p.id
        nome = p.nome
        preco_desc = None
        if com_preco:
            if p.modo_venda == Produto.ModoVenda.FAIXA:
                f = p.faixas.first()
                preco_desc = f"a partir de {_moeda(f.preco)}" if f else None
            else:
                preco_desc = _moeda(preco_para(p, cliente))
        titulo = nome
        desc = preco_desc
        if len(nome) > 24:
            desc = f"{nome}" + (f" — {preco_desc}" if preco_desc else "")
            titulo = nome
        row = {"id": kid, "titulo": titulo}
        if desc:
            row["descricao"] = desc
        rows.append(row)
    return rows, mapa


def _linha_item_carrinho(it) -> str:
    prod = Produto.objects.filter(id=it.get("produto_id")).first()
    nome = prod.nome if prod else "Item"
    if it.get("modo") == ItemPedido.Modo.COMPLETA:
        extra = f" {it.get('peso_g')}g"
    elif it.get("peso_g"):
        extra = f" {it.get('peso_g')}g"
    elif it.get("variacao"):
        extra = f" ({it.get('variacao')})"
    else:
        extra = ""
    qtd = int(it.get("quantidade") or 1)
    sub = _moeda(it.get("subtotal", "0"))
    prefix = f"{qtd}x " if qtd > 1 else ""
    return f"• {prefix}{nome}{extra} — {sub}"


def _avisos_promo(cliente, perfil=None) -> list[str]:
    avisos = []
    promos = promocoes_exclusivas_ativas(cliente)
    if promos:
        for pe in promos:
            avisos.append(
                pe.mensagem or f"🎁 Promoção exclusiva: {pe.produto.nome} com {pe.desconto_percentual:.0f}% off!"
            )
    elif _ha_promo_global():
        avisos.append(mensagem("ANUNCIO_PROMO", cliente, perfil=perfil))
    return avisos



def _tela_menu(sessao) -> list:
    sessao.estado_atual = SessaoBot.Estado.MENU_PRINCIPAL
    _set_menu(sessao, {})
    itens = sessao.carrinho_json["itens"]
    cab = ""
    if itens:
        total = sum(Decimal(str(i["subtotal"])) for i in itens)
        cab = f"🛒 Carrinho: {len(itens)} item(ns) - {_moeda(total)}\n\n"

    linhas = [
        {"id": "1", "titulo": "Montar refeição completa"},
        {"id": "2", "titulo": "Grandes porções"},
        {"id": "3", "titulo": "Encomenda outro dia"},
        {"id": "4", "titulo": "Sanduíches"},
        {"id": "5", "titulo": "Sopas"},
        {"id": "fechar", "titulo": "Fechar pedido"},
    ]
    corpo = (
        cab
        + "O que você deseja?\n"
        "Toque em *Ver opções* para escolher.\n\n"
        "*cancelar* recomeça o pedido."
    )
    return [lista(corpo, "Ver opções", linhas)]

def _entrar_menu(sessao, perfil=None) -> list[str]:
    cliente = _cliente(sessao)
    return _avisos_promo(cliente, perfil) + _tela_menu(sessao)


def _preco_proteina(cfg, produto, peso_g):
    custom = produto.preco_proteina_custom(peso_g) if produto else None
    return custom if custom is not None else cfg.preco_proteina(peso_g)



def _tela_peso(sessao, modo, produto=None, perfil=None) -> list:
    cfg = ConfiguracaoLoja.get()
    sessao.estado_atual = SessaoBot.Estado.ESCOLHENDO_PESO
    cliente = _cliente(sessao)
    if modo == ItemPedido.Modo.COMPLETA:
        tabela = PESOS_COMPLETA
        titulo = mensagem("MONTAR_REFEICAO", cliente, perfil=perfil)
        linhas = []
        for k, g in tabela.items():
            linhas.append(
                {
                    "id": k,
                    "titulo": f"{g}g",
                    "descricao": f"{_moeda(cfg.preco_completa(g))}, até {cfg.lim_acomp(g)} acomp.",
                }
            )
    else:
        nome = f" — {produto.nome}" if produto else ""
        tabela = PESOS_PROTEINA
        titulo = f"Grandes porções{nome}"
        linhas = []
        for k, g in tabela.items():
            linhas.append(
                {
                    "id": k,
                    "titulo": f"{g}g",
                    "descricao": _moeda(_preco_proteina(cfg, produto, g)),
                }
            )
    _set_menu(sessao, {k: g for k, g in tabela.items()})
    return [lista(titulo, "Escolher peso", linhas)]


def _tela_proteinas(sessao, perfil=None) -> list:
    proteinas = _disponiveis(Categoria.Tipo.PROTEINA)
    if not proteinas:
        return [T("No momento não há proteínas disponíveis.")] + _tela_menu(sessao)
    sessao.estado_atual = SessaoBot.Estado.ESCOLHENDO_ITENS
    rows, mapa = _rows_produtos(proteinas)
    _set_menu(sessao, mapa)
    prefixo = mensagem("ESCOLHER_PROTEINA", _cliente(sessao), perfil=perfil)
    return [lista(prefixo, "Ver proteínas", rows)]


def _tela_acompanhamentos(sessao, perfil=None) -> list:
    cfg = ConfiguracaoLoja.get()
    peso = sessao.carrinho_json["montagem"]["peso_g"]
    lim = cfg.lim_acomp(peso)
    acomps = _disponiveis(Categoria.Tipo.ACOMPANHAMENTO)
    sessao.estado_atual = SessaoBot.Estado.MONTANDO_PRATO
    rows, mapa = _rows_produtos(acomps)
    opcoes = [
        {"id": r["id"], "titulo": r["titulo"], **({"descricao": r["descricao"]} if r.get("descricao") else {})}
        for r in rows
    ]
    prefixo = mensagem("ESCOLHER_ACOMPANHAMENTOS", _cliente(sessao), perfil=perfil, lim=lim)
    corpo = prefixo
    msg, mapa, token = montar_tela_acompanhamentos(corpo, opcoes, mapa, lim, minimo=1)
    _set_menu(sessao, mapa)
    if token:
        sessao.carrinho_json.setdefault("_flow", {})["acom_token"] = token
    return [msg]
def _tela_confirmacao(sessao) -> list:
    m = sessao.carrinho_json["montagem"]
    prot = Produto.objects.filter(id=m.get("produto_id")).first()
    prot_nome = prot.nome if prot else "Proteína"
    ids = m.get("acompanhamentos") or []
    nomes_ac = []
    if ids:
        por_id = {p.id: p.nome for p in Produto.objects.filter(id__in=ids)}
        nomes_ac = [por_id[i] for i in ids if i in por_id]
    sessao.estado_atual = SessaoBot.Estado.CONFIRMANDO_ITEM
    _set_menu(sessao, {})
    linhas = [f"🍽️ Confira seu prato ({m.get('peso_g')}g):", f"• Proteína: {prot_nome}"]
    if nomes_ac:
        linhas.append("• Acompanhamentos: " + ", ".join(nomes_ac))
    corpo = "\n".join(linhas)
    return [
        botoes(
            corpo,
            [
                {"id": "1", "titulo": "Sim, adicionar"},
                {"id": "2", "titulo": "Corrigir"},
                {"id": "3", "titulo": "Menu"},
            ],
        )
    ]


def _tela_resumo_carrinho(sessao, perfil=None) -> list:
    itens = sessao.carrinho_json.get("itens") or []
    sessao.estado_atual = SessaoBot.Estado.RESUMO_CARRINHO
    _set_menu(sessao, {"corrigir": "corrigir", "adicionar": "adicionar", "fechar": "fechar"})
    cab = mensagem("RESUMO_CARRINHO", _cliente(sessao), perfil=perfil)
    linhas = [cab, "", "🛒 *Seu pedido:*"]
    for it in itens:
        linhas.append(_linha_item_carrinho(it))
    total = sum(Decimal(str(i["subtotal"])) for i in itens)
    linhas.append(f"\n*Subtotal:* {_moeda(total)}")
    corpo = "\n".join(linhas)
    return [
        botoes(
            corpo,
            [
                {"id": "corrigir", "titulo": "Corrigir último"},
                {"id": "adicionar", "titulo": "Adicionar mais"},
                {"id": "fechar", "titulo": "Fechar pedido"},
            ],
        )
    ]


def _tela_perguntar_adicionar(sessao, perfil=None) -> list:
    sessao.estado_atual = SessaoBot.Estado.PERGUNTANDO_ADICIONAR
    _set_menu(sessao, {"bebida": "bebida", "sobremesa": "sobremesa", "refeicao": "menu", "voltar": "resumo"})
    corpo = mensagem("PERGUNTAR_ADICIONAR", _cliente(sessao), perfil=perfil)
    linhas = [
        {"id": "bebida", "titulo": "Bebida", "descricao": "Refrigerante, suco..."},
        {"id": "sobremesa", "titulo": "Sobremesa", "descricao": "Doces e sobremesas"},
        {"id": "refeicao", "titulo": "Outra refeição", "descricao": "Voltar ao cardápio"},
        {"id": "voltar", "titulo": "Só isso", "descricao": "Voltar ao resumo"},
    ]
    return [lista(corpo, "Ver opções", linhas)]


def _tela_lista_extra(sessao, tipo: str, titulo: str) -> list:
    produtos = _disponiveis(tipo)
    if not produtos:
        return [T(f"No momento não há {titulo.lower()} disponíveis.")] + _tela_perguntar_adicionar(sessao)
    sessao.estado_atual = SessaoBot.Estado.OFERTA_BEBIDA
    sessao.carrinho_json["_extra_tipo"] = tipo
    rows, mapa = _rows_produtos(produtos, com_preco=True, cliente=_cliente(sessao))
    rows.append({"id": "voltar", "titulo": "Voltar", "descricao": "Sem adicionar"})
    mapa["voltar"] = "voltar"
    _set_menu(sessao, mapa)
    return [lista(f"Escolha {titulo.lower()}:", "Ver opções", rows)]


def _pos_item_adicionado(sessao, msgs: list, perfil=None) -> list:
    return msgs + _tela_resumo_carrinho(sessao, perfil)



def _tela_categoria(sessao, tipo, titulo) -> list:
    produtos = _disponiveis(tipo)
    if not produtos:
        return [T(f"No momento não há {titulo.lower()} disponíveis.")] + _tela_menu(sessao)
    sessao.estado_atual = SessaoBot.Estado.ESCOLHENDO_FIXO
    sessao.carrinho_json["_ultimo_tipo_fixo"] = {"tipo": tipo, "titulo": titulo}
    rows, mapa = _rows_produtos(produtos, com_preco=True, cliente=_cliente(sessao))
    _set_menu(sessao, mapa)
    return [lista(f"{titulo}:", "Ver itens", rows)]


def _tela_faixas(sessao, produto) -> list:
    sessao.carrinho_json["fixo"] = {"produto_id": produto.id}
    sessao.estado_atual = SessaoBot.Estado.ESCOLHENDO_FAIXA
    faixas = list(produto.faixas.all())
    mapa = {str(i): f.id for i, f in enumerate(faixas, start=1)}
    _set_menu(sessao, mapa)
    linhas = [
        {"id": str(i), "titulo": f.rotulo, "descricao": _moeda(f.preco)}
        for i, f in enumerate(faixas, start=1)
    ]
    corpo = f"{produto.nome} — escolha o tamanho:"
    return [lista(corpo, "Tamanhos", linhas)]

def _finalizar_completa(sessao) -> list[str]:
    cfg = ConfiguracaoLoja.get()
    m = sessao.carrinho_json["montagem"]
    preco = cfg.preco_completa(m["peso_g"])
    produto_id = m["produto_id"]
    sessao.carrinho_json["itens"].append({
        "modo": ItemPedido.Modo.COMPLETA, "produto_id": produto_id, "peso_g": m["peso_g"],
        "variacao": f"{m['peso_g']}g", "acompanhamentos": list(m["acompanhamentos"]),
        "preco_unitario": str(preco), "quantidade": 1, "subtotal": str(preco),
    })
    sessao.carrinho_json["montagem"] = {}
    prot = Produto.objects.get(id=produto_id)
    return [f"✅ Adicionado: {prot.nome} {m['peso_g']}g — {_moeda(preco)}"]


def _finalizar_proteina(sessao) -> list[str]:
    cfg = ConfiguracaoLoja.get()
    m = sessao.carrinho_json["montagem"]
    prot = Produto.objects.get(id=m["produto_id"])
    preco = _preco_proteina(cfg, prot, m["peso_g"])
    sessao.carrinho_json["itens"].append({
        "modo": ItemPedido.Modo.PROTEINA, "produto_id": m["produto_id"], "peso_g": m["peso_g"],
        "variacao": f"{m['peso_g']}g", "acompanhamentos": [],
        "preco_unitario": str(preco), "quantidade": 1, "subtotal": str(preco),
    })
    sessao.carrinho_json["montagem"] = {}
    return [f"✅ Adicionado: {prot.nome} {m['peso_g']}g (só proteína) — {_moeda(preco)}"]


def _add_unidade(sessao, produto) -> list[str]:
    preco = preco_para(produto, _cliente(sessao))
    sessao.carrinho_json["itens"].append({
        "modo": ItemPedido.Modo.FIXO, "produto_id": produto.id, "peso_g": None, "variacao": "",
        "acompanhamentos": [], "preco_unitario": str(preco), "quantidade": 1, "subtotal": str(preco),
    })
    return [f"✅ Adicionado: {produto.nome} — {_moeda(preco)}"]


def _add_faixa(sessao, faixa) -> list[str]:
    sessao.carrinho_json["itens"].append({
        "modo": ItemPedido.Modo.FIXO, "produto_id": faixa.produto_id, "peso_g": None,
        "variacao": faixa.rotulo, "acompanhamentos": [],
        "preco_unitario": str(faixa.preco), "quantidade": 1, "subtotal": str(faixa.preco),
    })
    sessao.carrinho_json["fixo"] = {}
    return [f"✅ Adicionado: {faixa.produto.nome} ({faixa.rotulo}) — {_moeda(faixa.preco)}"]


def _checkout(sessao):
    itens = sessao.carrinho_json["itens"]
    if not itens:
        return None, ["Seu carrinho está vazio."] + _tela_menu(sessao)

    validos, removidos = [], []
    for it in itens:
        prod = Produto.objects.filter(id=it["produto_id"]).first()
        if prod and prod.disponivel_agora:
            validos.append(it)
        else:
            removidos.append(prod.nome if prod else "item")
    avisos = []
    if removidos:
        avisos.append("⚠️ Estes itens acabaram e saíram do pedido: " + ", ".join(removidos) + ".")
    if not validos:
        sessao.carrinho_json["itens"] = []
        return None, avisos + ["Seu pedido ficou sem itens. 😕"] + _tela_menu(sessao)
    sessao.carrinho_json["itens"] = validos
    itens = validos

    cfg = ConfiguracaoLoja.get()
    cliente, _ = Cliente.objects.get_or_create(telefone=sessao.telefone)
    end = sessao.carrinho_json.get("endereco", {})
    data_enc = (sessao.carrinho_json.get("encomenda") or {}).get("data")
    data_obj = None
    if data_enc:
        from datetime import date
        try:
            data_obj = date.fromisoformat(data_enc)
        except ValueError:
            data_obj = None
    pedido = Pedido.objects.create(
        cliente=cliente, status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        endereco_entrega=end.get("rua", ""), bairro=end.get("bairro", ""),
        cep=end.get("cep", ""), taxa_entrega=cfg.taxa_entrega,
        data_agendada=data_obj,
    )
    for it in itens:
        item = ItemPedido.objects.create(
            pedido=pedido, modo=it["modo"], produto_id=it["produto_id"], peso_g=it["peso_g"],
            variacao=it.get("variacao", ""), quantidade=it["quantidade"],
            preco_unitario=Decimal(it["preco_unitario"]),
        )
        for ac_id in it["acompanhamentos"]:
            ac = Produto.objects.get(id=ac_id)
            ItemAcompanhamento.objects.create(item_pedido=item, produto=ac, preco_adicional=ac.preco)
    pedido.recalcular_total()
    pedido.save(update_fields=["valor_total"])
    sessao.estado_atual = SessaoBot.Estado.AGUARDANDO_PAGAMENTO
    sessao.carrinho_json = _carrinho_vazio()

    produtos = pedido.valor_total
    taxa = pedido.taxa_entrega
    total = (produtos + taxa).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    linhas = [f"Pedido #{pedido.pk} confirmado! 🧾"]
    if pedido.data_agendada:
        linhas.append(f"📅 Encomenda para {pedido.data_agendada.strftime('%d/%m/%Y')}")
    linhas += [
        f"Produtos: {_moeda(produtos)}",
        f"Taxa de entrega: {_moeda(taxa)} (paga ao entregador na entrega)",
        f"Total: {_moeda(total)}",
        "",
        f"💳 Agora pague os *{_moeda(produtos)}* dos produtos pelo Pix. "
        f"A taxa de {_moeda(taxa)} você paga ao entregador. Gerando seu Pix...",
    ]
    return pedido.pk, avisos + ["\n".join(linhas)]


def _iniciar_fechamento(sessao, perfil=None):
    if not sessao.carrinho_json.get("itens"):
        return None, ["Seu carrinho está vazio."] + _tela_menu(sessao)
    end = sessao.carrinho_json.get("endereco") or {}
    if not end.get("rua"):
        sessao.estado_atual = SessaoBot.Estado.PEDINDO_ENDERECO_COMPLETO
        return None, [mensagem("PEDIR_ENDERECO_COMPLETO", _cliente(sessao), perfil=perfil)]
    return _checkout(sessao)


_fechar_pedido = _iniciar_fechamento


def _parse_selecoes(texto: str) -> list[str]:
    partes = [p.strip() for p in texto.replace(";", ",").split(",")]
    return [p for p in partes if p]



def _adicionar_acompanhamentos(sessao, selecoes: list[str], cfg, perfil=None) -> list:
    m = sessao.carrinho_json["montagem"]
    lim = cfg.lim_acomp(m["peso_g"])
    escolhidos = m["acompanhamentos"]
    erros = []

    for sel in selecoes:
        low = sel.lower()
        if sel == "pronto" or low in _PRONTO or sel == "0":
            if len(escolhidos) < 1:
                return [T("Escolha pelo menos 1 acompanhamento antes de continuar.")] + _tela_acompanhamentos(
                    sessao, perfil
                )
            return _tela_confirmacao(sessao)
        pid = _resolver(sessao, sel)
        if not pid:
            erros.append(f"Opção inválida: {sel}.")
            continue
        if pid in escolhidos:
            continue
        if len(escolhidos) >= lim:
            erros.append(f"Limite de {lim} acompanhamentos atingido.")
            break
        escolhidos.append(pid)

    if erros:
        return [T(e) for e in erros] + _tela_acompanhamentos(sessao, perfil)
    return _tela_acompanhamentos(sessao, perfil)


def _aplicar_acompanhamentos_multi(sessao, selecoes: list[str], cfg, perfil=None) -> list:
    m = sessao.carrinho_json["montagem"]
    lim = cfg.lim_acomp(m["peso_g"])
    escolhidos = []
    erros = []
    for sel in selecoes:
        pid = _resolver(sessao, sel)
        if not pid:
            erros.append(f"Opcao invalida: {sel}.")
            continue
        if pid in escolhidos:
            continue
        if len(escolhidos) >= lim:
            erros.append(f"Limite de {lim} acompanhamentos.")
            break
        escolhidos.append(pid)
    if len(escolhidos) < 1:
        return [T("Escolha pelo menos 1 acompanhamento.")] + _tela_acompanhamentos(sessao, perfil)
    if erros:
        return [T(e) for e in erros] + _tela_acompanhamentos(sessao, perfil)
    m["acompanhamentos"] = escolhidos
    return _tela_confirmacao(sessao)


def _core(telefone: str, texto: str, nome: str, perfil_id=None) -> dict:
    texto = (texto or "").strip()
    low = texto.lower()
    perfil = PerfilFluxo.objects.filter(id=perfil_id).first() if perfil_id else None
    sessao, _ = SessaoBot.objects.get_or_create(telefone=telefone)
    if not sessao.carrinho_json:
        sessao.carrinho_json = _carrinho_vazio()
    for k, v in _carrinho_vazio().items():
        sessao.carrinho_json.setdefault(k, v)
    if nome:
        Cliente.objects.update_or_create(telefone=telefone, defaults={"nome_whatsapp": nome})

    out = {"mensagens": [], "checkout_pedido_id": None}

    if low in {"cancelar", "reiniciar", "recomeçar", "recomecar"}:
        sessao.carrinho_json = _carrinho_vazio()
        out["mensagens"] = ["Pedido reiniciado."] + _saudacao(sessao, perfil)
        sessao.save()
        return out

    cfg = ConfiguracaoLoja.get()
    estado = sessao.estado_atual
    cep_ok = _cep_validado(sessao.carrinho_json)

    if low in SAUDACOES and estado != SessaoBot.Estado.AGUARDANDO_PAGAMENTO:
        if cep_ok:
            out["mensagens"] = _tela_menu(sessao)
        else:
            out["mensagens"] = _saudacao(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.MENU_PRINCIPAL and not cep_ok:
        out["mensagens"] = _saudacao(sessao, perfil)
        sessao.save()
        return out

    if estado in (SessaoBot.Estado.PEDINDO_ENDERECO, SessaoBot.Estado.PEDINDO_RUA):
        out["mensagens"] = _saudacao(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.PEDINDO_CEP:
        digitos = "".join(c for c in texto if c.isdigit())
        if len(digitos) != 8:
            out["mensagens"] = [mensagem("CEP_INVALIDO", _cliente(sessao), perfil=perfil)]
            sessao.save()
            return out
        cep = _normalizar_cep(digitos)
        area = AreaEntrega.por_cep(cep)
        if not area:
            out["mensagens"] = [mensagem("FORA_AREA", _cliente(sessao), perfil=perfil)]
            sessao.save()
            return out
        sessao.carrinho_json["endereco"] = {
            "bairro": area.bairro,
            "area_id": area.id,
            "cep": cep,
            "rua": "",
        }
        # Fora do horário avisamos, mas deixamos continuar (encomenda futura funciona
        # mesmo fechado; o pedido para HOJE fica barrado no menu).
        avisos = ["📍 CEP confirmado!"]
        if not cfg.esta_aberta:
            avisos.append(
                f"ℹ️ Estamos fechados agora (das {cfg.hora_abertura:%H:%M} às "
                f"{cfg.hora_fechamento:%H:%M}). Você pode *agendar uma encomenda* "
                "escolhendo *Encomenda outro dia* no menu."
            )
        out["mensagens"] = avisos + _entrar_menu(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.MENU_PRINCIPAL:
        encomenda = bool(sessao.carrinho_json.get("encomenda", {}).get("data"))
        loja_fechada = not cfg.esta_aberta
        # Opção 3: agendar encomenda para outro dia (permitida mesmo com a loja fechada).
        if low == "3":
            sessao.estado_atual = SessaoBot.Estado.ENCOMENDA_FUTURA
            _set_menu(sessao, {})
            out["mensagens"] = [mensagem("PEDIR_DATA_ENCOMENDA", _cliente(sessao), perfil=perfil)]
            sessao.save()
            return out
        # Pedido para HOJE fica barrado quando a loja está fechada (encomenda passa).
        imediato = low in {"1", "2", "fechar", "finalizar"} or low in MENU_CATEGORIAS
        if imediato and loja_fechada and not encomenda:
            out["mensagens"] = [
                f"Estamos fechados agora (das {cfg.hora_abertura:%H:%M} às {cfg.hora_fechamento:%H:%M}). "
                "Para receber outro dia, escolha *Encomenda outro dia* no menu. 🙂"
            ] + _tela_menu(sessao)
            sessao.save()
            return out
        if low in {"fechar", "finalizar"} or texto.strip() == "fechar":
            pid, msgs = _iniciar_fechamento(sessao, perfil)
            out["mensagens"], out["checkout_pedido_id"] = msgs, pid
        elif low == "1":
            sessao.carrinho_json["montagem"] = {"modo": ItemPedido.Modo.COMPLETA, "acompanhamentos": []}
            out["mensagens"] = _tela_peso(sessao, ItemPedido.Modo.COMPLETA, perfil=perfil)
        elif low == "2":
            sessao.carrinho_json["montagem"] = {"modo": ItemPedido.Modo.PROTEINA, "acompanhamentos": []}
            out["mensagens"] = _tela_proteinas(sessao, perfil)
        elif low in MENU_CATEGORIAS:
            out["mensagens"] = _tela_categoria(sessao, *MENU_CATEGORIAS[low])
        else:
            out["mensagens"] = ["Opção inválida."] + _tela_menu(sessao)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.ENCOMENDA_FUTURA:
        data = _parse_data_futura(texto)
        if not data:
            out["mensagens"] = [mensagem("DATA_INVALIDA", _cliente(sessao), perfil=perfil)]
            sessao.save()
            return out
        sessao.carrinho_json["encomenda"] = {"data": data.isoformat()}
        aviso = mensagem("ENCOMENDA_AGENDADA", _cliente(sessao), perfil=perfil, data=data.strftime("%d/%m/%Y"))
        out["mensagens"] = [aviso] + _tela_menu(sessao)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.ESCOLHENDO_PESO:
        modo = sessao.carrinho_json["montagem"]["modo"]
        tabela = PESOS_COMPLETA if modo == ItemPedido.Modo.COMPLETA else PESOS_PROTEINA
        peso = tabela.get(texto.strip())
        if not peso:
            produto = None
            if modo == ItemPedido.Modo.PROTEINA:
                pid = sessao.carrinho_json["montagem"].get("produto_id")
                produto = Produto.objects.filter(id=pid).first() if pid else None
            out["mensagens"] = [_ERR_LISTA] + _tela_peso(sessao, modo, produto, perfil=perfil)
        else:
            sessao.carrinho_json["montagem"]["peso_g"] = peso
            if modo == ItemPedido.Modo.COMPLETA:
                out["mensagens"] = _tela_proteinas(sessao, perfil)
            else:
                msgs = _finalizar_proteina(sessao)
                out["mensagens"] = _pos_item_adicionado(sessao, msgs, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.ESCOLHENDO_ITENS:
        pid = _resolver(sessao, texto)
        if not pid:
            out["mensagens"] = [_ERR_LISTA] + _tela_proteinas(sessao, perfil)
        else:
            sessao.carrinho_json["montagem"]["produto_id"] = pid
            if sessao.carrinho_json["montagem"]["modo"] == ItemPedido.Modo.COMPLETA:
                out["mensagens"] = _tela_acompanhamentos(sessao, perfil)
            else:
                out["mensagens"] = _tela_peso(
                    sessao, ItemPedido.Modo.PROTEINA, Produto.objects.get(id=pid), perfil=perfil
                )
        sessao.save()
        return out

    if estado == SessaoBot.Estado.MONTANDO_PRATO:
        selecoes_multi = parse_resposta_acompanhamentos(texto)
        if selecoes_multi:
            out["mensagens"] = _aplicar_acompanhamentos_multi(sessao, selecoes_multi, cfg, perfil)
        elif "," in texto or ";" in texto:
            out["mensagens"] = _adicionar_acompanhamentos(sessao, _parse_selecoes(texto), cfg, perfil)
        else:
            out["mensagens"] = _adicionar_acompanhamentos(sessao, [texto.strip()], cfg, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.CONFIRMANDO_ITEM:
        if low in _SIM or texto.strip() == "1":
            msgs = _finalizar_completa(sessao)
            out["mensagens"] = _pos_item_adicionado(sessao, msgs, perfil)
        elif low in _CORRIGIR or texto.strip() == "2":
            sessao.carrinho_json["montagem"]["acompanhamentos"] = []
            out["mensagens"] = _tela_acompanhamentos(sessao, perfil)
        elif texto.strip() == "3" or low in {"menu", "voltar"}:
            sessao.carrinho_json["montagem"] = {}
            out["mensagens"] = _tela_menu(sessao)
        else:
            out["mensagens"] = [_ERR_BOTOES] + _tela_confirmacao(sessao)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.RESUMO_CARRINHO:
        acao = _resolver(sessao, texto) or low
        if acao == "corrigir" or low in {"corrigir", "2"}:
            itens = sessao.carrinho_json.get("itens") or []
            if itens:
                removido = itens.pop()
                prod = Produto.objects.filter(id=removido.get("produto_id")).first()
                nome = prod.nome if prod else "item"
                out["mensagens"] = [f"Removido: {nome}."] + _tela_resumo_carrinho(sessao, perfil)
            else:
                out["mensagens"] = ["Seu carrinho está vazio."] + _tela_menu(sessao)
        elif acao == "adicionar" or low in {"adicionar", "1"}:
            out["mensagens"] = _tela_perguntar_adicionar(sessao, perfil)
        elif acao == "fechar" or low in {"fechar", "finalizar", "3"}:
            pid, msgs = _iniciar_fechamento(sessao, perfil)
            out["mensagens"], out["checkout_pedido_id"] = msgs, pid
        else:
            out["mensagens"] = [_ERR_BOTOES] + _tela_resumo_carrinho(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.PERGUNTANDO_ADICIONAR:
        acao = _resolver(sessao, texto) or low
        if acao == "bebida" or low == "bebida":
            out["mensagens"] = _tela_lista_extra(sessao, Categoria.Tipo.BEBIDA, "Bebida")
        elif acao == "sobremesa" or low == "sobremesa":
            out["mensagens"] = _tela_lista_extra(sessao, Categoria.Tipo.SOBREMESA, "Sobremesa")
        elif acao in {"refeicao", "menu"} or low in {"refeicao", "menu"}:
            out["mensagens"] = _tela_menu(sessao)
        elif acao == "resumo" or low in {"voltar", "resumo"}:
            out["mensagens"] = _tela_resumo_carrinho(sessao, perfil)
        else:
            out["mensagens"] = [_ERR_LISTA] + _tela_perguntar_adicionar(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.OFERTA_BEBIDA:
        if low in _PULAR_BEBIDA or texto.strip() in {"pular", "voltar"}:
            out["mensagens"] = _tela_resumo_carrinho(sessao, perfil)
        else:
            pid = _resolver(sessao, texto)
            if pid == "voltar":
                out["mensagens"] = _tela_perguntar_adicionar(sessao, perfil)
            elif not pid:
                tipo = sessao.carrinho_json.get("_extra_tipo", Categoria.Tipo.BEBIDA)
                titulo = "Bebida" if tipo == Categoria.Tipo.BEBIDA else "Sobremesa"
                out["mensagens"] = [_ERR_LISTA] + _tela_lista_extra(sessao, tipo, titulo)
            else:
                produto = Produto.objects.get(id=pid)
                if produto.modo_venda == Produto.ModoVenda.FAIXA:
                    out["mensagens"] = [_ERR_LISTA] + _tela_lista_extra(
                        sessao,
                        sessao.carrinho_json.get("_extra_tipo", Categoria.Tipo.BEBIDA),
                        "item",
                    )
                else:
                    msgs = _add_unidade(sessao, produto)
                    out["mensagens"] = _pos_item_adicionado(sessao, msgs, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.PERGUNTANDO_MAIS_ITEM:
        if texto.strip() == "1" or low in _SIM:
            out["mensagens"] = _tela_menu(sessao)
        elif texto.strip() == "2" or low in _NAO:
            pid, msgs = _iniciar_fechamento(sessao, perfil)
            out["mensagens"], out["checkout_pedido_id"] = msgs, pid
        else:
            out["mensagens"] = [_ERR_BOTOES] + _tela_resumo_carrinho(sessao, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.PEDINDO_ENDERECO_COMPLETO:
        sessao.carrinho_json.setdefault("endereco", {})["rua"] = texto
        pid, msgs = _checkout(sessao)
        out["mensagens"], out["checkout_pedido_id"] = msgs, pid
        sessao.save()
        return out

    if estado == SessaoBot.Estado.ESCOLHENDO_FIXO:
        pid = _resolver(sessao, texto)
        if not pid:
            info = sessao.carrinho_json.get("_ultimo_tipo_fixo") or {}
            titulo = info.get("titulo", "itens")
            out["mensagens"] = [_ERR_LISTA] + _tela_categoria(sessao, info.get("tipo"), titulo)
        else:
            produto = Produto.objects.get(id=pid)
            if produto.modo_venda == Produto.ModoVenda.FAIXA:
                out["mensagens"] = _tela_faixas(sessao, produto)
            else:
                msgs = _add_unidade(sessao, produto)
                out["mensagens"] = _pos_item_adicionado(sessao, msgs, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.ESCOLHENDO_FAIXA:
        fid = _resolver(sessao, texto)
        if not fid:
            fixo = sessao.carrinho_json.get("fixo") or {}
            produto = Produto.objects.filter(id=fixo.get("produto_id")).first()
            if produto:
                out["mensagens"] = [_ERR_LISTA] + _tela_faixas(sessao, produto)
            else:
                out["mensagens"] = [_ERR_LISTA] + _tela_menu(sessao)
        else:
            from cardapio.models import FaixaPreco
            msgs = _add_faixa(sessao, FaixaPreco.objects.select_related("produto").get(id=fid))
            out["mensagens"] = _pos_item_adicionado(sessao, msgs, perfil)
        sessao.save()
        return out

    if estado == SessaoBot.Estado.AGUARDANDO_PAGAMENTO:
        out["mensagens"] = [mensagem("AGUARDANDO_PAGAMENTO", _cliente(sessao), perfil=perfil)]
        sessao.save()
        return out

    out["mensagens"] = _saudacao(sessao, perfil)
    sessao.save()
    return out


def _saudacao(sessao, perfil=None) -> list[str]:
    cliente = _cliente(sessao)
    sessao.estado_atual = SessaoBot.Estado.PEDINDO_CEP
    _set_menu(sessao, {})
    saudacao = (
        f"{mensagem('BOAS_VINDAS', cliente, perfil=perfil)}\n\n"
        f"{mensagem('PEDIR_CEP', cliente, perfil=perfil)}"
    )
    return [saudacao]



def _registrar_conversa(telefone: str, texto_in: str, mensagens_out: list):
    """Grava o bate-papo (entrada do cliente + respostas do bot) para o monitor."""
    from pedidos.models import LogMensagem
    if texto_in:
        LogMensagem.objects.create(telefone=telefone, direcao=LogMensagem.Direcao.ENTRADA, texto=texto_in)
    for m in mensagens_out:
        LogMensagem.objects.create(
            telefone=telefone, direcao=LogMensagem.Direcao.SAIDA, texto=texto_plano(m)
        )



async def processar_mensagem(telefone: str, texto: str, nome: str = "", perfil_id=None, registrar: bool = True) -> list[str]:
    resultado = await sync_to_async(_core)(telefone, texto, nome, perfil_id)
    mensagens = resultado["mensagens"]
    pedido_id = resultado.get("checkout_pedido_id")
    if pedido_id:
        from pagamentos.asaas import AsaasError, criar_cobranca_pix
        pedido = await sync_to_async(
            lambda: Pedido.objects.select_related("cliente").get(pk=pedido_id)
        )()
        try:
            dados = await criar_cobranca_pix(pedido)
            from pagamentos.pix_whatsapp import montar_mensagens_pix
            mensagens.extend(montar_mensagens_pix(pedido, dados))
        except AsaasError as exc:
            mensagens.append("Não consegui gerar o Pix agora. Um atendente vai te ajudar. 🙏")
            import logging
            logging.getLogger(__name__).error("Asaas falhou no pedido #%s: %s", pedido_id, exc)
    if registrar:
        await sync_to_async(_registrar_conversa)(telefone, texto, mensagens)
    return normalizar_mensagens(mensagens)