"""Tarefas Celery do app pagamentos."""

from celery import shared_task

from pagamentos.services import rotina_de_cobranca as rotina


@shared_task
def rotina_de_cobranca() -> dict[str, int]:
    """Diária (beat, 6h): gera faturas, marca vencidas, põe em atraso (pausa) e manda os lembretes."""
    return rotina()
