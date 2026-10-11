"""Rotas do app anunciantes: cadastro, confirmação de e-mail, painel e vitrine das lojas."""

from django.urls import path

from anunciantes import views

app_name = "anunciantes"

urlpatterns = [
    path("cadastro/", views.cadastro, name="cadastro"),
    path("cadastro/obrigado/", views.cadastro_obrigado, name="cadastro_obrigado"),
    path("cadastro/confirmar/reenviar/", views.reenviar_confirmacao_view, name="reenviar_confirmacao"),
    path("cadastro/confirmar/<str:token>/", views.confirmar_email_view, name="confirmar_email"),
    path("painel/", views.painel, name="painel"),
    path("painel/loja/", views.painel_loja, name="painel_loja"),
    path("lojas/", views.lojas, name="lojas"),
    path("loja/<slug:slug>/", views.loja, name="loja"),
    path("loja/<slug:slug>/whatsapp/", views.loja_whatsapp, name="loja_whatsapp"),
]
