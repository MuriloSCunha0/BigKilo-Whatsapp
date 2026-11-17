"""Encomendas de Natal e Ano Novo pelo WhatsApp.

Do jeito que o Leandro descreveu (15/11/2026):
- o cliente toca em "Natal e Ano Novo", recebe a arte com o cardápio e escolhe
  categoria → item → quantidade; depois de cada item pode adicionar, corrigir ou
  finalizar;
- no fim escolhe a data e o horário da retirada na loja, vê o resumo e paga só o
  sinal (Pix aqui mesmo ou na loja até o prazo). O valor total NÃO aparece: os
  itens são pesados depois de prontos, então qualquer total seria chute.

O cardápio vem da arte que o restaurante mandou. Ele é sazonal e fixo, por isso
mora aqui e não no cadastro de produtos (que alimenta o cardápio do dia, a cozinha
e as comandas — misturar a Ceia lá faria o Lombo de Natal aparecer no almoço).
"""

import re
from datetime import date
from decimal import Decimal

from django.utils import timezone

from bot.mensagens import ID_MAIS, ID_VOLTAR, LINHA_VOLTAR, T, botoes, imagem, lista, lista_paginada

PESO_GRANDE = [("700", "700g"), ("1000", "1kg"), ("1500", "1,5kg"), ("2000", "2kg")]
PESO = [("500", "500g"), ("700", "700g"), ("1000", "1kg")]
UNIDADE = [("1", "1 unidade"), ("2", "2 unidades"), ("3", "3 unidades")]


def _i(id_, nome, curto=None, preco=None, medida=None, cada=""):
    return {"id": id_, "nome": nome, "curto": curto or nome, "preco": preco,
            "medida": medida, "cada": cada}


CATEGORIAS = [
    {"id": "pratos", "titulo": "🍖 Pratos principais", "preco": "15.90", "medida": PESO_GRANDE,
     "itens": [
         _i("lombo_abacaxi", "Lombo ao Molho de Abacaxi", "Lombo molho de abacaxi"),
         _i("lombo_ervas", "Lombo ao Molho de Ervas", "Lombo molho de ervas"),
         _i("lombo_madeira", "Lombo ao Molho Madeira", "Lombo molho madeira"),
         _i("chester", "Chester à Califórnia", medida=UNIDADE, cada="3kg"),
         _i("maminha", "Maminha Recheada com Calabresa", "Maminha c/ calabresa"),
         _i("carne_assada", "Carne Assada"),
         _i("bobo", "Bobó de Camarão"),
     ]},
    {"id": "guarnicoes", "titulo": "🥗 Guarnições", "preco": "9.89", "medida": PESO,
     "itens": [
         _i("salpicao", "Salpicão de Frango"),
         _i("macarronese", "Macarronese"),
         _i("maionese", "Salada de Maionese"),
         _i("berinjela", "Berinjela no Shoyo"),
         _i("arroz_grega", "Arroz à Grega"),
         _i("arroz_lentilha", "Arroz com Lentilha"),
         _i("farofa_ovos", "Farofa de Ovos"),
         _i("farofa_crocante", "Farofa Crocante"),
         _i("creme_milho", "Creme de Milho"),
         _i("pure_batata", "Purê de Batata"),
         _i("pure_abobora", "Purê de Abóbora"),
         _i("pure_batata_doce", "Purê de Batata Doce"),
     ]},
    {"id": "massas", "titulo": "🥧 Massas e tortas", "preco": "11.90", "medida": UNIDADE, "cada": "1kg",
     "itens": [
         _i("lasanha_frango", "Lasanha de Frango"),
         _i("lasanha_carne", "Lasanha de Carne Desfiada", "Lasanha carne desfiada"),
         _i("escondidinho_carne", "Escondidinho de Carne"),
         _i("escondidinho_frango", "Escondidinho de Frango"),
         _i("empadao_frango", "Empadão de Frango"),
         _i("empadao_camarao", "Empadão de Camarão", preco="15.90"),
         _i("arroz_forno", "Arroz de Forno"),
         _i("batata_gratinada", "Batata Gratinada"),
         _i("quiche_alho_poro", "Quiche de Alho Poró"),
         _i("quiche_cebola", "Quiche de Cebola"),
     ]},
    {"id": "bacalhau", "titulo": "🐟 Bolinho de bacalhau", "preco": "11.90", "medida": PESO,
     "itens": [_i("bolinho_bacalhau", "Bolinho de Bacalhau")]},
    {"id": "camarao", "titulo": "🍤 Camarão empanado", "preco": "11.90", "medida": PESO,
     "itens": [_i("camarao_empanado", "Camarão Empanado")]},
    {"id": "rabanada", "titulo": "🍞 Rabanada", "preco": "9.89", "medida": PESO,
     "itens": [_i("rabanada", "Rabanada")]},
]

