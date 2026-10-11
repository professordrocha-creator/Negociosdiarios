"""URLs do painel de anúncios (/painel/anuncios/...). A página pública do anúncio chega na Parte B."""

from django.urls import path

from anuncios import views

app_name = "anuncios"

urlpatterns = [
    path("painel/anuncios/novo/", views.novo, name="novo"),
    path("painel/anuncios/<str:codigo>/editar/", views.editar, name="editar"),
    path("painel/anuncios/<str:codigo>/editar/localizacao/", views.localizacao, name="localizacao"),
    path("painel/anuncios/<str:codigo>/editar/fotos/", views.fotos, name="fotos"),
    path("painel/anuncios/<str:codigo>/editar/fotos/ordem/", views.ordenar_fotos, name="ordenar_fotos"),
    path(
        "painel/anuncios/<str:codigo>/editar/fotos/<int:foto_id>/excluir/",
        views.excluir_foto,
        name="excluir_foto",
    ),
    path("painel/anuncios/<str:codigo>/editar/revisao/", views.revisao, name="revisao"),
    path("painel/anuncios/<str:codigo>/<str:nome>/", views.acao, name="acao"),
]
