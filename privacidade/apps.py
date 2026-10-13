"""Registro do app privacidade no Django."""

from django.apps import AppConfig


class PrivacidadeConfig(AppConfig):
    """Configuração do app privacidade."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "privacidade"
    verbose_name = "Privacidade (LGPD)"
