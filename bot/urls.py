from django.urls import path

from . import views

app_name = "bot"

urlpatterns = [
    path("webhook/whatsapp/", views.webhook_whatsapp, name="webhook_whatsapp"),
    # Evolution API (WhatsApp não-oficial via QR) — provedor alternativo
    path("webhook/evolution/", views.webhook_evolution, name="webhook_evolution"),
    # Aba "Conexão do WhatsApp" (QR + status) embutida no painel
    path("whatsapp/conexao/", views.whatsapp_conexao, name="whatsapp_conexao"),
    path("whatsapp/status/", views.whatsapp_status, name="whatsapp_status"),
    path("whatsapp/qr/", views.whatsapp_qr, name="whatsapp_qr"),
    path("whatsapp/logout/", views.whatsapp_logout, name="whatsapp_logout"),
    # Aba "Atendimento" — inbox de conversas (estilo WhatsApp) + atendimento humano
    path("atendimento/", views.atendimento_inbox, name="atendimento_inbox"),
    path("atendimento/conversas/", views.atendimento_conversas, name="atendimento_conversas"),
    path("atendimento/mensagens/", views.atendimento_mensagens, name="atendimento_mensagens"),
    path("atendimento/abrir/", views.atendimento_abrir, name="atendimento_abrir"),
    path("atendimento/encerrar/", views.atendimento_encerrar, name="atendimento_encerrar"),
    path("atendimento/enviar/", views.atendimento_enviar, name="atendimento_enviar"),
    # Aba "Impressão" — download do programa de impressão do restaurante
    path("privacidade/", views.politica_privacidade, name="politica_privacidade"),
    path("impressao/", views.impressao_pagina, name="impressao_pagina"),
    path("impressao/baixar/", views.impressao_baixar, name="impressao_baixar"),
    # Simulador de testes (sem WhatsApp real)
    path("simulador/", views.simulador, name="simulador"),
    path("simulador/msg/", views.simulador_msg, name="simulador_msg"),
    path("simulador/reset/", views.simulador_reset, name="simulador_reset"),
    path("simulador/pagar/", views.simulador_pagar, name="simulador_pagar"),
]
