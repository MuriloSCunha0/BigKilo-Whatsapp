"""Checklist de prontidão da loja (painel do lojista)."""

from cardapio.models import Produto
from django.conf import settings

from .models import AreaEntrega, PerfilFluxo


def checklist_loja():
    """Retorna itens do checklist com status ok/link para corrigir."""
    perfil = PerfilFluxo.objects.filter(ativo=True).first()
    tem_produtos = Produto.objects.filter(ativo=True).exists()
    tem_bairros = AreaEntrega.objects.filter(ativo=True).exists()
    tem_fluxo = perfil is not None and perfil.mensagens.exists()
    token_impressao = bool(getattr(settings, "IMPRESSAO_API_TOKEN", ""))

    itens = [
        {
            "id": "bairros",
            "titulo": "Áreas de entrega cadastradas",
            "ok": tem_bairros,
            "link": "/admin/pedidos/areaentrega/",
            "dica": "Cadastre os bairros que o bot aceita.",
        },
        {
            "id": "produtos",
            "titulo": "Produtos ativos no cardápio",
            "ok": tem_produtos,
            "link": "/admin/cardapio/produto/",
            "dica": "Cadastre pelo menos um produto visível ao cliente.",
        },
        {
            "id": "fluxo",
            "titulo": "Fluxo de mensagens ativo",
            "ok": tem_fluxo,
            "link": "/admin/pedidos/perfilfluxo/",
            "dica": "Ative um fluxo e edite as mensagens do WhatsApp.",
        },
        {
            "id": "impressao",
            "titulo": "Token de impressão configurado",
            "ok": token_impressao,
            "link": "/admin/pedidos/configuracaoloja/",
            "dica": "Defina IMPRESSAO_API_TOKEN no servidor e rode print_agent.py no PC.",
        },
    ]
    pronta = all(i["ok"] for i in itens)
    return {"itens": itens, "pronta": pronta, "perfil_ativo": perfil.nome if perfil else None}
