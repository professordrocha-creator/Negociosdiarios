"""Tarefas Celery do app core: exemplo/batimento e envio de e-mail.

Regra do projeto: e-mail **sempre** sai por aqui (fila do Celery), nunca dentro da
requisição web. O backend `core.email.CeleryEmailBackend` transforma cada
`send_mail()` do Django em uma chamada a `enviar_email`.
"""

import logging
from smtplib import SMTPException

from celery import shared_task
from django.utils import timezone

from core.services import enviar_email_agora

logger = logging.getLogger(__name__)


@shared_task
def batimento() -> str:
    """Tarefa de exemplo: prova que o worker e o agendador (beat) estão vivos.

    O beat a agenda a cada 5 minutos (CELERY_BEAT_SCHEDULE) e o comando
    `testar_celery` a dispara na hora. Só registra a hora no log e a devolve.
    """
    agora = timezone.localtime().isoformat(timespec="seconds")
    logger.info("Batimento do Celery: worker funcionando (%s).", agora)
    return agora


@shared_task(
    autoretry_for=(SMTPException, OSError),  # servidor de e-mail fora do ar, rede, recusa temporária
    retry_backoff=30,  # espera ~30 s, 1, 2, 4 e 8 min (com variação): ~15 min de tentativas
    retry_backoff_max=600,
    max_retries=5,
)
def enviar_email(dados: dict) -> int:
    """Envia de verdade um e-mail que a página colocou na fila. Tenta de novo se falhar.

    `dados` vem de `core.services.email_para_fila`. O log nunca leva endereços (LGPD).
    """
    enviados = enviar_email_agora(dados)
    logger.info("E-mail enviado (%s destinatário(s)).", len(dados.get("to", [])))
    return enviados
