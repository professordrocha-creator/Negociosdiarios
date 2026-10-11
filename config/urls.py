"""URLs raiz do projeto. Cada app inclui as suas próprias rotas."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin em URL não óbvia + 2FA entram na etapa 5 da Sprint 0 (ver docs/SEGURANCA.md).
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
