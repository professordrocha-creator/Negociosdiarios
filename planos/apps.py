"""Registro do app planos no Django."""

from django.apps import AppConfig


class PlanosConfig(AppConfig):
    """Configuração do app planos."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "planos"
    verbose_name = "Planos e assinaturas"