ERRO = "Não entendi 🙂 Toque numa das opções abaixo."
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# ids dos botões que valem em qualquer etapa da encomenda
B_CATEGORIAS = "ceia_cats"
B_CORRIGIR = "ceia_corrigir"
B_FINALIZAR = "ceia_fim"
B_PIX = "ceia_pix"
B_LOJA = "ceia_loja"
B_DATA_LISTA = "ceia_datas"


# ===================== consulta ao cardápio =====================
def _categoria(cid):
    return next((c for c in CATEGORIAS if c["id"] == cid), None)


def _item(iid):
    for cat in CATEGORIAS:
        for it in cat["itens"]:
            if it["id"] == iid:
                return cat, it
    return None, None


def _medida(cat, it):
    return it["medida"] or cat["medida"]


def _preco(cat, it) -> str:
    return it["preco"] or cat["preco"]


def _cada(cat, it) -> str:
    return it["cada"] or cat.get("cada", "")


def _preco_txt(valor) -> str:
    return f"R$ {Decimal(valor):.2f}".replace(".", ",") + "/100g"


def _moeda(valor) -> str:
    return f"R$ {Decimal(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha_item(it: dict) -> str:
    """• Lombo ao Molho de Abacaxi — 1kg  /  • Chester à Califórnia — 2 unidades (cerca de 3kg cada)"""
    extra = f" (cerca de {it['cada']} cada)" if it.get("cada") else ""
    return f"• {it['nome']} — {it['rotulo']}{extra}"


# ===================== estado da conversa =====================
def _c(sessao) -> dict:
    return sessao.carrinho_json.setdefault("ceia", {"itens": []})


def _menu(sessao, mapa: dict):
    sessao.carrinho_json["_menu"] = {str(k): v for k, v in mapa.items()}


def _toque(sessao, texto: str):
    return (sessao.carrinho_json.get("_menu") or {}).get((texto or "").strip())


# ===================== telas =====================
def iniciar(sessao, foto=None) -> list:
    from pedidos.models import SessaoBot

    sessao.estado_atual = SessaoBot.Estado.CEIA
    sessao.carrinho_json["ceia"] = {"itens": []}
    msgs = [imagem(foto)] if foto else []
    return msgs + tela_categorias(sessao, corpo=(
        "🎄 Esse é o nosso cardápio de *Natal e Ano Novo*! Também fazemos por encomenda "
        "qualquer item do nosso buffet.\n\nEscolha uma categoria para montar sua encomenda:"))


def tela_categorias(sessao, corpo: str = "", aviso: str = "") -> list:
    c = _c(sessao)
    c["etapa"], c["pag"] = "categoria", 0
    itens = c.get("itens") or []
    linhas, mapa = [], {}
    for cat in CATEGORIAS:
        unico = len(cat["itens"]) == 1
        desc = _preco_txt(cat["preco"]) + ("" if unico else f" · {len(cat['itens'])} opções")
        linhas.append({"id": cat["id"], "titulo": cat["titulo"], "descricao": desc})
        mapa[cat["id"]] = cat["id"]
    if itens:
        linhas.append({"id": B_FINALIZAR, "titulo": "✅ Finalizar encomenda",
                       "descricao": f"{len(itens)} item(ns) escolhido(s)"})
        linhas.append({"id": B_CORRIGIR, "titulo": "✏️ Corrigir itens", "descricao": "Tirar algum item"})
    linhas.append(dict(LINHA_VOLTAR, descricao="Sai da encomenda de Natal"))
    _menu(sessao, mapa)
    corpo = corpo or ("Escolha uma categoria para adicionar à sua encomenda:" if itens
                      else "Escolha uma categoria para montar sua encomenda:")
    if aviso:
        corpo = f"{aviso}\n\n{corpo}"
    return [lista(corpo, "Ver categorias", linhas)]


