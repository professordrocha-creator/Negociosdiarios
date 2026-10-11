"""Registro do app anuncios no Django."""

from django.apps import AppConfig


class AnunciosConfig(AppConfig):
    """Configuração do app anuncios; liga os sinais do app planos (atraso pausa, pagamento reativa)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "anuncios"
    verbose_name = "Anúncios"

    def ready(self) -> None:
        """Conecta os receptores de `planos.sinais` (import aqui: os apps já estão carregados)."""
        from anuncios import receptores  # noqa: F401
