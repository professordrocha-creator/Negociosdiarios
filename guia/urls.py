"""URLs públicas do app guia (incluídas em /guia/; docs/GUIA.md §6). Todas com a UF nas páginas de cidade.

Os caminhos fixos (aceite, empresa, contato) vêm antes dos de cidade, e a UF só casa com 2 letras.
"""

from django.urls import path, re_path

from guia import views

app_name = "guia"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("aceite/<str:token>/", views.aceite, name="aceite"),
    path("empresa/<slug:slug>/", views.empresa, name="empresa"),
    path("pedido/<slug:slug>/", views.pedido, name="pedido"),
    path("contato/<int:pk>/whatsapp/", views.contato_whatsapp, name="whatsapp"),
    path("contato/<int:pk>/telefone/", views.contato_telefone, name="telefone"),
    re_path(r"^(?P<uf>[a-z]{2})/(?P<cidade>[-a-z0-9]+)/$", views.cidade, name="cidade"),
    re_path(
        r"^(?P<uf>[a-z]{2})/(?P<cidade>[-a-z0-9]+)/(?P<categoria>[-a-z0-9]+)/$",
        views.categoria,
        name="categoria",
    ),
]
