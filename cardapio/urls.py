from django.urls import path

from . import views

app_name = "cardapio"

urlpatterns = [
    path("cardapio/produto/assistente/", views.wizard, name="wizard"),
    path("cardapio/produto/assistente/<int:produto_id>/", views.wizard_carregar, name="wizard_carregar"),
    path("cardapio/produto/assistente/salvar/", views.wizard_salvar, name="wizard_salvar"),
    path("cardapio/categoria/assistente/salvar/", views.categoria_salvar, name="categoria_salvar"),
    path("cardapio/categoria/assistente/<int:categoria_id>/", views.categoria_carregar, name="categoria_carregar"),
    path("cardapio/cardapio/assistente/salvar/", views.cardapio_salvar, name="cardapio_salvar"),
    path("cardapio/cardapio/assistente/<int:cardapio_id>/", views.cardapio_carregar, name="cardapio_carregar"),
    path("cardapio/promocao/assistente/salvar/", views.promocao_salvar, name="promocao_salvar"),
    path("cardapio/promocao/assistente/<int:produto_id>/", views.promocao_carregar, name="promocao_carregar"),
]