def tela_itens(sessao, cat) -> list:
    if len(cat["itens"]) == 1:
        return tela_qtd(sessao, cat, cat["itens"][0])
    c = _c(sessao)
    c["etapa"], c["cat"] = "item", cat["id"]
    linhas, mapa = [], {}
    for it in cat["itens"]:
        partes = [it["nome"]] if it["curto"] != it["nome"] else []
        partes.append(_preco_txt(_preco(cat, it)))
        linhas.append({"id": f"ci:{it['id']}", "titulo": it["curto"], "descricao": " · ".join(partes)})
        mapa[f"ci:{it['id']}"] = it["id"]
    _menu(sessao, mapa)
    corpo = f"*{cat['titulo']}*\nEscolha o item:"
    nota = cat.get("cada")
    if nota:
        corpo += f"\n_Cada um tem em torno de {nota} e é pesado depois de pronto._"
    return [lista_paginada(corpo, "Ver opções", linhas, int(c.get("pag") or 0),
                           fixas=[{"id": B_CATEGORIAS, "titulo": "↩️ Outras categorias"}])]


def tela_qtd(sessao, cat, it) -> list:
    c = _c(sessao)
    c["etapa"], c["cat"], c["item"] = "qtd", cat["id"], it["id"]
    med = _medida(cat, it)
    unidade = med is UNIDADE
    linhas = [{"id": f"q:{v}", "titulo": t} for v, t in med]
    linhas.append({"id": B_CATEGORIAS, "titulo": "↩️ Outras categorias"})
    _menu(sessao, {f"q:{v}": v for v, _ in med})
    corpo = f"*{it['nome']}* — {_preco_txt(_preco(cat, it))}\n\n"
    cada = _cada(cat, it)
    if unidade and cada:
        if it["id"] == "chester":
            corpo += f"_Cada unidade tem em torno de {cada} e é pesada depois de pronta._\n\n"
        else:
            corpo += f"_Cada item tem em torno de {cada} e é pesado depois de pronto._\n\n"
    corpo += "Quantas unidades?" if unidade else "Qual quantidade você quer?"
    return [lista(corpo, "Escolher quantidade", linhas)]


def tela_depois(sessao, aviso: str) -> list:
    c = _c(sessao)
    c["etapa"] = "depois"
    _menu(sessao, {})
    return [botoes(f"{aviso}\n\nO que você quer fazer agora?", [
        {"id": B_CATEGORIAS, "titulo": "➕ Adicionar itens"},
        {"id": B_CORRIGIR, "titulo": "✏️ Corrigir"},
        {"id": B_FINALIZAR, "titulo": "✅ Finalizar"},
    ])]


def tela_corrigir(sessao, aviso: str = "") -> list:
    c = _c(sessao)
    itens = c.get("itens") or []
    if not itens:
        return tela_categorias(sessao, aviso=aviso or "Sua encomenda está vazia.")
    c["etapa"] = "corrigir"
    linhas, mapa = [], {}
    for n, it in enumerate(itens):
        linhas.append({"id": f"rm:{n}", "titulo": f"❌ {it['curto']}", "descricao": f"Tirar · {it['rotulo']}"})
        mapa[f"rm:{n}"] = n
    _menu(sessao, mapa)
    corpo = (f"{aviso}\n\n" if aviso else "") + "Toque no item para tirar da encomenda:"
    return [lista_paginada(corpo, "Ver itens", linhas, 0, fixas=[
        {"id": B_CATEGORIAS, "titulo": "➕ Adicionar itens"},
        {"id": B_FINALIZAR, "titulo": "✅ Finalizar encomenda"},
    ])]


def _datas_configuradas(cfg) -> list[date]:
    hoje = timezone.localdate()
    datas = []
    for pedaco in (cfg.ceia_datas_retirada or "").split(","):
        d = _ler_data(pedaco)
        if d and d >= hoje and d not in datas:
            datas.append(d)
    return sorted(datas)[:8]


def _ler_data(texto: str):
    """dd/mm (ano opcional) → a próxima data com esse dia/mês, ou None."""
    m = re.search(r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})(?:\s*[/.\-]\s*(\d{2,4}))?", texto or "")
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    hoje = timezone.localdate()
    try:
        if ano:
            ano = int(ano) + (2000 if len(ano) == 2 else 0)
            return date(ano, mes, dia)
        d = date(hoje.year, mes, dia)
        return d if d >= hoje else date(hoje.year + 1, mes, dia)
    except ValueError:
        return None


