import unicodedata
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from decimal import Decimal
from django.contrib import messages
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

        if not arquivo.name.endswith(".xlsx"):
            messages.error(request, "O arquivo deve ser um Excel (.xlsx).")
            return redirect("admin:cardapio_cardapio_changelist")

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
            
            # 1. Criar o Cardápio
            cardapio_obj = Cardapio.objects.create(
                nome=nome_cardapio,
                tipo=tipo_cardapio,
                exclusivo=exclusivo,
                ativo=True,
            )
            
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
                            periodo=periodo
                        )

            criados = 0
            existentes = 0

            import re
            from datetime import datetime
            
            for row in ws.iter_rows(min_row=2, values_only=True):
                raw_prod = str(row[idx_prod]) if len(row) > idx_prod and row[idx_prod] else ""
                raw_cat = str(row[idx_cat]) if len(row) > idx_cat and row[idx_cat] else ""
                
                # Normalização: remove espaços sobrando no começo/fim e reduz espaços duplos
                nome_prod = re.sub(r'\s+', ' ', raw_prod.strip())
                nome_cat = re.sub(r'\s+', ' ', raw_cat.strip())

                if not nome_prod or not nome_cat or nome_prod == "None" or nome_cat == "None":
                    continue

                # 2. Categoria (get or create - usando iexact para ignorar case)
                # Aceita código (PROTEINA) OU rótulo amigável (Proteína / proteina).
                tipo_cat = "OUTRO"
                if idx_tipo >= 0 and row[idx_tipo]:
                    tipo_cat = _mapa_tipo_categoria().get(_norm(row[idx_tipo]), "OUTRO")

                categoria, _ = Categoria.objects.get_or_create(
                    nome__iexact=nome_cat,
                    defaults={"nome": nome_cat, "tipo": tipo_cat},
                )
                
                # Tratar Horário Específico
                h_inicio = None
                h_fim = None
                if idx_horario >= 0 and row[idx_horario]:
                    horario_str = str(row[idx_horario]).strip()
                    if "-" in horario_str:
                        partes = horario_str.split("-")
                        try:
                            h_inicio = datetime.strptime(partes[0].strip(), "%H:%M").time()
                            h_fim = datetime.strptime(partes[1].strip(), "%H:%M").time()
                        except ValueError:
                            pass # ignora formato inválido

                # 3. Produto — se já existe (ignorando case), apenas vincula; se não, cria
                produto_existente = Produto.objects.filter(nome__iexact=nome_prod).first()

                if produto_existente:
                    produto = produto_existente
                    
                    # Atualiza os horários se vieram na planilha
                    update_fields = []
                    if h_inicio and h_fim:
                        produto.horario_inicio = h_inicio
                        produto.horario_fim = h_fim
                        update_fields.extend(["horario_inicio", "horario_fim"])
                    
                    if update_fields:
                        produto.save(update_fields=update_fields)
                        
                    existentes += 1
                else:
                    desc = str(row[idx_desc]).strip() if idx_desc >= 0 and row[idx_desc] and row[idx_desc] != "None" else ""
                    modo = "UNIDADE"
                    if idx_modo >= 0 and row[idx_modo] and row[idx_modo] != "None":
                        modo = _mapa_modo_venda().get(_norm(row[idx_modo]), "UNIDADE")

                    try:
                        preco = Decimal(str(row[idx_preco]).replace(",", ".").strip()) if idx_preco >= 0 and row[idx_preco] else Decimal("0.00")
                    except Exception:
                        preco = Decimal("0.00")

                    try:
                        preco_kg = Decimal(str(row[idx_kg]).replace(",", ".").strip()) if idx_kg >= 0 and row[idx_kg] else Decimal("0.00")
                    except Exception:
                        preco_kg = Decimal("0.00")

                    ativo = True
                    if idx_ativo >= 0 and row[idx_ativo]:
                        if _norm(row[idx_ativo]) in ("NAO", "NO", "FALSE", "0", "N"):
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
            messages.success(
                request,
                f'Cardápio "{nome_cardapio}" criado com {total} produto(s)! '
                f"{criados} novo(s) criado(s), {existentes} já existente(s) vinculado(s).",
            )
        except Exception as e:
            messages.error(request, f"Erro ao processar a planilha: {str(e)}")

        return redirect("admin:cardapio_cardapio_changelist")

    return render(request, "admin/cardapio/importar_planilha.html")
