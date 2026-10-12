"""URLs da busca: /imoveis/ e /veiculos/ (todas as cidades) e por cidade, sempre com a UF; o JSON do mapa
(mesmos filtros, `mapa.json` no fim) e os cartões que abrem ao clicar num marcador."""

from django.urls import path

from busca import views

app_name = "busca"

urlpatterns = [
    path("imoveis/", views.busca, {"categoria": "imoveis"}, name="imoveis"),
    path("imoveis/mapa.json", views.mapa, {"categoria": "imoveis"}, name="imoveis_mapa"),
    path("imoveis/<slug:uf>/<slug:cidade>/", views.busca, {"categoria": "imoveis"}, name="imoveis_cidade"),
    path(
        "imoveis/<slug:uf>/<slug:cidade>/mapa.json",
        views.mapa,
        {"categoria": "imoveis"},
        name="imoveis_cidade_mapa",
    ),
    path("veiculos/", views.busca, {"categoria": "veiculos"}, name="veiculos"),
    path("veiculos/mapa.json", views.mapa, {"categoria": "veiculos"}, name="veiculos_mapa"),
    path("veiculos/<slug:uf>/<slug:cidade>/", views.busca, {"categoria": "veiculos"}, name="veiculos_cidade"),
    path(
        "veiculos/<slug:uf>/<slug:cidade>/mapa.json",
        views.mapa,
        {"categoria": "veiculos"},
        name="veiculos_cidade_mapa",
    ),
    path("mapa/cartao/anuncio/<str:codigo>/", views.cartao_anuncio, name="cartao_anuncio"),
    path("mapa/cartao/loja/<slug:slug>/", views.cartao_loja, name="cartao_loja"),
]
