"""Tarefas Celery do app privacidade."""

from celery import shared_task

from privacidade.services import limpar_dados_vencidos as limpar


@shared_task
def limpar_dados_vencidos() -> int:
    """Diária (beat, 4h): apaga comprovantes e anotações de faturas além da guarda fiscal."""
    return limpar()
