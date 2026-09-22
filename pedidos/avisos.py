# -*- coding: utf-8 -*-
"""Avisos por e-mail para a loja (hoje: pedido de encomenda)."""

import logging
import urllib.parse

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

SAUDACAO = (
    "Olá, {nome}! 😊 Aqui é do Restaurante Big Kilo.\n\n"
    "Vi que você tem interesse em fazer uma encomenda — me conta o que você "
    "precisa (itens, data e horário) que eu organizo tudo para você! 🍽️"
)


def _so_digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def link_whatsapp(telefone: str, nome: str) -> str:
    """Link que abre a conversa com o cliente e já deixa a saudação escrita."""
    primeiro = (nome or "").strip().split()[0] if (nome or "").strip() else "tudo bem"
    texto = SAUDACAO.format(nome=primeiro)
    return "https://wa.me/%s?text=%s" % (_so_digitos(telefone), urllib.parse.quote(texto))


def avisar_encomenda(cliente, base_url: str = "", encomenda=None) -> bool:
    """Avisa a loja de que alguém pediu encomenda. Nunca levanta exceção.

    O atendimento ao cliente não pode quebrar porque o SMTP caiu ou não foi
    configurado — por isso todo erro aqui vira log, não exceção.
    """
    from .models import ConfiguracaoLoja

    try:
        cfg = ConfiguracaoLoja.get()
        destino = (cfg.email_encomendas or "").strip()
        if not destino:
            logger.info("Encomenda de %s: sem e-mail configurado.", cliente.telefone)
            return False
        if not settings.EMAIL_HOST_USER:
            logger.warning("Encomenda de %s: SMTP não configurado.", cliente.telefone)
            return False

        nome = cliente.nome_whatsapp or "Cliente"
        quando = timezone.localtime().strftime("%d/%m/%Y às %H:%M")
        wa = link_whatsapp(cliente.telefone, nome)
        inbox = f"{base_url.rstrip('/')}/atendimento/" if base_url else ""

        linhas = [
            f"{nome} pediu uma ENCOMENDA pelo WhatsApp.",
            "",
            f"Cliente : {nome}",
            f"WhatsApp: +{_so_digitos(cliente.telefone)}",
            f"Quando  : {quando}",
            "",
            "O cliente foi avisado de que alguém vai falar com ele.",
            "",
            "Responder agora pelo seu WhatsApp (saudação já escrita):",
            wa,
        ]
        if inbox:
            linhas += ["", "Ou responder pelo número da loja, no painel:", inbox]
        if encomenda is not None and base_url:
            linhas += [
                "",
                "Acompanhar e anotar o combinado:",
                "%s/admin/pedidos/encomenda/%s/change/" % (base_url.rstrip("/"), encomenda.pk),
            ]

        msg = EmailMessage(
            subject=f"🍽️ Encomenda: {nome} está esperando contato",
            body="\n".join(linhas),
            to=[destino],
        )
        msg.send(fail_silently=False)
        logger.info("Aviso de encomenda enviado para %s (cliente %s).", destino, cliente.telefone)
        return True
    except Exception:
        logger.exception("Falha ao avisar encomenda de %s", getattr(cliente, "telefone", "?"))
        return False
