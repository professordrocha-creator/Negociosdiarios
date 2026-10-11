"""Rotas do app anunciantes (cadastro, confirmação de e-mail e painel; a vitrine chega na Sprint 2)."""

from django.urls import path

from anunciantes import views

app_name = "anunciantes"

urlpatterns = [
    path("cadastro/", views.cadastro, name="cadastro"),
    path("cadastro/obrigado/", views.cadastro_obrigado, name="cadastro_obrigado"),
    path("cadastro/confirmar/reenviar/", views.reenviar_confirmacao_view, name="reenviar_confirmacao"),
    path("cadastro/confirmar/<str:token>/", views.confirmar_email_view, name="confirmar_email"),
    path("painel/", views.painel, name="painel"),
]
