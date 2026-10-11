"""Tarefas Celery do app planos."""

from celery import shared_task

from planos.services import processar_atrasos


@shared_task
def verificar_atrasos() -> int:
    """Diária (beat, 6h): assinaturas vencidas além da carência viram "em atraso"."""
    return processar_atrasos()
