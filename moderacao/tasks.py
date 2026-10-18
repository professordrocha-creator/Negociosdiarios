"""Tarefas Celery do app moderacao."""

from celery import shared_task

from moderacao.services import limpar_denuncias_antigas as limpar


@shared_task
def limpar_denuncias_antigas() -> int:
    """Diária (beat, 4h15): apaga e-mail e detalhes das denúncias decididas há mais que a guarda."""
    return limpar()
