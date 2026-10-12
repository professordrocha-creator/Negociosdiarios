"""Tarefas Celery do app publicidade."""

from celery import shared_task

from publicidade.models import Banner
from publicidade.services import processar_banner as processar
from publicidade.services import rotina_de_publicidade as rotina


@shared_task
def processar_banner(banner_id: int) -> bool:
    """Gera os WebP da peça enviada no admin (tamanho da Configuracao, sem EXIF) e apaga o original."""
    banner = Banner.objects.filter(pk=banner_id).first()
    return processar(banner) if banner else False


@shared_task
def rotina_de_publicidade() -> dict[str, int]:
    """Diária (beat): encerra campanhas que passaram do fim e avisa a equipe das que terminam em breve."""
    return rotina()
