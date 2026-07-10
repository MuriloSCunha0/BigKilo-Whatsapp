from django.urls import path

from . import views

app_name = "bot"

urlpatterns = [
    path("webhook/whatsapp/", views.webhook_whatsapp, name="webhook_whatsapp"),
    # Simulador de testes (sem WhatsApp real)
    path("simulador/", views.simulador, name="simulador"),
    path("simulador/msg/", views.simulador_msg, name="simulador_msg"),
    path("simulador/reset/", views.simulador_reset, name="simulador_reset"),
    path("simulador/pagar/", views.simulador_pagar, name="simulador_pagar"),
]
