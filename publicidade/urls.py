"""Rotas do app publicidade."""

from django.urls import path

from publicidade import views

app_name = "publicidade"

urlpatterns = [
    path("publicidade/clique/<int:pk>/", views.clique, name="clique"),
]
