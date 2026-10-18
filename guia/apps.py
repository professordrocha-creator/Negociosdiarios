"""Registro do app guia (Guia de Negócios; docs/GUIA.md) no Django."""

from django.apps import AppConfig


class GuiaConfig(AppConfig):
    """Configuração do app guia. O `ready` liga a trava de categorias do perfil (guia/signals.py)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "guia"
    verbose_name = "Guia de Negócios"

    def ready(self) -> None:
        """Importa os sinais (máximo de categorias; regulamentada sem frase), valendo em qualquer caminho."""
        from guia import signals  # noqa: F401
