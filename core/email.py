"""Backend de e-mail do projeto: todo `send_mail()` vai para a fila do Celery.

Configurado em `EMAIL_BACKEND`. A página só coloca o e-mail na fila (milissegundos)
e segue; o worker envia de verdade com `EMAIL_BACKEND_REAL` e tenta de novo se o
servidor de e-mail falhar. Vale para tudo, inclusive o código de login do admin.
"""

from django.core.mail.backends.base import BaseEmailBackend

from core.services import email_para_fila
from core.tasks import enviar_email


class CeleryEmailBackend(BaseEmailBackend):
    """Coloca cada e-mail na fila (`core.tasks.enviar_email`) em vez de enviar na hora."""

    def send_messages(self, email_messages) -> int:
        """Enfileira os e-mails e devolve quantos entraram na fila.

        Se o Redis estiver fora do ar, o erro sobe (a menos que `fail_silently`),
        para quem chamou poder avisar o usuário.
        """
        enfileirados = 0
        for mensagem in email_messages:
            try:
                enviar_email.delay(email_para_fila(mensagem))
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                enfileirados += 1
        return enfileirados
