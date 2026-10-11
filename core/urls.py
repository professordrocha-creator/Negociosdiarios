"""Rotas do app core."""

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("sobre/", views.sobre, name="sobre"),
    path("saude/", views.saude, name="saude"),
    path("favicon.ico", views.favicon, name="favicon"),
]
