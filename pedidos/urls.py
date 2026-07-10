from django.urls import path

from . import views

app_name = "pedidos_extra"

urlpatterns = [
    path("pedidos/perfilfluxo/assistente/salvar/", views.perfilfluxo_salvar, name="perfilfluxo_salvar"),
    path("pedidos/areaentrega/assistente/salvar/", views.area_salvar, name="area_salvar"),
    path("pedidos/fluxo/<int:perfil_id>/editar/", views.fluxo_editar, name="fluxo_editar"),
    path("pedidos/fluxo/<int:perfil_id>/editar/salvar/", views.fluxo_editar_salvar, name="fluxo_editar_salvar"),
    path("pedidos/contato/<int:cliente_id>/mensagens/", views.contato_mensagens, name="contato_mensagens"),
    path("pedidos/contato/<int:cliente_id>/mensagens/salvar/", views.contato_mensagens_salvar, name="contato_mensagens_salvar"),
    path("pedidos/sessao/<str:telefone>/reiniciar/", views.sessao_reiniciar, name="sessao_reiniciar"),
    path("pedidos/sessao/<str:telefone>/enviar/", views.sessao_enviar_mensagem, name="sessao_enviar"),
    # API do agente de impressão (autenticada por token)
    path("pedidos/impressao/pendentes/", views.impressao_pendentes, name="impressao_pendentes"),
    path("pedidos/impressao/marcar/", views.impressao_marcar, name="impressao_marcar"),
]

