"""Tarefas Celery do app anuncios: processamento das fotos e expiração diária."""

from celery import shared_task

from anuncios.models import Foto
from anuncios.services import expirar_vencidos
from anuncios.services import processar_foto as processar


@shared_task
def processar_foto(foto_id: int) -> bool:
    """Gera os WebP da foto (fora da requisição: foto grande do celular não trava a página)."""
    foto = Foto.objects.filter(pk=foto_id).first()
    return processar(foto) if foto else False


@shared_task
def expirar_anuncios() -> int:
    """Celery beat, todo dia: anúncios com prazo vencido saem do ar (expirados, nunca apagados)."""
    return expirar_vencidos()
