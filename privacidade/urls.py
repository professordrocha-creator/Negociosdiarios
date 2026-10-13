"""Rotas do app privacidade (painel). Termos e Política ficam em /termos/ e /privacidade/ (core.urls)."""

from django.urls import path

from privacidade import views

app_name = "privacidade"

urlpatterns = [
    path("painel/termos-atualizados/", views.aceitar, name="aceitar"),
    path("painel/meus-dados/", views.meus_dados, name="meus_dados"),
    path("painel/meus-dados/baixar/", views.baixar, name="baixar"),
    path("painel/meus-dados/excluir/", views.excluir, name="excluir"),
]
