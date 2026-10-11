"""Configuração do app admin do projeto.

Fica separado de `config/admin_site.py` de propósito: este módulo é importado
enquanto o Django ainda carrega os apps, então não pode importar modelos nem
formulários (o django-otp importa). O site é indicado por texto e carregado depois.
"""

from django.contrib.admin.apps import AdminConfig


class AdminConfigND(AdminConfig):
    """Substitui `django.contrib.admin` no INSTALLED_APPS e define o site com 2FA como padrão."""

    default_site = "config.admin_site.AdminSiteND"
