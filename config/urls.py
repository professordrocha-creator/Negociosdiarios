"""URLs raiz do projeto. Cada app inclui as suas próprias rotas."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin em endereço secreto (ADMIN_URL no .env) e com 2FA (config/admin_site.py).
    # Não existe rota /admin/: quem tentar recebe 404, como qualquer página inexistente.
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
]
