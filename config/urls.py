"""URLs raiz do projeto.

Os webhooks (bot e pagamentos) serão plugados aqui nas próximas fases.
"""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

# Os "índices de app" do admin (ex.: /admin/cardapio/) são telas pouco úteis e
# confusas. Redirecionamos para o painel. Devem vir ANTES do include do admin.
_app_index = lambda request, *a, **k: redirect("admin:index")

urlpatterns = [
    path("admin/cardapio/", _app_index),
    path("admin/pedidos/", _app_index),
    path("admin/auth/", _app_index),
    path("admin/", admin.site.urls),
    path("", include("pagamentos.urls")),  # /webhook/asaas/
    path("", include("bot.urls")),         # /webhook/whatsapp/
    path("", include("cardapio.urls")),    # assistente de produto
    path("", include("pedidos.urls")),     # perfis de fluxo / editor de mensagens
]

# Customização leve do título do Admin (painel do lojista).
admin.site.site_header = "Big Kilo · Comida Caseira"
admin.site.site_title = "Big Kilo"
admin.site.index_title = "Gestão de Cardápio e Pedidos"
