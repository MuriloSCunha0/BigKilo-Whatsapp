"""Assistente (wizard) de cadastro de produto em passos."""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import Cardapio, Categoria, DisponibilidadeCardapio, FaixaPreco, PeriodoChoices, Produto


def _dec(valor) -> Decimal:
    try:
        return Decimal(str(valor).replace(",", ".").strip() or "0")
    except (InvalidOperation, AttributeError):
        return Decimal("0")


def _parse_data(valor):
    """Converte 'YYYY-MM-DD' em datetime aware (início do dia) ou None."""
    if not valor:
        return None
    try:
        d = datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
        return timezone.make_aware(datetime.combine(d, datetime.min.time()))
    except (ValueError, TypeError):
        return None


def _data_iso(dt):
    if not dt:
        return ""
    return timezone.localtime(dt).strftime("%Y-%m-%d")


@staff_member_required
def wizard(request):
    contexto = {
        "categorias": Categoria.objects.filter(ativa=True),
        "modos": Produto.ModoVenda.choices,
    }
    return render(request, "produto_wizard.html", contexto)


@staff_member_required
def wizard_carregar(request, produto_id):
    try:
        p = Produto.objects.prefetch_related("faixas", "cardapios").select_related("categoria").get(id=produto_id)
    except Produto.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Produto não encontrado."}, status=404)
    return JsonResponse({
        "ok": True,
        "produto": {
            "id": p.id,
            "categoria_id": p.categoria_id,
            "nome": p.nome,
            "descricao": p.descricao,
            "modo_venda": p.modo_venda,
            "preco": str(p.preco).replace(".", ","),
            "preco_kg": str(p.preco_kg).replace(".", ",") if p.preco_kg else "",
            "sempre_disponivel": p.sempre_disponivel,
            "horario_inicio": p.horario_inicio.strftime("%H:%M") if p.horario_inicio else None,
            "horario_fim": p.horario_fim.strftime("%H:%M") if p.horario_fim else None,
            "faixas": [{"rotulo": f.rotulo, "preco": str(f.preco).replace(".", ",")} for f in p.faixas.all()],
            "cardapios": list(p.cardapios.values_list("id", flat=True)),
        },
    })


@staff_member_required
def wizard_salvar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)

    dados = json.loads(request.body or b"{}")
    produto_id = dados.get("produto_id")
    nome = (dados.get("nome") or "").strip()
    cat_id = dados.get("categoria_id")
    if not nome or not cat_id:
        return JsonResponse({"ok": False, "erro": "Informe a categoria e o nome do produto."})

    try:
        categoria = Categoria.objects.get(id=cat_id)
    except Categoria.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Categoria inválida."})

    modo = dados.get("modo_venda") or Produto.ModoVenda.UNIDADE
    
    from datetime import datetime
    
    h_inicio = None
    if dados.get("horario_inicio"):
        try:
            h_inicio = datetime.strptime(dados["horario_inicio"], "%H:%M").time()
        except ValueError:
            pass
            
    h_fim = None
    if dados.get("horario_fim"):
        try:
            h_fim = datetime.strptime(dados["horario_fim"], "%H:%M").time()
        except ValueError:
            pass

    if produto_id:
        try:
            produto = Produto.objects.get(id=produto_id)
        except Produto.DoesNotExist:
            return JsonResponse({"ok": False, "erro": "Produto não encontrado."})
        produto.categoria = categoria
        produto.nome = nome
        produto.descricao = (dados.get("descricao") or "").strip()
        produto.modo_venda = modo
        produto.preco = _dec(dados.get("preco"))
        produto.preco_kg = _dec(dados.get("preco_kg"))
        produto.sempre_disponivel = bool(dados.get("sempre_disponivel"))
        produto.horario_inicio = h_inicio
        produto.horario_fim = h_fim
        produto.save()
        produto.faixas.all().delete()
    else:
        produto = Produto.objects.create(
            categoria=categoria,
            nome=nome,
            descricao=(dados.get("descricao") or "").strip(),
            modo_venda=modo,
            preco=_dec(dados.get("preco")),
            preco_kg=_dec(dados.get("preco_kg")),
            sempre_disponivel=bool(dados.get("sempre_disponivel")),
            horario_inicio=h_inicio,
            horario_fim=h_fim,
        )

    if modo == Produto.ModoVenda.FAIXA:
        for i, f in enumerate(dados.get("faixas", [])):
            rotulo = (f.get("rotulo") or "").strip()
            if rotulo:
                FaixaPreco.objects.create(produto=produto, rotulo=rotulo, preco=_dec(f.get("preco")), ordem=i)

    # Se não for "sempre disponível", vincula aos cardápios escolhidos.
    if not produto.sempre_disponivel:
        ids = [c for c in dados.get("cardapios", []) if str(c).isdigit()]
        produto.cardapios.set(Cardapio.objects.filter(id__in=ids))
    else:
        produto.cardapios.clear()

    return JsonResponse({
        "ok": True,
        "produto": produto.id,
        "redirect": reverse("admin:cardapio_produto_changelist"),
    })


@staff_member_required
def categoria_carregar(request, categoria_id):
    try:
        c = Categoria.objects.get(id=categoria_id)
    except Categoria.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Categoria não encontrada."}, status=404)
    return JsonResponse({
        "ok": True,
        "categoria": {
            "id": c.id,
            "nome": c.nome,
            "tipo": c.tipo,
            "ordem": c.ordem,
            "ativa": c.ativa,
        },
    })


