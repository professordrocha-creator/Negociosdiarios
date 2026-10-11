"""Configuração do projeto Django (settings, URLs raiz, WSGI/ASGI e app do Celery)."""

# Carrega o app do Celery junto com o Django: assim `tarefa.delay()` usa a configuração
# do projeto (fila no Redis) em qualquer lugar do código.
from config.celery import app as celery_app

__all__ = ("celery_app",)
