"""URLs dos anúncios: página pública (/anuncio/<codigo>-<slug>/), WhatsApp e painel (/painel/anuncios/...)."""

from django.urls import path, re_path

from anuncios import views, views_publicas

app_name = "anuncios"

# Código público: ND-IM-00001 (ou ND-VE- na Sprint 4); o slug é opcional e o antigo redireciona.
CODIGO = r"(?P<codigo>[Nn][Dd]-[A-Za-z]{2}-\d{5,})"

urlpatterns = [
    re_path(rf"^anuncio/{CODIGO}/whatsapp/$", views_publicas.whatsapp, name="whatsapp"),
    re_path(rf"^anuncio/{CODIGO}(?:-(?P<slug>[-a-z0-9]*))?/$", views_publicas.publico, name="publico"),
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
