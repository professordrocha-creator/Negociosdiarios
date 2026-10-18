"""Rotas do app moderacao."""

from django.urls import path

from moderacao import views

app_name = "moderacao"

urlpatterns = [
    path("denunciar/", views.denunciar, name="denunciar"),
    path("como-denunciar/", views.como_denunciar, name="como_denunciar"),
]
