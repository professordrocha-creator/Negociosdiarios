"""Registro do app anunciantes no Django."""

from django.apps import AppConfig


class AnunciantesConfig(AppConfig):
    """Configuração do app anunciantes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "anunciantes"
    verbose_name = "Anunciantes"