@staff_member_required
def categoria_salvar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    dados = json.loads(request.body or b"{}")
    categoria_id = dados.get("categoria_id")
    nome = (dados.get("nome") or "").strip()
    tipo = dados.get("tipo")
    if not nome or not tipo:
        return JsonResponse({"ok": False, "erro": "Informe o nome e o tipo."})
    if tipo not in dict(Categoria.Tipo.choices):
        return JsonResponse({"ok": False, "erro": "Tipo inválido."})
    try:
        ordem = int(dados.get("ordem") or 0)
    except (ValueError, TypeError):
        ordem = 0

    if categoria_id:
        try:
            cat = Categoria.objects.get(id=categoria_id)
        except Categoria.DoesNotExist:
            return JsonResponse({"ok": False, "erro": "Categoria não encontrada."})
        cat.nome = nome
        cat.tipo = tipo
        cat.ordem = ordem
        cat.ativa = bool(dados.get("ativa", True))
        cat.save()
    else:
        Categoria.objects.create(nome=nome, tipo=tipo, ordem=ordem, ativa=bool(dados.get("ativa", True)))
    return JsonResponse({"ok": True})


@staff_member_required
def cardapio_carregar(request, cardapio_id):
    try:
        c = Cardapio.objects.prefetch_related("agenda", "produtos").get(id=cardapio_id)
    except Cardapio.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Cardápio não encontrado."}, status=404)

    grade, custom = [], []
    for row in c.agenda.all():
        if row.periodo in (PeriodoChoices.ALMOCO, PeriodoChoices.JANTAR):
            grade.append({"dia": row.dia_semana, "periodo": row.periodo})
        else:
            custom.append({
                "dia": row.dia_semana,
                "hora_inicio": row.hora_inicio.strftime("%H:%M") if row.hora_inicio else "11:00",
                "hora_fim": row.hora_fim.strftime("%H:%M") if row.hora_fim else "14:00",
            })

    return JsonResponse({
        "ok": True,
        "cardapio": {
            "id": c.id,
            "nome": c.nome,
            "tipo": c.tipo,
            "ativo": c.ativo,
            "exclusivo": c.exclusivo,
            "data_inicio": c.data_inicio.isoformat() if c.data_inicio else "",
            "data_fim": c.data_fim.isoformat() if c.data_fim else "",
            "grade": grade,
            "custom": custom,
            "produtos": list(c.produtos.values_list("id", flat=True)),
        },
    })


@staff_member_required
def cardapio_salvar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    dados = json.loads(request.body or b"{}")
    cardapio_id = dados.get("cardapio_id")
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"ok": False, "erro": "Informe o nome do cardápio."})

    tipo = dados.get("tipo") or Cardapio.Tipo.NORMAL
    if tipo == Cardapio.Tipo.ESPECIAL and not dados.get("data_inicio"):
        return JsonResponse({"ok": False, "erro": "Para cardápio Especial, informe a data inicial."})

    campos = {
        "nome": nome,
        "tipo": tipo,
        "ativo": bool(dados.get("ativo", True)),
        "exclusivo": bool(dados.get("exclusivo")),
        "data_inicio": dados.get("data_inicio") or None,
        "data_fim": dados.get("data_fim") or None,
    }

    if cardapio_id:
        try:
            cardapio = Cardapio.objects.get(id=cardapio_id)
        except Cardapio.DoesNotExist:
            return JsonResponse({"ok": False, "erro": "Cardápio não encontrado."})
        for k, v in campos.items():
            setattr(cardapio, k, v)
        cardapio.save()
        cardapio.agenda.all().delete()
    else:
        cardapio = Cardapio.objects.create(**campos)

    if tipo == Cardapio.Tipo.NORMAL:
        for r in dados.get("agenda", []):
            try:
                periodo = r["periodo"]
                campos_ag = {"cardapio": cardapio, "dia_semana": int(r["dia"]), "periodo": periodo}
                if periodo == "CUSTOM":
                    campos_ag["hora_inicio"] = r.get("hora_inicio") or "00:00"
                    campos_ag["hora_fim"] = r.get("hora_fim") or "23:59"
                DisponibilidadeCardapio.objects.create(**campos_ag)
            except (KeyError, ValueError, TypeError):
                continue

    ids = [i for i in dados.get("produtos", []) if str(i).isdigit()]
    cardapio.produtos.set(Produto.objects.filter(id__in=ids))
    return JsonResponse({"ok": True})


@staff_member_required
def promocao_carregar(request, produto_id):
    try:
        p = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Produto não encontrado."}, status=404)
    return JsonResponse({
        "ok": True,
        "promocao": {
            "produto_id": p.id,
            "produto_nome": p.nome,
            "desconto": str(p.desconto_percentual).replace(".", ",").rstrip("0").rstrip(",") or "0",
            "data_inicio": _data_iso(p.promo_inicio),
            "data_fim": _data_iso(p.promo_fim),
        },
    })


@staff_member_required
def promocao_salvar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido."}, status=405)
    dados = json.loads(request.body or b"{}")
    produto_id = dados.get("produto_id")
    desconto = _dec(dados.get("desconto"))
    if not produto_id:
        return JsonResponse({"ok": False, "erro": "Escolha o produto."})
    if desconto <= 0 or desconto > 100:
        return JsonResponse({"ok": False, "erro": "Informe um desconto entre 1 e 100%."})
    try:
        produto = Produto.objects.get(id=produto_id)
    except Produto.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Produto inválido."})
    produto.desconto_percentual = desconto
    produto.promo_inicio = _parse_data(dados.get("data_inicio"))
    produto.promo_fim = _parse_data(dados.get("data_fim"))
    produto.save(update_fields=["desconto_percentual", "promo_inicio", "promo_fim"])
    return JsonResponse({"ok": True})
