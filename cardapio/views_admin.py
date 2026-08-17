import re
import unicodedata
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from cardapio.models import Categoria, Produto, Cardapio

COLUNAS_ESPERADAS = [
    "Categoria",
    "Tipo da Categoria",
    "Produto",
    "Descrição",
    "Modo de Venda",
    "Preço",
    "Preço por KG",
    "Horário Específico",
    "Ativo",
]


def _norm(valor) -> str:
    """Normaliza texto para casar valores: tira acento, maiúsculas, ignora o que vem após '('."""
    s = str(valor or "").strip()
    if "(" in s:
        s = s.split("(")[0]
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split()).upper()


def _mapa_tipo_categoria() -> dict:
    """Aceita tanto o código (PROTEINA) quanto o rótulo amigável (Proteína)."""
    m = {}
    for code, label in Categoria.Tipo.choices:
        m[_norm(code)] = code
        m[_norm(label)] = code
    return m


def _mapa_modo_venda() -> dict:
    m = {}
    for code, label in Produto.ModoVenda.choices:
        m[_norm(code)] = code
        m[_norm(label)] = code
    return m


def _preco_dec(valor) -> Decimal:
    """Converte o preço da planilha em Decimal, tolerante a 'R$', milhar e vírgula.

    Aceita: 6 · 6,00 · 159,90 · "R$ 15,50" · 1.234,56 · 159.9 (float do Excel).
    """
    if valor is None or valor == "":
        return Decimal("0.00")
    if isinstance(valor, (int, float)):
        try:
            return Decimal(str(valor))
        except InvalidOperation:
            return Decimal("0.00")
    s = str(valor).strip()
    # mantém só dígitos, vírgula, ponto e sinal
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s:
        return Decimal("0.00")
    # formato brasileiro "1.234,56" -> tira milhar, vírgula vira ponto
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0.00")


def baixar_planilha_exemplo(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cardápio"

    # Cabeçalho
    for col_num, nome in enumerate(COLUNAS_ESPERADAS, 1):
        cell = ws.cell(row=1, column=col_num, value=nome)
        cell.font = openpyxl.styles.Font(bold=True)
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor="FFEFD5")

    # Larguras
    for letra, larg in zip("ABCDEFGHI", [18, 20, 24, 25, 22, 10, 12, 16, 8]):
        ws.column_dimensions[letra].width = larg

    # Listas suspensas (o usuário escolhe, não digita) — rótulos amigáveis
    tipos = ",".join(label for _, label in Categoria.Tipo.choices)          # Proteína,Acompanhamento,...
    modos = ",".join(label for _, label in Produto.ModoVenda.choices)        # Montagem (por peso),...
    dv_tipo = DataValidation(type="list", formula1=f'"{tipos}"', allow_blank=True)
    dv_modo = DataValidation(type="list", formula1=f'"{modos}"', allow_blank=True)
    dv_ativo = DataValidation(type="list", formula1='"Sim,Não"', allow_blank=True)
    for dv in (dv_tipo, dv_modo, dv_ativo):
        ws.add_data_validation(dv)
    dv_tipo.add("B2:B1000")   # Tipo da Categoria
    dv_modo.add("E2:E1000")   # Modo de Venda
    dv_ativo.add("I2:I1000")  # Ativo

    tipo_label = dict(Categoria.Tipo.choices)
    modo_label = dict(Produto.ModoVenda.choices)

    def _preco(v):
        return (f"{v:.2f}".replace(".", ",")) if v else "0"

    # Pré-preenche com os produtos REAIS já cadastrados (o lojista só ajusta/apaga).
    produtos = Produto.objects.select_related("categoria").order_by("categoria__nome", "nome")
    linha = 2
    for p in produtos:
        horario = ""
        if p.horario_inicio and p.horario_fim:
            horario = f"{p.horario_inicio:%H:%M}-{p.horario_fim:%H:%M}"
        vals = [
            p.categoria.nome if p.categoria_id else "",
            tipo_label.get(p.categoria.tipo, "") if p.categoria_id else "",
            p.nome,
            p.descricao or "",
            modo_label.get(p.modo_venda, ""),
            _preco(p.preco),
            _preco(p.preco_kg),
            horario,
            "Sim" if p.ativo else "Não",
        ]
        for col_num, val in enumerate(vals, 1):
            ws.cell(row=linha, column=col_num, value=val)
        linha += 1

    # Catálogo vazio: mostra exemplos amigáveis para o usuário se guiar.
    if linha == 2:
        exemplos = [
            ["Proteínas", "Proteína", "Frango grelhado", "Ao alho e óleo", "Montagem (por peso)", "0", "0", "", "Sim"],
            ["Acompanhamentos", "Acompanhamento", "Farofa da casa", "", "Montagem (por peso)", "0", "0", "", "Sim"],
            ["Bebidas", "Bebida", "Coca-Cola lata", "Gelada", "Unidade (preço fixo)", "6,00", "0", "", "Sim"],
            ["Sopas", "Sopa", "Caldo verde", "", "Unidade (preço fixo)", "15,00", "0", "18:00-23:00", "Sim"],
        ]
        for i, ex in enumerate(exemplos, start=2):
            for col_num, val in enumerate(ex, 1):
                ws.cell(row=i, column=col_num, value=val)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="modelo_cardapio_bigkilo.xlsx"'
    wb.save(response)
    return response


