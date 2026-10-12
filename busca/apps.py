"""Registro do app busca no Django."""

from django.apps import AppConfig


class BuscaConfig(AppConfig):
    """Configuração do app busca (páginas /imoveis/ e /veiculos/ com filtros e busca por texto)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "busca"
    verbose_name = "Busca"
