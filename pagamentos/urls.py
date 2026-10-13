"""Rotas do app pagamentos (painel do anunciante)."""

from django.urls import path, re_path

from pagamentos import views

app_name = "pagamentos"

urlpatterns = [
    path("painel/faturas/", views.faturas, name="faturas"),
    path("painel/faturas/<str:codigo>/ja-paguei/", views.ja_paguei, name="ja_paguei"),
    path("painel/faturas/<str:codigo>/comprovante/", views.comprovante, name="comprovante"),
    # Fatura de publicidade (patrocinador sem login): link com token aleatório enviado por e-mail.
    # Só o formato do token (base64 de URL, 43+ caracteres): qualquer outra coisa nem chega à view.
    re_path(r"^fatura/(?P<token>[A-Za-z0-9_-]{43,64})/$", views.fatura_publica, name="fatura_publica"),
    re_path(
        r"^fatura/(?P<token>[A-Za-z0-9_-]{43,64})/ja-paguei/$",
        views.fatura_publica_ja_paguei,
        name="fatura_publica_ja_paguei",
    ),
]
