import re

with open('bot/fluxo.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. _pos_item_adicionado
content = re.sub(
    r'(def _pos_item_adicionado\(sessao, msgs: list, perfil=None\) -> list:\n\s+return msgs \+ )_tela_resumo_carrinho\(sessao, perfil\)',
    r'\g<1>_tela_perguntar_adicionar(sessao, perfil)',
    content
)

# 2. MENU_PRINCIPAL low == "2"
content = re.sub(
    r'        elif low == "2":\n\s+if sessao\.carrinho_json\.get\("itens"\):\n\s+out\["mensagens"\] = \["Opção inválida\."\] \+ _tela_menu\(sessao\)\n\s+else:\n\s+out\["mensagens"\] = _tela_tipo_grande_porcao\(sessao, perfil\)',
    lambda m: '''        elif low == "2":
            out["mensagens"] = _tela_tipo_grande_porcao(sessao, perfil)''',
    content
)

# 3. MENU_PRINCIPAL low in MENU_CATEGORIAS
content = re.sub(
    r'        elif low in MENU_CATEGORIAS:\n\s+# Block sandwiches and soups if it\'s an encomenda\n\s+if encomenda:\n\s+out\["mensagens"\] = \["Opção inválida para Encomendas\."\] \+ _tela_menu\(sessao\)\n\s+else:\n\s+out\["mensagens"\] = _tela_categoria\(sessao, \*MENU_CATEGORIAS\[low\]\)',
    lambda m: '''        elif low in MENU_CATEGORIAS:
            out["mensagens"] = _tela_categoria(sessao, *MENU_CATEGORIAS[low])''',
    content
)

# 4. _parse_data_futura
new_parse = r'''def _parse_data_futura(texto: str):
    """Interpreta dia/mês (ou dia/mês/ano) e devolve uma data futura, ou None."""
    from datetime import date, timedelta
    from django.utils import timezone
    import re

    hoje = timezone.localdate()
    texto = (texto or "").strip().lower()

    if "amanh" in texto or texto == "amanha":
        return hoje + timedelta(days=1)
    if "depois" in texto:
        return hoje + timedelta(days=2)

    match = re.search(r"(\d{1,2})\s*(?:/|-|\.|de)?\s*([a-z]+|\d{1,2})(?:\s*(?:/|-|\.|de)?\s*(\d{2,4}))?", texto)
    if not match:
        return None

    dia_str, mes_str, ano_str = match.groups()
    try:
        dia = int(dia_str)
        if mes_str.isdigit():
            mes = int(mes_str)
        else:
            meses = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, 
                     "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
            mes = meses.get(mes_str[:3], 0)
            if not mes: return None

        ano = hoje.year
        if ano_str:
            ano = int(ano_str)
            if ano < 100:
                ano += 2000

        alvo = date(ano, mes, dia)
        if not ano_str and alvo <= hoje:
            alvo = date(hoje.year + 1, mes, dia)
        return alvo if alvo > hoje else None
    except ValueError:
        return None
'''
content = re.sub(
    r'def _parse_data_futura\(texto: str\):\n.*?return alvo if alvo > hoje else None\n',
    lambda m: new_parse,
    content,
    flags=re.DOTALL
)

# 5. PEDINDO_CEP regex
content = re.sub(
    r'    if estado == SessaoBot\.Estado\.PEDINDO_CEP:\n\s+digitos = "".join\(c for c in texto if c\.isdigit\(\)\)\n\s+if len\(digitos\) != 8:\n\s+if texto\.strip\(\)\.isdigit\(\) and len\(texto\.strip\(\)\) < 8:\n\s+from bot\.mensagens import T\n\s+msg = ".*?"\n\s+out\["mensagens"\] = \[T\(msg\)\]\n\s+else:\n\s+out\["mensagens"\] = \[mensagem\("CEP_INVALIDO", _cliente\(sessao\), perfil=perfil\)\]\n\s+sessao\.save\(\)\n\s+return out',
    lambda m: '''    if estado == SessaoBot.Estado.PEDINDO_CEP:
        import re
        match = re.search(r"\\d{5}-?\\d{3}", texto)
        if not match:
            out["mensagens"] = [mensagem("CEP_INVALIDO", _cliente(sessao), perfil=perfil)]
            sessao.save()
            return out
        digitos = match.group().replace("-", "")''',
    content
)

# 6. ENCOMENDA_DATA
content = re.sub(
    r'    if estado == SessaoBot\.Estado\.ENCOMENDA_DATA:\n\s+data = _parse_data_futura\(texto\)',
    lambda m: '''    if estado == SessaoBot.Estado.ENCOMENDA_DATA:
        acao = _resolver(sessao, texto)
        texto_data = acao if acao else texto
        data = _parse_data_futura(texto_data)''',
    content
)

# 7. Menu Encomenda data MSG
new_enc_msg = '''            sessao.estado_atual = SessaoBot.Estado.ENCOMENDA_DATA
            from django.utils import timezone
            from datetime import timedelta
            hoje = timezone.localtime().date()
            amanha = hoje + timedelta(days=1)
            depois = hoje + timedelta(days=2)
            _set_menu(sessao, {
                "1": amanha.strftime("%d/%m/%Y"),
                "2": depois.strftime("%d/%m/%Y"),
            })
            corpo = "Legal! Para qual data é a sua encomenda?\\n\\nVocê pode tocar em uma das opções ou digitar a data (ex: 12/10)."
            linhas = [
                {"id": "1", "titulo": f"Amanhã ({amanha.strftime('%d/%m')})"},
                {"id": "2", "titulo": f"Depois ({depois.strftime('%d/%m')})"},
            ]
            from bot.mensagens import lista
            out["mensagens"] = [lista(corpo, "Datas Rápidas", linhas)]'''

content = re.sub(
    r'            sessao\.estado_atual = SessaoBot\.Estado\.ENCOMENDA_FUTURA\n\s+_set_menu\(sessao, \{\}\)\n\s+out\["mensagens"\] = \[mensagem\("PEDIR_DATA_ENCOMENDA", _cliente\(sessao\), perfil=perfil\)\]',
    lambda m: new_enc_msg,
    content
)
content = re.sub(
    r'            sessao\.estado_atual = SessaoBot\.Estado\.ENCOMENDA_DATA\n\s+msg = "Legal! Para qual data é a sua encomenda\? \(ex: 12/10 ou 12 de Outubro\)"\n\s+out\["mensagens"\] = \[msg\]',
    lambda m: new_enc_msg,
    content
)

# 8. Taxa
content = re.sub(
    r'    else:\n\s+linhas\.append\("🛵 Método: Entrega em domicílio"\)\n\s+linhas \+= \[\n\s+f"Produtos: \{_moeda\(produtos\)\}",\n\s+f"Taxa de entrega: \{_moeda\(taxa\)\} \(paga ao entregador na entrega\)",\n\s+f"Total: \{_moeda\(total\)\}",\n\s+"",\n\s+f"💳 Agora pague os \*\{_moeda\(produtos\)\}\* dos produtos pelo Pix\. "\n\s+f"A taxa de \{_moeda\(taxa\)\} você paga ao entregador\. Gerando seu Pix\.\.\.",\n\s+\]\n\s+return pedido\.pk, avisos \+ \["\\n"\.join\(linhas\)\]',
    lambda m: '''    else:
        linhas.append("🛵 Método: Entrega em domicílio")
        linhas.append(f"Produtos: {_moeda(produtos)}")
        if taxa > 0:
            linhas.append(f"Taxa de entrega: {_moeda(taxa)} (paga ao entregador na entrega)")
        linhas.append(f"Total: {_moeda(total)}")
        linhas.append("")
        if taxa > 0:
            linhas.append(
                f"💳 Agora pague os *{_moeda(produtos)}* dos produtos pelo Pix. "
                f"A taxa de {_moeda(taxa)} você paga ao entregador. Gerando seu Pix..."
            )
        else:
            linhas.append(f"💳 Agora pague os *{_moeda(total)}* do pedido pelo Pix. Gerando seu Pix...")
    return pedido.pk, avisos + ["\\n".join(linhas)]''',
    content
)

with open('bot/fluxo.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("refactoring done")
