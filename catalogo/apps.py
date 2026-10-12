"""Registro do app catalogo no Django."""

from django.apps import AppConfig


class CatalogoConfig(AppConfig):
    """Configuração do app catalogo (marcas, modelos e versões de veículos da Tabela FIPE)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogo"
    verbose_name = "Catálogo de veículos"