def _data_txt(d: date) -> str:
    return f"{DIAS[d.weekday()]}, {d:%d/%m}"


def tela_data(sessao, cfg, aviso: str = "") -> list:
    c = _c(sessao)
    datas = _datas_configuradas(cfg)
    if not datas:
        return tela_data_outra(sessao, aviso)
    c["etapa"] = "data"
    linhas = [{"id": f"d:{d.isoformat()}", "titulo": _data_txt(d)} for d in datas]
    linhas.append({"id": "d:outra", "titulo": "📅 Outra data", "descricao": "Digitar o dia"})
    linhas.append({"id": B_CORRIGIR, "titulo": "✏️ Corrigir itens"})
    _menu(sessao, {f"d:{d.isoformat()}": d.isoformat() for d in datas} | {"d:outra": "outra"})
    corpo = (f"{aviso}\n\n" if aviso else "") + "📅 Para qual *data* é a retirada na loja?"
    return [lista(corpo, "Escolher data", linhas)]


def tela_data_outra(sessao, aviso: str = "") -> list:
    c = _c(sessao)
    c["etapa"] = "data_outra"
    _menu(sessao, {})
    corpo = (f"{aviso}\n\n" if aviso else "") + "Digite o *dia da retirada* (dia/mês), por exemplo: 23/12"
    return [botoes(corpo, [{"id": B_DATA_LISTA, "titulo": "📅 Ver datas"},
                           {"id": B_CORRIGIR, "titulo": "✏️ Corrigir itens"}])]


def tela_hora(sessao, cfg) -> list:
    c = _c(sessao)
    c["etapa"] = "hora"
    horas = [h.strip() for h in (cfg.ceia_horarios or "").split(",") if h.strip()] or ["12h"]
    linhas = [{"id": f"h:{h}", "titulo": h} for h in horas[:8]]
    linhas.append({"id": B_DATA_LISTA, "titulo": "📅 Trocar a data"})
    _menu(sessao, {f"h:{h}": h for h in horas[:8]})
    d = date.fromisoformat(c["data"])
    return [lista(f"Retirada em *{_data_txt(d)}*.\n\n🕐 Qual *horário*?", "Escolher horário", linhas)]


def _nome_anterior(sessao) -> str:
    """Nome que a pessoa já digitou numa encomenda anterior (o do perfil do WhatsApp
    não serve: muita gente usa apelido ou frase ali)."""
    from pedidos.models import EncomendaNatal

    enc = (EncomendaNatal.objects.filter(telefone=sessao.telefone, origem=EncomendaNatal.Origem.BOT)
           .exclude(nome="").order_by("-criado_em").first())
    return enc.nome if enc else ""


def tela_nome(sessao, aviso: str = "") -> list:
    c = _c(sessao)
    c["etapa"] = "nome"
    anterior = _nome_anterior(sessao)
    opcoes = []
    mapa = {}
    if anterior and len(anterior) <= 17:
        opcoes.append({"id": "nome:anterior", "titulo": f"✅ {anterior}"})
        mapa["nome:anterior"] = anterior
    opcoes.append({"id": B_CORRIGIR, "titulo": "✏️ Corrigir itens"})
    _menu(sessao, mapa)
    corpo = (f"{aviso}\n\n" if aviso else "") + "👤 Para registrar a encomenda, me diga o seu *nome completo*:"
    if mapa:
        corpo += "\n_Se for o mesmo da última vez, é só tocar no botão._"
    return [botoes(corpo, opcoes)]


def tela_resumo(sessao, cfg) -> list:
    c = _c(sessao)
    c["etapa"] = "resumo"
    _menu(sessao, {})
    d = date.fromisoformat(c["data"])
    prazo = f" até {cfg.ceia_natal_ate:%d/%m}" if cfg.ceia_natal_ate else ""
    corpo = (
        "🎄 *Resumo da sua encomenda*\n\n"
        + (f"👤 {c['nome']}\n\n" if c.get("nome") else "")
        + "\n".join(linha_item(it) for it in c["itens"])
        + f"\n\n🏬 Retirada na loja: *{_data_txt(d)} às {c['hora']}*\n\n"
        "💡 O valor de cada item é calculado pelo peso, depois de pronto.\n\n"
        f"Para confirmar, a encomenda precisa de um *sinal de {_moeda(cfg.ceia_sinal)}*, "
        f"pago por Pix aqui mesmo ou direto na loja{prazo}."
    )
    return [botoes(corpo, [
        {"id": B_PIX, "titulo": "💠 Sinal no Pix"},
        {"id": B_LOJA, "titulo": "🏬 Pagar na loja"},
        {"id": B_CORRIGIR, "titulo": "✏️ Corrigir"},
    ])]


