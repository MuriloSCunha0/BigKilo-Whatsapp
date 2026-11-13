"""Lembrete para quem montou o pedido e parou antes de pagar.

Nas conversas reais (29/07–28/10), 4 pessoas chegaram até "Pix ou cartão?" com o
pedido pronto (R$ 107,60, R$ 53,90, R$ 53,90, R$ 34,80) e nunca voltaram. Um
toque de lembrete, uma vez só, traz parte delas de volta.

Não há agendador no servidor. Quem chama `verificar_lembretes` é o que já roda
sozinho: o programa da impressora (a cada poucos segundos, com o PC da loja ligado),
toda mensagem que chega no WhatsApp e a tela do Modo Cozinha. Um trava de 60 s no
cache garante que a varredura roda no máximo uma vez por minuto.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

ESPERA_MIN = 15   # parado há pelo menos isto...
JANELA_MIN = 60   # ...e no máximo isto (depois disso o lembrete soa estranho)
ESPERA_ATENDENTE_MIN = 10  # "Falar com a loja" sem resposta da equipe

ID_LEMBRETE_FINALIZAR = "lembrete_finalizar"
ID_LEMBRETE_DESISTIR = "lembrete_desistir"
ID_ATENDENTE = "pedir_atendente"


def _moeda(v) -> str:
    return "R$ " + f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def verificar_lembretes() -> int:
    """Envia os lembretes devidos. Nunca levanta erro para quem chamou."""
    schema = getattr(connection, "schema_name", "") or ""
    if schema == "public":
        return 0
    if not cache.add(f"lembretes:{schema}", 1, 60):
        return 0
    try:
        return _varrer()
    except Exception:
        logger.exception("Falha ao verificar lembretes")
        return 0


def _varrer() -> int:
    from pedidos.models import ConfiguracaoLoja, Pedido, SessaoBot

    cfg = ConfiguracaoLoja.get()
    if not cfg.esta_aberta:
        return 0  # com a loja fechada não dá para entregar: lembrar só irrita
    agora = timezone.now()
    sessoes = SessaoBot.objects.filter(
        atualizado_em__gte=agora - timedelta(minutes=JANELA_MIN),
        atualizado_em__lte=agora - timedelta(minutes=ESPERA_MIN),
    ).exclude(estado_atual=SessaoBot.Estado.ATENDIMENTO_HUMANO)

    enviados = 0
    for s in sessoes:
        c = dict(s.carrinho_json or {})
        if s.estado_atual == SessaoBot.Estado.AGUARDANDO_PAGAMENTO:
            msg, marca = _lembrete_pix(s, c, Pedido)
        else:
            msg, marca = _lembrete_carrinho(s, c, cfg, Pedido)
        if not msg:
            continue
        c.update(marca)
        # Marca ANTES de enviar e só se a sessão não mudou desde a leitura: se o
        # cliente respondeu neste meio-tempo, ele já voltou e o lembrete não vai.
        if not SessaoBot.objects.filter(pk=s.pk, atualizado_em=s.atualizado_em).update(carrinho_json=c):
            continue
        _enviar(s.telefone, msg)
        enviados += 1
    return enviados + _sem_resposta(agora)


def _sem_resposta(agora) -> int:
    """Quem tocou "Falar com a loja" e ninguém respondeu em ESPERA_ATENDENTE_MIN.

    Em 12/11 uma cliente com R$ 102,80 no carrinho pediu ajuda, ninguém respondeu e
    ela foi embora. Agora o bot pede desculpas, diz que a mensagem ficou registrada e
    oferece seguir sozinho. Uma vez só por pedido de ajuda.
    """
    from datetime import datetime

    from bot.mensagens import botoes
    from pedidos.models import LogMensagem, SessaoBot

    enviados = 0
    for s in SessaoBot.objects.filter(estado_atual=SessaoBot.Estado.ATENDIMENTO_HUMANO,
                                      atualizado_em__gte=agora - timedelta(hours=2)):
        c = dict(s.carrinho_json or {})
        quando = c.get("_chamou_loja_em")
        if not quando or c.get("_aviso_sem_resposta"):
            continue
        try:
            chamou = datetime.fromisoformat(quando)
        except ValueError:
            continue
        if agora - chamou < timedelta(minutes=ESPERA_ATENDENTE_MIN):
            continue
        # Mensagem que saiu depois do pedido de ajuda e não é automática do bot = a
        # equipe respondeu (texto, foto ou "Abrir atendimento").
        respostas = (LogMensagem.objects
                     .filter(telefone=s.telefone, direcao=LogMensagem.Direcao.SAIDA, criado_em__gt=chamou)
                     .exclude(texto__startswith="Pronto! 😊 Chamei")
                     .exclude(texto__startswith="⏰").exclude(texto__startswith="⚠️"))
        if respostas.exists():
            continue
        itens = c.get("itens") or []
        opcoes = ([{"id": ID_LEMBRETE_FINALIZAR, "titulo": "✅ Finalizar pedido"}] if itens else [])
        opcoes.append({"id": "ver_menu", "titulo": "🍽️ Ver cardápio"})
        msg = botoes(
            f"Oi{_nome(s.telefone)}! Desculpe a demora 🙏 Nossa equipe ainda não conseguiu "
            "te responder, mas sua mensagem ficou registrada e vamos responder por aqui.\n\n"
            + ("Se quiser, você já pode finalizar seu pedido:" if itens
               else "Enquanto isso, o cardápio continua à sua disposição:"),
            opcoes)
        c["_aviso_sem_resposta"] = True
        if not SessaoBot.objects.filter(pk=s.pk, atualizado_em=s.atualizado_em).update(carrinho_json=c):
            continue
        _enviar(s.telefone, msg)
        enviados += 1
    return enviados


def _nome(telefone: str) -> str:
    from pedidos.models import Cliente, _primeiro_nome

    nome = _primeiro_nome(Cliente.objects.filter(telefone=telefone).first())
    return f" {nome}" if nome else ""


def _lembrete_carrinho(s, c, cfg, Pedido):
    itens = c.get("itens") or []
    if not itens or c.get("_lembrete"):
        return None, {}
    lojista = c.get("canal") == Pedido.Canal.LOJISTA
    if (lojista and cfg.fechado_lojista) or (not lojista and cfg.fechado_cliente):
        return None, {}
    total = sum(Decimal(str(i.get("subtotal") or 0)) for i in itens)
    from bot.mensagens import botoes

    msg = botoes(
        f"Oi{_nome(s.telefone)}! Seu pedido ficou guardado aqui 🛒\n"
        f"{len(itens)} item(ns) — {_moeda(total)}\n\n"
        "Quer finalizar? É só tocar abaixo. 🙂",
        [{"id": ID_LEMBRETE_FINALIZAR, "titulo": "✅ Finalizar pedido"},
         {"id": ID_ATENDENTE, "titulo": "💬 Falar com a loja"},
         {"id": ID_LEMBRETE_DESISTIR, "titulo": "🗑️ Não quero mais"}],
    )
    return msg, {"_lembrete": True}


def _lembrete_pix(s, c, Pedido):
    pedido = (Pedido.objects.filter(
        cliente__telefone=s.telefone, status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        forma_pagamento=Pedido.FormaPagamento.PIX,
        criado_em__gte=timezone.now() - timedelta(minutes=JANELA_MIN),
    ).order_by("-criado_em").first())
    if not pedido or c.get("_lembrete_pix") == pedido.id:
        return None, {}
    from bot.mensagens import botoes

    msg = botoes(
        f"Oi{_nome(s.telefone)}! Seu pedido #{pedido.id} ainda está esperando o Pix 🙂 "
        "Assim que o pagamento cair, ele vai direto para a cozinha.\n\n"
        "Se já pagou, pode desconsiderar esta mensagem.",
        [{"id": ID_ATENDENTE, "titulo": "💬 Falar com a loja"}],
    )
    return msg, {"_lembrete_pix": pedido.id}


def _enviar(telefone: str, msg: dict):
    from bot.mensagens import texto_plano
    from bot.whatsapp import enviar_mensagem_sync
    from pedidos.models import LogMensagem

    try:
        enviar_mensagem_sync(telefone, msg)
        LogMensagem.objects.create(telefone=telefone, direcao=LogMensagem.Direcao.SAIDA,
                                   texto=f"⏰ {texto_plano(msg)}")
    except Exception as exc:
        logger.exception("Lembrete não enviado para %s", telefone)
        LogMensagem.objects.create(telefone=telefone, direcao=LogMensagem.Direcao.SAIDA,
                                   texto=f"⚠️ Lembrete não enviado: {str(exc)[:300]}")
