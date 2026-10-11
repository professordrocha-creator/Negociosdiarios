"""App do Celery: tarefas assíncronas e agendadas (e-mails, imagens, expiração, cobranças).

A configuração vem do settings do Django (variáveis `CELERY_*`), e as tarefas são
descobertas sozinhas no `tasks.py` de cada app. Fila e resultados ficam no Redis.
Em dev o container `worker` roda o worker e o agendador (beat) juntos.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("negocios_diarios")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
