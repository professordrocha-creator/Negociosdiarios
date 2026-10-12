"""Registro do app estatisticas no Django."""

from django.apps import AppConfig


class EstatisticasConfig(AppConfig):
    """Configuração do app estatisticas (visualizações e cliques no WhatsApp, sem dado pessoal)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "estatisticas"
    verbose_name = "Estatísticas"