def tela_atual(sessao, cfg) -> list:
    """Repete a tela em que a pessoa estava (depois de uma resposta que não entendemos)."""
    c = _c(sessao)
    etapa = c.get("etapa")
    if etapa == "item" and _categoria(c.get("cat")):
        return tela_itens(sessao, _categoria(c["cat"]))
    if etapa == "qtd":
        cat, it = _item(c.get("item"))
        if it:
            return tela_qtd(sessao, cat, it)
    if etapa == "depois":
        return tela_depois(sessao, "Sua encomenda até agora:\n" + "\n".join(linha_item(i) for i in c["itens"]))
    if etapa == "corrigir":
        return tela_corrigir(sessao)
    if etapa == "data":
        return tela_data(sessao, cfg)
    if etapa == "data_outra":
        return tela_data_outra(sessao)
    if etapa == "hora" and c.get("data"):
        return tela_hora(sessao, cfg)
    if etapa == "nome":
        return tela_nome(sessao)
    if etapa == "resumo" and c.get("data") and c.get("hora"):
        return tela_resumo(sessao, cfg)
    return tela_categorias(sessao)


# ===================== respostas =====================
def tratar(sessao, texto: str, out: dict) -> list:
    """Uma mensagem do cliente no meio da encomenda. Pode marcar out["ceia_sinal_id"]."""
    from pedidos.models import ConfiguracaoLoja

    cfg = ConfiguracaoLoja.get()
    c = _c(sessao)
    alvo = (texto or "").strip()
    etapa = c.get("etapa")

    if alvo == B_CATEGORIAS:
        return tela_categorias(sessao)
    if alvo == B_CORRIGIR:
        return tela_corrigir(sessao)
    if alvo == B_FINALIZAR:
        if not c.get("itens"):
            return tela_categorias(sessao, aviso="Escolha pelo menos um item antes de finalizar 🙂")
        return tela_data(sessao, cfg)
    if alvo == B_DATA_LISTA:
        return tela_data(sessao, cfg)

    if etapa == "categoria":
        cat = _categoria(_toque(sessao, alvo) or "")
        return tela_itens(sessao, cat) if cat else [ERRO] + tela_categorias(sessao)

    if etapa == "item":
        cat = _categoria(c.get("cat"))
        if alvo == ID_MAIS and cat:
            c["pag"] = int(c.get("pag") or 0) + 1
            return tela_itens(sessao, cat)
        _, it = _item(_toque(sessao, alvo) or "")
        return tela_qtd(sessao, cat, it) if it else [ERRO] + tela_atual(sessao, cfg)

    if etapa == "qtd":
        cat, it = _item(c.get("item"))
        qtd = _toque(sessao, alvo)
        rotulo = dict(_medida(cat, it)).get(qtd) if it and qtd else None
        if not rotulo:
            return [ERRO] + tela_atual(sessao, cfg)
        unidade = _medida(cat, it) is UNIDADE
        novo = {"id": it["id"], "nome": it["nome"], "curto": it["curto"], "categoria": cat["id"],
                "qtd": qtd, "rotulo": rotulo, "unidade": unidade,
                "cada": _cada(cat, it) if unidade else "", "preco_100g": _preco(cat, it)}
        c.setdefault("itens", []).append(novo)
        return tela_depois(sessao, f"✅ Adicionado: {linha_item(novo)[2:]}")

    if etapa == "corrigir":
        if alvo == ID_MAIS:
            return tela_corrigir(sessao)
        n = _toque(sessao, alvo)
        if n is None or not (0 <= int(n) < len(c.get("itens") or [])):
            return [ERRO] + tela_corrigir(sessao)
        tirado = c["itens"].pop(int(n))
        return tela_corrigir(sessao, aviso=f"🗑️ {tirado['nome']} saiu da encomenda.")

    if etapa == "data":
        escolha = _toque(sessao, alvo)
        if escolha == "outra":
            return tela_data_outra(sessao)
        if escolha:
            d = date.fromisoformat(escolha)
        else:
            d = _ler_data(alvo)  # digitou a data em vez de tocar
            if not d or d < timezone.localdate():
                return [ERRO] + tela_data(sessao, cfg)
        c["data"] = d.isoformat()
        return tela_hora(sessao, cfg)

    if etapa == "data_outra":
        d = _ler_data(alvo)
        if not d or d < timezone.localdate():
            return tela_data_outra(sessao, aviso="Não entendi a data 🤔")
        c["data"] = d.isoformat()
        return tela_hora(sessao, cfg)

    if etapa == "hora":
        hora = _toque(sessao, alvo)
        if not hora:
            return [ERRO] + tela_hora(sessao, cfg)
        c["hora"] = hora
        return tela_nome(sessao)

    if etapa == "nome":
        nome = _toque(sessao, alvo) or " ".join(alvo.split())
        letras = sum(ch.isalpha() for ch in nome)
        if letras < 2 or re.match(r"^(\d+|[a-z_]+(:[\w,]+)?)$", nome):
            return tela_nome(sessao, aviso="Me diga o seu *nome*, por favor 🙂 (ex.: Maria Silva)")
        c["nome"] = nome[:120]
        return tela_resumo(sessao, cfg)

    if etapa == "resumo":
        if alvo not in (B_PIX, B_LOJA):
            return [ERRO] + tela_resumo(sessao, cfg)
        return _confirmar(sessao, cfg, "PIX" if alvo == B_PIX else "LOJA", out)

    return [ERRO] + tela_atual(sessao, cfg)


