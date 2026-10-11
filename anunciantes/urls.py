"""Rotas do app anunciantes (painel do anunciante; a vitrine /loja/<slug>/ chega na Sprint 2)."""

from django.urls import path

from anunciantes import views

app_name = "anunciantes"

urlpatterns = [
    path("painel/", views.painel, name="painel"),
]
