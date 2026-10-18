"""Registro do app moderacao no Django."""

from django.apps import AppConfig


class ModeracaoConfig(AppConfig):
    """Configuração do app moderacao."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "moderacao"
    verbose_name = "Moderação"