def _confirmar(sessao, cfg, forma: str, out: dict) -> list:
    """Grava a encomenda em Encomendas de Natal e Ano Novo e encerra a conversa da Ceia."""
    from pedidos.models import Cliente, EncomendaNatal, SessaoBot

    c = _c(sessao)
    cliente = Cliente.objects.filter(telefone=sessao.telefone).first()
    nome = c.get("nome") or (cliente.nome_whatsapp if cliente else "") or "Cliente do WhatsApp"
    d = date.fromisoformat(c["data"])
    enc = EncomendaNatal.objects.create(
        nome=nome[:120], telefone=sessao.telefone,
        recebe=EncomendaNatal.Recebe.RETIRADA,
        pedido="\n".join(linha_item(it) for it in c["itens"]),
        itens=c["itens"], data_entrega=d, horario=c["hora"],
        status=EncomendaNatal.Status.AGUARDANDO_SINAL, origem=EncomendaNatal.Origem.BOT,
        forma_sinal=forma, sinal_valor=cfg.ceia_sinal,
        # Pagar na loja já é compromisso: imprime agora. No Pix, imprime quando o sinal
        # cair (mesma regra dos pedidos: Pix sem confirmação não vai para a impressora).
        na_fila_impressao=(forma == "LOJA"),
    )
    sessao.carrinho_json.pop("ceia", None)
    sessao.estado_atual = SessaoBot.Estado.MENU_PRINCIPAL
    _menu(sessao, {})
    quando = f"{_data_txt(d)} às {c['hora']}"
    if forma == "PIX":
        out["ceia_sinal_id"] = enc.pk
        return [T(f"🎄 Encomenda nº {enc.pk} registrada!\n\n🏬 Retirada: *{quando}*\n\n"
                  f"Agora é só pagar o sinal de *{_moeda(cfg.ceia_sinal)}* no Pix abaixo 👇 "
                  "Assim que o pagamento cair, a sua encomenda fica reservada.")]
    prazo = f" até {cfg.ceia_natal_ate:%d/%m}" if cfg.ceia_natal_ate else ""
    return [botoes(
        f"🎄 Encomenda nº {enc.pk} registrada!\n\n🏬 Retirada: *{quando}*\n\n"
        f"Para garantir, pague o sinal de *{_moeda(cfg.ceia_sinal)}* direto na loja{prazo}.\n\n"
        "Obrigado pela preferência! 😊",
        [{"id": "ver_menu", "titulo": "🍽️ Ver cardápio"}])]