@require_http_methods(["GET", "POST"])
def importar_planilha_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get("planilha")
        nome_cardapio = request.POST.get("nome_cardapio", "").strip()
        exclusivo = request.POST.get("exclusivo") == "on"

        if not nome_cardapio:
            messages.error(request, "Informe o nome do novo cardápio.")
            return redirect("admin:cardapio_cardapio_changelist")

        if not arquivo:
            messages.error(request, "Nenhum arquivo enviado.")
            return redirect("admin:cardapio_cardapio_changelist")

        if not arquivo.name.lower().endswith(".xlsx"):
            messages.error(request, "O arquivo deve ser um Excel (.xlsx).")
            return redirect("admin:cardapio_cardapio_changelist")

        from datetime import datetime

        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active

            # Valida cabeçalho
            header = [str(cell.value).strip() if cell.value else "" for cell in ws[1]]

            if "Produto" not in header or "Categoria" not in header:
                messages.error(
                    request,
                    "A planilha não possui as colunas 'Produto' e 'Categoria'. "
                    "Use a planilha de exemplo.",
                )
                return redirect("admin:cardapio_cardapio_importar_planilha")

            idx_cat = header.index("Categoria")
            idx_tipo = header.index("Tipo da Categoria") if "Tipo da Categoria" in header else -1
            idx_prod = header.index("Produto")
            idx_desc = header.index("Descrição") if "Descrição" in header else -1
            idx_modo = header.index("Modo de Venda") if "Modo de Venda" in header else -1
            idx_preco = header.index("Preço") if "Preço" in header else -1
            idx_kg = header.index("Preço por KG") if "Preço por KG" in header else -1
            idx_ativo = header.index("Ativo") if "Ativo" in header else -1
            idx_horario = header.index("Horário Específico") if "Horário Específico" in header else -1

            tipo_cardapio = request.POST.get("tipo_cardapio", "NORMAL")
            mapa_tipo = _mapa_tipo_categoria()
            mapa_modo = _mapa_modo_venda()

            def _cel(row, idx):
                """Lê a célula com segurança (índice pode faltar ou linha ser curta)."""
                if idx < 0 or len(row) <= idx:
                    return None
                return row[idx]

            # Tudo dentro de UMA transação: se algo falhar no meio, NADA é gravado
            # (evita deixar cardápios órfãos/vazios no banco em caso de erro).
            with transaction.atomic():
                # 1. Criar o Cardápio
                cardapio_obj = Cardapio.objects.create(
                    nome=nome_cardapio,
                    tipo=tipo_cardapio,
                    exclusivo=exclusivo,
                    ativo=True,
                )

                qtd_dias = 0
                # Aplicar horários ou datas
                if tipo_cardapio == "ESPECIAL":
                    d_inicio = request.POST.get("data_inicio")
                    d_fim = request.POST.get("data_fim")
                    if d_inicio:
                        cardapio_obj.data_inicio = d_inicio
                    if d_fim:
                        cardapio_obj.data_fim = d_fim
                    cardapio_obj.save()
                else:
                    from cardapio.models import DisponibilidadeCardapio
                    dias = request.POST.getlist("dias")
                    periodo = request.POST.get("periodo", "ALMOCO")
                    for dia in dias:
                        if periodo == "DIA_INTEIRO":
                            DisponibilidadeCardapio.objects.create(cardapio=cardapio_obj, dia_semana=int(dia), periodo="ALMOCO")
                            DisponibilidadeCardapio.objects.create(cardapio=cardapio_obj, dia_semana=int(dia), periodo="JANTAR")
                        else:
                            DisponibilidadeCardapio.objects.create(
                                cardapio=cardapio_obj,
                                dia_semana=int(dia),
                                periodo=periodo,
                            )
                        qtd_dias += 1

                criados = 0
                existentes = 0

                for row in ws.iter_rows(min_row=2, values_only=True):
                    raw_prod = str(_cel(row, idx_prod)) if _cel(row, idx_prod) else ""
                    raw_cat = str(_cel(row, idx_cat)) if _cel(row, idx_cat) else ""

                    # Normalização: tira espaços sobrando no começo/fim e reduz espaços duplos
                    nome_prod = re.sub(r"\s+", " ", raw_prod.strip())
                    nome_cat = re.sub(r"\s+", " ", raw_cat.strip())

                    if not nome_prod or not nome_cat or nome_prod == "None" or nome_cat == "None":
                        continue

                    # 2. Categoria — aceita código (PROTEINA) OU rótulo amigável (Proteína / proteina)
                    tipo_cat = "OUTRO"
                    if _cel(row, idx_tipo):
                        tipo_cat = mapa_tipo.get(_norm(_cel(row, idx_tipo)), "OUTRO")

                    categoria = Categoria.objects.filter(nome__iexact=nome_cat).first()
                    if not categoria:
                        categoria = Categoria.objects.create(nome=nome_cat, tipo=tipo_cat)

                    # Horário específico ("HH:MM-HH:MM")
                    h_inicio = None
                    h_fim = None
                    if _cel(row, idx_horario):
                        horario_str = str(_cel(row, idx_horario)).strip()
                        if "-" in horario_str:
                            partes = horario_str.split("-")
                            try:
                                h_inicio = datetime.strptime(partes[0].strip(), "%H:%M").time()
                                h_fim = datetime.strptime(partes[1].strip(), "%H:%M").time()
                            except ValueError:
                                pass  # ignora formato inválido

                    # 3. Produto — se já existe (ignorando case), apenas vincula; senão cria
                    produto = Produto.objects.filter(nome__iexact=nome_prod).first()
                    if produto:
                        if h_inicio and h_fim:
                            produto.horario_inicio = h_inicio
                            produto.horario_fim = h_fim
                            produto.save(update_fields=["horario_inicio", "horario_fim"])
                        existentes += 1
                    else:
                        desc = ""
                        if _cel(row, idx_desc) and _cel(row, idx_desc) != "None":
                            desc = str(_cel(row, idx_desc)).strip()
                        modo = "UNIDADE"
                        if _cel(row, idx_modo) and _cel(row, idx_modo) != "None":
                            modo = mapa_modo.get(_norm(_cel(row, idx_modo)), "UNIDADE")

                        preco = _preco_dec(_cel(row, idx_preco))
                        preco_kg = _preco_dec(_cel(row, idx_kg))

                        ativo = True
                        if _cel(row, idx_ativo) and _norm(_cel(row, idx_ativo)) in ("NAO", "NO", "FALSE", "0", "N"):
                            ativo = False

                        produto = Produto.objects.create(
                            nome=nome_prod,
                            categoria=categoria,
                            descricao=desc,
                            modo_venda=modo,
                            preco=preco,
                            preco_kg=preco_kg,
                            ativo=ativo,
                            horario_inicio=h_inicio,
                            horario_fim=h_fim,
                        )
                        criados += 1

                    # 4. Vincular ao Cardápio
                    cardapio_obj.produtos.add(produto)

                total = criados + existentes

                # Nenhum produto válido: cancela tudo (não deixa cardápio vazio no banco).
                if total == 0:
                    raise ValueError(
                        "Nenhum produto válido encontrado na planilha. "
                        "Confira se as colunas 'Produto' e 'Categoria' estão preenchidas."
                    )

            # Sucesso (fora do atomic: os dados já foram gravados)
            messages.success(
                request,
                f'Cardápio "{nome_cardapio}" criado com {total} produto(s)! '
                f"{criados} novo(s) criado(s), {existentes} já existente(s) vinculado(s).",
            )
            if tipo_cardapio == "NORMAL" and qtd_dias == 0:
                messages.warning(
                    request,
                    "⚠️ Você não marcou nenhum dia da semana. Assim o cardápio NÃO vai "
                    "aparecer para o cliente. Clique em Editar e escolha os dias/horários.",
                )
            elif tipo_cardapio == "ESPECIAL" and not request.POST.get("data_inicio"):
                messages.warning(
                    request,
                    "⚠️ Cardápio especial sem data inicial: ele não vai aparecer até você definir a data.",
                )
        except Exception as e:
            messages.error(request, f"Erro ao processar a planilha: {str(e)}")

        return redirect("admin:cardapio_cardapio_changelist")

    return render(request, "admin/cardapio/importar_planilha.html")
