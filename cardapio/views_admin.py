import openpyxl
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


def baixar_planilha_exemplo(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cardápio"

    # Cabeçalho
    for col_num, nome in enumerate(COLUNAS_ESPERADAS, 1):
        cell = ws.cell(row=1, column=col_num, value=nome)
        cell.font = openpyxl.styles.Font(bold=True)
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor="FFEFD5")

    # Ajustar larguras para ficar legível
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 25
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 10
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 8

    # Linha de exemplo 1
    exemplo1 = [
        "Bebidas", "BEBIDA", "Coca-Cola 2L", "Gelada",
        "UNIDADE", "12.00", "0.00", "", "SIM",
    ]
    for col_num, val in enumerate(exemplo1, 1):
        ws.cell(row=2, column=col_num, value=val)

    # Linha de exemplo 2
    exemplo2 = [
        "Proteínas", "PROTEINA", "Lombo (Madeira)", "Ao molho madeira",
        "MONTAGEM", "0.00", "0.00", "", "SIM",
    ]
    for col_num, val in enumerate(exemplo2, 1):
        ws.cell(row=3, column=col_num, value=val)

    # Linha de exemplo 3 (Sopa à noite)
    exemplo3 = [
        "Caldos", "ACOMPANHAMENTO", "Caldo de Feijão", "",
        "UNIDADE", "15.00", "0.00", "18:00-23:00", "SIM",
    ]
    for col_num, val in enumerate(exemplo3, 1):
        ws.cell(row=4, column=col_num, value=val)

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
                tipo_cat = str(row[idx_tipo]).strip().upper() if idx_tipo >= 0 and row[idx_tipo] else "OUTRO"
                if tipo_cat not in dict(Categoria.Tipo.choices).keys():
                    tipo_cat = "OUTRO"

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
                    modo = str(row[idx_modo]).strip().upper() if idx_modo >= 0 and row[idx_modo] and row[idx_modo] != "None" else "UNIDADE"
                    if modo not in dict(Produto.ModoVenda.choices).keys():
                        modo = "UNIDADE"

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
                        val_ativo = str(row[idx_ativo]).strip().upper()
                        if val_ativo in ["NÃO", "NAO", "NO", "FALSE", "0"]:
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
