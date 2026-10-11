"""Rotas do app planos (painel do anunciante)."""

from django.urls import path

from planos import views

app_name = "planos"

urlpatterns = [
    path("painel/plano/", views.meu_plano, name="meu_plano"),
    path("painel/plano/escolher-anuncios/", views.escolher_anuncios, name="escolher_anuncios"),
]
