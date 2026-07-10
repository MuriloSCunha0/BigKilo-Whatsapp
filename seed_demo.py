"""
Popula o banco com o cardápio REAL do Big Kilo (PLANILHA CARDAPIO WHATSAPP),
agora organizado em CARDÁPIOS (agendados por dia/período) + itens fixos.

- Itens fixos (todo dia, almoço e jantar) => sempre_disponivel=True.
- Itens que variam (só almoço, só jantar, por dia) => entram em cardápios.

Uso: python seed_demo.py
"""

import os
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from cardapio.models import (  # noqa: E402
    Cardapio, Categoria, DisponibilidadeCardapio, FaixaPreco, Produto,
)
from pedidos.models import (  # noqa: E402
    MENSAGENS_PADRAO, AreaEntrega, Cliente, ConfiguracaoLoja, ItemAcompanhamento, ItemPedido,
    MensagemCliente, MensagemFluxo, Pedido, PerfilFluxo, PromocaoExclusiva,
)

User = get_user_model()

TODOS = [0, 1, 2, 3, 4, 5]  # seg a sáb
A = ["ALMOCO"]
J = ["JANTAR"]


def D(c) -> Decimal:
    return Decimal(str(c))


def criar_admin():
    if not User.objects.filter(username="admin").exists():
        User.objects.create_superuser("admin", "admin@bigkilo.local", "admin123")
        print("Superusuário -> admin / admin123")
    else:
        print("Superusuário 'admin' já existe.")


def criar_config():
    cfg = ConfiguracaoLoja.get()
    cfg.nome_loja = "Big Kilo"
    cfg.slogan = "Comida Caseira"
    cfg.taxa_entrega = D("7.00")
    # Preços arredondados (decisão do cliente, reunião 30/06).
    cfg.completa_300, cfg.completa_500, cfg.completa_700 = D("32"), D("51"), D("70")
    cfg.proteina_300, cfg.proteina_500, cfg.proteina_700, cfg.proteina_1000 = D("42"), D("68"), D("94"), D("133")
    cfg.chave_pix = "bigkilo@exemplo.com.br"
    cfg.dias_funcionamento = TODOS
    cfg.hora_abertura = "11:00"
    cfg.hora_fechamento = "19:30"
    cfg.area_atendimento_texto = "Novo Leblon e arredores (Barra da Tijuca)"
    cfg.save()
    print("Configuração da loja definida.")


def criar_areas():
    for bairro, ini, fim in [
        ("Novo Leblon", "22790-000", "22799-999"),
        ("Barra da Tijuca", "22600-000", "22799-999"),
        ("Recreio dos Bandeirantes", "22790-000", "22795-999"),
    ]:
        AreaEntrega.objects.get_or_create(bairro=bairro, defaults={"cep_inicio": ini, "cep_fim": fim})
    print(f"Áreas de entrega: {AreaEntrega.objects.count()}.")


def cat(nome, tipo, ordem):
    obj, _ = Categoria.objects.get_or_create(nome=nome, defaults={"tipo": tipo, "ordem": ordem})
    return obj


def prod(categoria, nome, modo, preco="0", sempre=False, faixas=None):
    p, _ = Produto.objects.get_or_create(nome=nome, defaults={"categoria": categoria})
    p.categoria = categoria
    p.modo_venda = modo
    p.preco = D(preco)
    p.sempre_disponivel = sempre
    p.save()
    if faixas is not None:
        p.faixas.all().delete()
        for i, (rot, val) in enumerate(faixas):
            FaixaPreco.objects.create(produto=p, rotulo=rot, preco=D(val), ordem=i)
    return p


def card(nome, regras, produtos):
    c, _ = Cardapio.objects.get_or_create(nome=nome)
    c.ativo = True
    c.save()
    c.agenda.all().delete()
    for dias, periodos in regras:
        for dia in dias:
            for per in periodos:
                DisponibilidadeCardapio.objects.create(cardapio=c, dia_semana=dia, periodo=per)
    c.produtos.set(produtos)
    return c


