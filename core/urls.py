"""Rotas do app core."""

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("sobre/", views.sobre, name="sobre"),
    # Institucionais (docs/TELAS.md §2). Os textos legais são rascunhos até a revisão do advogado.
    path("privacidade/", views.privacidade, name="privacidade"),
    path("termos/", views.termos, name="termos"),
    path("cookies/", views.cookies, name="cookies"),
    path("planos/", views.planos_view, name="planos"),
    path("anuncie/", views.anuncie, name="anuncie"),
    path("contato/", views.contato, name="contato"),
    # Ainda em construção: "Em breve" em vez de 404. Cada sprint troca a sua rota pela de verdade.
    path("imoveis/", views.em_breve, {"pagina": "imoveis"}, name="imoveis"),
    path("veiculos/", views.em_breve, {"pagina": "veiculos"}, name="veiculos"),
    path("lojas/", views.em_breve, {"pagina": "lojas"}, name="lojas"),
    path("denunciar/", views.em_breve, {"pagina": "denunciar"}, name="denunciar"),
    path("saude/", views.saude, name="saude"),
    path("favicon.ico", views.favicon, name="favicon"),
]
