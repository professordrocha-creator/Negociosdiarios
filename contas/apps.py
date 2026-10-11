"""Registro do app contas no Django."""

from django.apps import AppConfig


class ContasConfig(AppConfig):
    """Configuração do app contas."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "contas"
    verbose_name = "Contas"
