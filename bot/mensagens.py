"""Mensagens estruturadas para WhatsApp (Meta Cloud API — interativas)."""

from __future__ import annotations


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)].rstrip() + "…"


def T(corpo: str) -> dict:
    return {"tipo": "texto", "corpo": corpo}


def lista(corpo: str, botao: str, linhas: list[dict]) -> dict:
    rows = []
    for row in (linhas or [])[:10]:
        item = {
            "id": str(row["id"]),
            "titulo": _trunc(str(row.get("titulo", "")), 24),
        }
        if row.get("descricao"):
            item["descricao"] = _trunc(str(row["descricao"]), 72)
        rows.append(item)
    return {
        "tipo": "lista",
        "corpo": corpo,
        "botao": _trunc(botao, 20),
        "linhas": rows,
    }


def botoes(corpo: str, opcoes: list[dict]) -> dict:
    opts = []
    for op in opcoes[:3]:
        opts.append(
            {
                "id": str(op["id"]),
                "titulo": _trunc(str(op.get("titulo", "")), 20),
            }
        )
    return {"tipo": "botoes", "corpo": corpo, "opcoes": opts}



def multi_select(
    corpo: str,
    opcoes: list[dict],
    minimo: int = 1,
    maximo: int = 10,
    escolhidos: list[str] | None = None,
    pagina: int = 0,
) -> dict:
    """Multi-select para simulador (checkboxes). opcoes: [{id, titulo, descricao?}].

    `escolhidos` são os nomes já marcados; usados para montar o texto de progresso
    quando a mensagem precisa virar lista interativa (ver `multi_para_lista`).
    """
    opts = []
    for op in opcoes:
        item = {"id": str(op["id"]), "titulo": _trunc(str(op.get("titulo", "")), 40)}
        if op.get("descricao"):
            item["descricao"] = _trunc(str(op["descricao"]), 72)
        opts.append(item)
    return {
        "tipo": "multi_select",
        "corpo": corpo,
        "opcoes": opts,
        "minimo": minimo,
        "maximo": maximo,
        "escolhidos": list(escolhidos or []),
        "pagina": pagina,
        "botao": "Confirmar escolha",
    }


def _cabecalho_multi(msg: dict) -> tuple[str, int]:
    """Corpo do multi_select com o progresso da escolha. Devolve (texto, faltam)."""
    corpo = (msg.get("corpo") or "").strip()
    maximo = int(msg.get("maximo") or 1)
    escolhidos = msg.get("escolhidos") or []
    faltam = max(0, maximo - len(escolhidos))
    partes = [corpo]
    if escolhidos:
        partes.append("Já escolhido: " + ", ".join(escolhidos) + ".")
    return "\n".join(x for x in partes if x), faltam


MAX_LINHAS_LISTA = 10   # teto de linhas de uma lista interativa na Cloud API
ID_MAIS = "mais"        # linha de paginação
ID_PRONTO = "pronto"    # linha de encerrar a escolha