def criar_cardapio():
    c_prot = cat("Proteínas", Categoria.Tipo.PROTEINA, 1)
    c_acomp = cat("Acompanhamentos", Categoria.Tipo.ACOMPANHAMENTO, 2)
    c_grel = cat("Grelhados", Categoria.Tipo.GRELHADO, 3)
    c_esp = cat("Espetinhos", Categoria.Tipo.ESPETINHO, 4)
    c_sand = cat("Sanduíches", Categoria.Tipo.SANDUICHE, 5)
    c_sopa = cat("Sopas", Categoria.Tipo.SOPA, 6)
    c_adic = cat("Adicionais", Categoria.Tipo.ADICIONAL, 7)
    M = Produto.ModoVenda

    # ===== Fixos (sempre disponíveis) =====
    for nome in ["Feijão Preto (sem carne)", "Arroz Branco", "Arroz Integral", "Farofa Crocante",
                 "Salada de Maionese", "Salada Verde (Alface Crespa)", "Tomate", "Legumes Sortidos", "Batata Frita"]:
        prod(c_acomp, nome, M.MONTAGEM, sempre=True)
    prod(c_prot, "Carne Assada", M.MONTAGEM, sempre=True)
    prod(c_prot, 'Frango Ensopado "Caipira"', M.MONTAGEM, sempre=True)
    prod(c_grel, "Bife Acebolado (Coração da Alcatra)", M.FAIXA, sempre=True,
         faixas=[("100g", "16.49"), ("200g", "36.48"), ("300g", "52.97")])
    prod(c_esp, "Espetinho de Coração", M.UNIDADE, preco="17.49", sempre=True)

    # ===== Itens que variam (vão para cardápios) =====
    macarrao = prod(c_acomp, "Macarrão ao alho e óleo", M.MONTAGEM)
    molho_v = prod(c_acomp, "Molho Vermelho", M.MONTAGEM)
    molho_b = prod(c_acomp, "Molho Branco", M.MONTAGEM)
    pure_doce = prod(c_acomp, "Purê de Batata Doce", M.MONTAGEM)
    pure_bat = prod(c_acomp, "Purê de Batata", M.MONTAGEM)
    pure_abo = prod(c_acomp, "Purê de Abóbora", M.MONTAGEM)
    couve = prod(c_acomp, "Couve Mineira", M.MONTAGEM)
    angu = prod(c_acomp, "Angu (Polenta Mole)", M.MONTAGEM)
    quiabo = prod(c_acomp, "Quiabo ao molho Caipira", M.MONTAGEM)

    dobradinha = prod(c_prot, "Dobradinha com Feijão Branco", M.MONTAGEM)
    isca = prod(c_prot, "Isca de Fígado", M.MONTAGEM)
    lombo = prod(c_prot, "Lombo Suíno ao molho madeira", M.MONTAGEM)
    lingua = prod(c_prot, "Língua ao molho Madeira", M.MONTAGEM)
    frango_quiabo = prod(c_prot, "Frango com Quiabo", M.MONTAGEM)
    peixe = prod(c_prot, "Filé de Peixe à Milanesa", M.MONTAGEM)
    bobo = prod(c_prot, "Bobó de Camarão", M.MONTAGEM)
    mocoto = prod(c_prot, "Mocotó com Feijão Branco", M.MONTAGEM)

    sand = [
        prod(c_sand, "Sanduíche de Carne Assada no Pão Francês", M.UNIDADE, preco="20.30"),
        prod(c_sand, "Sanduíche de Carne Assada no Pão Brioche", M.UNIDADE, preco="24.30"),
        prod(c_sand, "Sanduíche de Frango Desfiado no Pão Francês", M.UNIDADE, preco="13.30"),
        prod(c_sand, "Sanduíche de Frango Desfiado no Pão Brioche", M.UNIDADE, preco="17.30"),
    ]
    sopas = [prod(c_sopa, n, M.FAIXA, faixas=[("300ml", "18.00"), ("500ml", "25.00")])
             for n in ["Caldo Verde", "Sopa de Ervilha", "Caldo de Abóbora", "Feijão Amigo",
                       "Sopa de Legumes com Carne", "Sopa de Legumes com Frango"]]
    adic = [prod(c_adic, n, M.ADICIONAL, preco=p)
            for n, p in [("Cheddar", "3.00"), ("Mussarela", "3.00"), ("Alface e Tomate", "3.00"),
                         ("Batata Palha", "2.00"), ("Molho Barbecue", "2.00"),
                         ("Calabresa (sopa)", "2.00"), ("Bacon (sopa)", "2.00"), ("Torradas (sopa)", "4.00")]]

    # Exemplo de carne premium com preço/kg próprio
    Produto.objects.filter(nome="Bobó de Camarão").update(preco_kg=D("169.00"))

    # ===== Cardápios =====
    card("Almoço diário", [(TODOS, A)], [macarrao, molho_v, molho_b])
    card("Jantar diário", [(TODOS, J)], sand + sopas + adic)
    card("Segunda - Almoço", [([0], A)], [dobradinha, pure_doce])
    card("Segunda - Jantar", [([0], J)], [dobradinha])
    card("Terça - Almoço", [([1], A)], [isca, pure_bat])
    card("Quarta - Almoço", [([2], A)], [lombo, pure_abo, couve])
    card("Quinta - Almoço", [([3], A)], [lingua, frango_quiabo, quiabo, pure_bat])
    card("Quinta - Jantar", [([3], J)], [frango_quiabo, quiabo])
    card("Sexta - Almoço", [([4], A)], [peixe, bobo, angu])
    card("Sexta - Jantar", [([4], J)], [bobo, angu])
    card("Sábado - Almoço", [([5], A)], [lombo, mocoto])
    card("Sábado - Jantar", [([5], J)], [mocoto])

    # Exemplo de cardápio ESPECIAL (Dia das Mães) — exclusivo, por data.
    carne = Produto.objects.get(nome="Carne Assada")
    esp, _ = Cardapio.objects.get_or_create(nome="Dia das Mães")
    esp.tipo = Cardapio.Tipo.ESPECIAL
    esp.exclusivo = True
    esp.ativo = True
    esp.data_inicio = "2026-05-10"
    esp.data_fim = "2026-05-10"
    esp.save()
    esp.agenda.all().delete()
    esp.produtos.set([carne, bobo, mocoto])

    print(f"Cardápio: {Produto.objects.count()} produtos, {Cardapio.objects.count()} cardápios.")


