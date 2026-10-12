"""Rotas do app pagamentos (painel do anunciante)."""

from django.urls import path

from pagamentos import views

app_name = "pagamentos"

urlpatterns = [
    path("painel/faturas/", views.faturas, name="faturas"),
    path("painel/faturas/<str:codigo>/ja-paguei/", views.ja_paguei, name="ja_paguei"),
    path("painel/faturas/<str:codigo>/comprovante/", views.comprovante, name="comprovante"),
    # Fatura de publicidade (patrocinador sem login): link com token aleatório enviado por e-mail.
    path("fatura/<uuid:token>/", views.fatura_publica, name="fatura_publica"),
    path("fatura/<uuid:token>/ja-paguei/", views.fatura_publica_ja_paguei, name="fatura_publica_ja_paguei"),
]
