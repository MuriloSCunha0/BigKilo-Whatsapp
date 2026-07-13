import openpyxl
from decimal import Decimal
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import path
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
    "Ativo",
    "Cardápios",
]

def baixar_planilha_exemplo(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Produtos"
    
    # Cabeçalho
    for col_num, nome in enumerate(COLUNAS_ESPERADAS, 1):
        cell = ws.cell(row=1, column=col_num, value=nome)
        cell.font = openpyxl.styles.Font(bold=True)
    
    # Linha de exemplo 1
    exemplo1 = [
        "Bebidas", "BEBIDA", "Coca-Cola 2L", "Gelada", 
        "UNIDADE", "12.00", "0.00", "SIM", "Almoço Diário"
    ]
    for col_num, val in enumerate(exemplo1, 1):
        ws.cell(row=2, column=col_num, value=val)

    # Linha de exemplo 2
    exemplo2 = [
        "Proteínas", "PROTEINA", "Lombo (Madeira)", "Ao molho", 
        "MONTAGEM", "0.00", "0.00", "SIM", "Almoço Diário, Jantar de Domingo"
    ]
    for col_num, val in enumerate(exemplo2, 1):
        ws.cell(row=3, column=col_num, value=val)
        
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="modelo_cardapio_bigkilo.xlsx"'
    wb.save(response)
    return response

@require_http_methods(["GET", "POST"])
def importar_planilha_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get("planilha")
        if not arquivo:
            messages.error(request, "Nenhum arquivo enviado.")
            return redirect("admin:cardapio_produto_changelist")
            
        if not arquivo.name.endswith(".xlsx"):
            messages.error(request, "O arquivo deve ser um Excel (.xlsx).")
            return redirect("admin:cardapio_produto_changelist")
            
        try:
            wb = openpyxl.load_workbook(arquivo, data_only=True)
            ws = wb.active
            
            # Valida cabeçalho (simplificado)
            header = [str(cell.value).strip() if cell.value else "" for cell in ws[1]]
            
            if "Produto" not in header or "Categoria" not in header:
                messages.error(request, "A planilha não possui as colunas 'Produto' e 'Categoria'. Use a planilha de exemplo.")
                return redirect("admin:cardapio_produto_changelist")
                
            idx_cat = header.index("Categoria")
            idx_tipo = header.index("Tipo da Categoria") if "Tipo da Categoria" in header else -1
            idx_prod = header.index("Produto")
            idx_desc = header.index("Descrição") if "Descrição" in header else -1
            idx_modo = header.index("Modo de Venda") if "Modo de Venda" in header else -1
            idx_preco = header.index("Preço") if "Preço" in header else -1
            idx_kg = header.index("Preço por KG") if "Preço por KG" in header else -1
            idx_ativo = header.index("Ativo") if "Ativo" in header else -1
            idx_card = header.index("Cardápios") if "Cardápios" in header else -1
            
            criados = 0
            atualizados = 0
            
            for row in ws.iter_rows(min_row=2, values_only=True):
                nome_prod = str(row[idx_prod]).strip() if len(row) > idx_prod and row[idx_prod] else ""
                nome_cat = str(row[idx_cat]).strip() if len(row) > idx_cat and row[idx_cat] else ""
                
                if not nome_prod or not nome_cat or nome_prod == "None" or nome_cat == "None":
                    continue
                    
                # 1. Categoria
                tipo_cat = str(row[idx_tipo]).strip().upper() if idx_tipo >= 0 and row[idx_tipo] else "OUTRO"
                if tipo_cat not in dict(Categoria.Tipo.choices).keys():
                    tipo_cat = "OUTRO"
                    
                categoria, _ = Categoria.objects.get_or_create(
                    nome__iexact=nome_cat,
                    defaults={"nome": nome_cat, "tipo": tipo_cat}
                )
                
                # 2. Produto
                desc = str(row[idx_desc]).strip() if idx_desc >= 0 and row[idx_desc] and row[idx_desc] != "None" else ""
                modo = str(row[idx_modo]).strip().upper() if idx_modo >= 0 and row[idx_modo] and row[idx_modo] != "None" else "UNIDADE"
                if modo not in dict(Produto.ModoVenda.choices).keys():
                    modo = "UNIDADE"
                
                try:
                    preco = Decimal(str(row[idx_preco]).replace(",", ".").strip()) if idx_preco >= 0 and row[idx_preco] else Decimal("0.00")
                except:
                    preco = Decimal("0.00")
                    
                try:
                    preco_kg = Decimal(str(row[idx_kg]).replace(",", ".").strip()) if idx_kg >= 0 and row[idx_kg] else Decimal("0.00")
                except:
                    preco_kg = Decimal("0.00")
                
                ativo = True
                if idx_ativo >= 0 and row[idx_ativo]:
                    val_ativo = str(row[idx_ativo]).strip().upper()
                    if val_ativo in ["NÃO", "NAO", "NO", "FALSE", "0"]:
                        ativo = False
                
                produto, created = Produto.objects.update_or_create(
                    nome__iexact=nome_prod,
                    defaults={
                        "nome": nome_prod,
                        "categoria": categoria,
                        "descricao": desc,
                        "modo_venda": modo,
                        "preco": preco,
                        "preco_kg": preco_kg,
                        "ativo": ativo
                    }
                )
                
                if created:
                    criados += 1
                else:
                    atualizados += 1
                    
                # 3. Cardápios
                if idx_card >= 0 and row[idx_card] and row[idx_card] != "None":
                    nomes_cards = [c.strip() for c in str(row[idx_card]).split(",") if c.strip()]
                    for nc in nomes_cards:
                        card_obj, _ = Cardapio.objects.get_or_create(
                            nome__iexact=nc,
                            defaults={"nome": nc, "tipo": Cardapio.Tipo.NORMAL}
                        )
                        card_obj.produtos.add(produto)
            
            messages.success(request, f"Planilha importada com sucesso! {criados} produtos criados, {atualizados} atualizados.")
        except Exception as e:
            messages.error(request, f"Erro ao processar a planilha: {str(e)}")
            
        return redirect("admin:cardapio_produto_changelist")
        
    return render(request, "admin/cardapio/importar_planilha.html")
