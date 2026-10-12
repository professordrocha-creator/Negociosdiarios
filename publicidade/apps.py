"""Registro do app publicidade no Django."""

from django.apps import AppConfig


class PublicidadeConfig(AppConfig):
    """Configuração do app publicidade."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "publicidade"
    verbose_name = "Publicidade"
