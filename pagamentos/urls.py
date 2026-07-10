from django.urls import path

from . import views

app_name = "pagamentos"

urlpatterns = [
    path("webhook/asaas/", views.webhook_asaas, name="webhook_asaas"),
]
