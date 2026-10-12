"""URLs da busca: /imoveis/ e /veiculos/ (todas as cidades) e por cidade, sempre com a UF."""

from django.urls import path

from busca import views

app_name = "busca"

urlpatterns = [
    path("imoveis/", views.busca, {"categoria": "imoveis"}, name="imoveis"),
    path("imoveis/<slug:uf>/<slug:cidade>/", views.busca, {"categoria": "imoveis"}, name="imoveis_cidade"),
    path("veiculos/", views.busca, {"categoria": "veiculos"}, name="veiculos"),
    path("veiculos/<slug:uf>/<slug:cidade>/", views.busca, {"categoria": "veiculos"}, name="veiculos_cidade"),
]
