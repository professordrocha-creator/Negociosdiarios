"""Rotas do app pagamentos (painel do anunciante)."""

from django.urls import path

from pagamentos import views

app_name = "pagamentos"

urlpatterns = [
    path("painel/faturas/", views.faturas, name="faturas"),
    path("painel/faturas/<str:codigo>/ja-paguei/", views.ja_paguei, name="ja_paguei"),
    path("painel/faturas/<str:codigo>/comprovante/", views.comprovante, name="comprovante"),
]
