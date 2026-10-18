"""Tarefas Celery do app guia: rotina diária (termo novo, pausa de quem passou do prazo e limpeza da LGPD)."""

from celery import shared_task

from guia import services


@shared_task
def rotina_do_guia() -> dict[str, int]:
    """Roda `services.rotina_do_guia` (agendada no beat; ver config/settings.py)."""
    return services.rotina_do_guia()