def criar_pedidos_exemplo():
    if Pedido.objects.exists():
        print("Pedidos de exemplo já existem (pulando).")
        return
    cfg = ConfiguracaoLoja.get()
    c1, _ = Cliente.objects.get_or_create(telefone="5521988887777", defaults={"nome_whatsapp": "Maria Souza"})
    c2, _ = Cliente.objects.get_or_create(telefone="5521977776666", defaults={"nome_whatsapp": "João Pereira"})
    c3, _ = Cliente.objects.get_or_create(telefone="5521966665555", defaults={"nome_whatsapp": "Ana Lima"})

    carne = Produto.objects.get(nome="Carne Assada")
    frango = Produto.objects.get(nome='Frango Ensopado "Caipira"')
    arroz = Produto.objects.get(nome="Arroz Branco")
    feijao = Produto.objects.get(nome="Feijão Preto (sem carne)")
    farofa = Produto.objects.get(nome="Farofa Crocante")

    p1 = Pedido.objects.create(
        cliente=c1, status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        endereco_entrega="Rua Mário Agostinelli 100, ap 502", bairro="Novo Leblon",
        cep="22790-100", taxa_entrega=cfg.taxa_entrega, asaas_cobranca_id="pay_demo_001",
        asaas_pix_copia_cola="00020126...EXEMPLO-PIX...6304ABCD",
    )
    it = ItemPedido.objects.create(pedido=p1, modo=ItemPedido.Modo.COMPLETA, produto=carne,
                                   peso_g=500, preco_unitario=cfg.preco_completa(500))
    for ac in [arroz, feijao, farofa]:
        ItemAcompanhamento.objects.create(item_pedido=it, produto=ac, preco_adicional=ac.preco)
    p1.recalcular_total(); p1.save(update_fields=["valor_total"])

    p2 = Pedido.objects.create(
        cliente=c2, status=Pedido.Status.CONCLUIDO,
        endereco_entrega="Av. das Américas 7707, loja 105", bairro="Barra da Tijuca",
        cep="22640-101", taxa_entrega=cfg.taxa_entrega, asaas_cobranca_id="pay_demo_002",
    )
    ItemPedido.objects.create(pedido=p2, modo=ItemPedido.Modo.PROTEINA, produto=frango,
                              peso_g=700, preco_unitario=cfg.preco_proteina(700), observacoes="bem passado")
    p2.recalcular_total(); p2.save(update_fields=["valor_total"])

    bife = Produto.objects.get(nome="Bife Acebolado (Coração da Alcatra)")
    faixa = bife.faixas.get(rotulo="200g")
    p3 = Pedido.objects.create(
        cliente=c3, status=Pedido.Status.CONCLUIDO, endereco_entrega="Rua do Novo Leblon 50",
        bairro="Novo Leblon", cep="22790-050", taxa_entrega=cfg.taxa_entrega, comanda_impressa=True,
    )
    ItemPedido.objects.create(pedido=p3, modo=ItemPedido.Modo.FIXO, produto=bife,
                              variacao="200g", preco_unitario=faixa.preco)
    p3.recalcular_total(); p3.save(update_fields=["valor_total"])
    print("Pedidos de exemplo criados (3).")


def criar_mensagens():
    perfil, _ = PerfilFluxo.objects.get_or_create(nome="Padrão")
    perfil.ativo = True
    perfil.save()
    for chave, texto in MENSAGENS_PADRAO.items():
        MensagemFluxo.objects.get_or_create(perfil=perfil, chave=chave, defaults={"texto": texto})
    print(f"Fluxo '{perfil.nome}' ativo com {perfil.mensagens.count()} mensagens.")


def criar_personalizacao_exemplo():
    maria = Cliente.objects.filter(telefone="5521988887777").first()
    if not maria:
        return
    MensagemCliente.objects.get_or_create(
        cliente=maria, chave="BOAS_VINDAS",
        defaults={"texto": "Oi, Maria! 💛 Que bom te ver de novo no Big Kilo!"},
    )
    sand = Produto.objects.filter(nome="Sanduíche de Carne Assada no Pão Brioche").first()
    if sand:
        PromocaoExclusiva.objects.get_or_create(
            cliente=maria, produto=sand,
            defaults={"desconto_percentual": D("20.00"),
                      "mensagem": "🎁 Pra você, Maria: 20% no sanduíche de brioche hoje!"},
        )
    print("Personalização de exemplo: contato Maria (saudação + promo exclusiva).")


if __name__ == "__main__":
    criar_admin()
    criar_config()
    criar_areas()
    criar_cardapio()
    criar_mensagens()
    criar_pedidos_exemplo()
    criar_personalizacao_exemplo()
    print("\nSeed concluído. Acesse http://127.0.0.1:8000/admin/")
