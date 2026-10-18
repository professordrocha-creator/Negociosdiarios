"""Registro do app pagamentos no Django."""

from django.apps import AppConfig


class PagamentosConfig(AppConfig):
    """Configuração do app pagamentos."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pagamentos"
    verbose_name = "Faturas e pagamentos"  # nome do menu no admin
