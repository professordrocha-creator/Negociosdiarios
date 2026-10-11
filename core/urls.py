"""Rotas do app core."""

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("saude/", views.saude, name="saude"),
]
