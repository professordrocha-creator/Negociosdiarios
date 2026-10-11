"""Tarefas Celery do app anunciantes: processamento das imagens da loja."""

from celery import shared_task

from anunciantes.models import Anunciante
from anunciantes.services import processar_imagem_loja as processar


@shared_task
def processar_imagem_loja(anunciante_id: int, tipo: str) -> bool:
    """Gera os WebP do logo ou da capa (fora da requisição: imagem grande não trava a página)."""
    anunciante = Anunciante.objects.filter(pk=anunciante_id).first()
    return processar(anunciante, tipo) if anunciante else False