def lista_paginada(corpo: str, botao: str, linhas: list[dict], pagina: int = 0,
                   fixas: list[dict] | None = None) -> dict:
    """Lista de escolha única que não perde item quando passa de 10 linhas.

    A Cloud API corta a lista em 10 silenciosamente — item nº 11 simplesmente
    some do cardápio. Aqui reserva-se uma linha para "ver mais", que dá a volta
    no fim, e o cliente alcança tudo só tocando.
    """
    fixas = list(fixas or [])
    reservados = len(fixas)
    if len(linhas) > MAX_LINHAS_LISTA - reservados:
        reservados += 1                                  # linha "ver mais"
    slots = max(1, MAX_LINHAS_LISTA - reservados)

    paginas = max(1, -(-len(linhas) // slots))
    pagina = int(pagina or 0) % paginas
    visiveis = [dict(l) for l in linhas[pagina * slots:(pagina + 1) * slots]]
    if paginas > 1:
        visiveis.append({
            "id": ID_MAIS,
            "titulo": "➡️ Ver mais opções",
            "descricao": f"página {pagina + 1} de {paginas}",
        })
    return lista(corpo, botao, visiveis + fixas)


def multi_para_lista(msg: dict) -> dict:
    """Converte um multi_select em lista interativa — tudo por toque, nada digitado.

    A Cloud API limita a lista a 10 linhas, então cardápio grande é paginado:
    reserva-se uma linha para "ver mais" (que dá a volta no fim, para não virar beco
    sem saída) e outra para "pronto", que encerra a escolha sem o cliente escrever.
    """
    cabecalho, faltam = _cabecalho_multi(msg)
    opcoes = list(msg.get("opcoes") or [])
    escolhidos = msg.get("escolhidos") or []

    reservados = 1 if escolhidos else 0                 # linha "pronto"
    if len(opcoes) > MAX_LINHAS_LISTA - reservados:
        reservados += 1                                 # linha "ver mais"
    slots = max(1, MAX_LINHAS_LISTA - reservados)

    paginas = max(1, -(-len(opcoes) // slots))
    pagina = int(msg.get("pagina") or 0) % paginas
    linhas = [dict(o) for o in opcoes[pagina * slots:(pagina + 1) * slots]]

    if paginas > 1:
        linhas.append({
            "id": ID_MAIS,
            "titulo": "➡️ Ver mais opções",
            "descricao": f"página {pagina + 1} de {paginas}",
        })
    if escolhidos:
        linhas.append({
            "id": ID_PRONTO,
            "titulo": "✅ Pronto, pode seguir",
            "descricao": "Encerrar a escolha",
        })

    partes = [
        cabecalho,
        f"Toque para escolher (cabem mais {faltam})." if faltam > 1 else "Toque para escolher:",
    ]
    return lista("\n".join(partes), "Ver acompanhamentos", linhas)


def flow_acompanhamentos(
    corpo: str, flow_id: str, cta: str, payload: dict, token: str = ""
) -> dict:
    """Mensagem de Flow. `token` viaja como parâmetro do Flow, nunca dentro de `data`:
    o `data` precisa bater exatamente com o schema declarado na tela publicada."""
    return {
        "tipo": "flow",
        "corpo": corpo,
        "flow_id": flow_id,
        "cta": _trunc(cta, 20),
        "payload": payload,
        "token": token,
    }



def pix_order(
    corpo: str,
    pedido_id: int,
    subtotal_centavos: int,
    taxa_centavos: int,
    pix_copia_cola: str,
    merchant_name: str,
    reference_id: str,
    order_parameters: dict,
    nativo: bool = False,
) -> dict:
    return {
        "tipo": "pix_order",
        "corpo": corpo,
        "pedido_id": pedido_id,
        "subtotal_centavos": subtotal_centavos,
        "taxa_centavos": taxa_centavos,
        "pix_copia_cola": pix_copia_cola,
        "merchant_name": merchant_name,
        "reference_id": reference_id,
        "order_parameters": order_parameters,
        "nativo": nativo,
    }


def texto_plano(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if not isinstance(msg, dict):
        return str(msg)
    tipo = msg.get("tipo", "texto")
    if tipo == "texto":
        return msg.get("corpo", "")
    if tipo == "lista":
        linhas = []
        for row in msg.get("linhas") or []:
            linha = row.get("titulo", "")
            if row.get("descricao"):
                linha += f" — {row['descricao']}"
            linhas.append(linha)
        botao = msg.get("botao", "")
        cab = msg.get("corpo", "")
        extra = f"\n[{botao}] " + " | ".join(linhas) if linhas else ""
        return cab + extra
    if tipo == "multi_select":
        # Sem Flow publicado o multi_select vira menu numerado, nunca texto cru.
        return texto_numerado(msg)
    if tipo == "flow":
        return f"{msg.get('corpo', '')}\n[Flow: {msg.get('cta', 'Abrir')}]"
    if tipo == "pix_order":
        return f"{msg.get('corpo', '')}\n[Pix nativo: pedido #{msg.get('pedido_id')}]"
    if tipo == "botoes":
        ops = " | ".join(o.get("titulo", "") for o in (msg.get("opcoes") or []))
        return f"{msg.get('corpo', '')}\n[botões: {ops}]"
    return str(msg)


def texto_numerado(msg) -> str:
    """Converte uma mensagem interativa em TEXTO com opções numeradas.

    Usado quando o provedor é texto puro (ex.: Evolution API), pois o WhatsApp
    Web não renderiza listas/botões de forma confiável. O cliente responde com o
    número da opção (o id de cada linha/opção é numérico no fluxo).
    """
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if not isinstance(msg, dict):
        return str(msg)
    tipo = msg.get("tipo", "texto")
    corpo = (msg.get("corpo", "") or "").strip()

    def _opcoes(itens, chave_titulo="titulo"):
        linhas = []
        for it in itens or []:
            titulo = it.get(chave_titulo, "")
            desc = it.get("descricao")
            linha = f"*{it.get('id')}* - {titulo}"
            if desc:
                linha += f" ({desc})"
            linhas.append(linha)
        return "\n".join(linhas)

    if tipo == "lista":
        opts = _opcoes(msg.get("linhas"))
        return f"{corpo}\n\n{opts}\n\n_Responda com o número da opção._" if opts else corpo
    if tipo == "botoes":
        opts = _opcoes(msg.get("opcoes"))
        return f"{corpo}\n\n{opts}\n\n_Responda com o número._" if opts else corpo
    if tipo == "multi_select":
        opts = _opcoes(msg.get("opcoes"))
        return (f"{corpo}\n\n{opts}\n\n_Responda os números separados por vírgula "
                f"(ex.: 1,3,5) e depois envie *pronto*._") if opts else corpo
    if tipo == "pix_order":
        copia = msg.get("pix_copia_cola") or ""
        return f"{corpo}\n\n{copia}".strip()
    if tipo == "flow":
        return corpo
    return texto_plano(msg)


def normalizar_mensagens(mensagens: list) -> list[dict]:
    out: list[dict] = []
    for m in mensagens or []:
        if isinstance(m, str):
            out.append(T(m))
        elif isinstance(m, dict) and m.get("tipo"):
            out.append(m)
        else:
            out.append(T(str(m)))
    return out
