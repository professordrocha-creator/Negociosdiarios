"""Armazenamento PRIVADO dos comprovantes de pagamento (docs/LGPD.md, docs/SEGURANCA.md).

Comprovante tem nome, banco e às vezes parte do CPF de quem pagou: nunca fica na mídia pública
(`/media/` em dev, domínio público do R2 em produção). Só sai por views que conferem quem pede
(o dono da fatura ou a equipe com permissão), nunca por URL direta.

- ARMAZENAMENTO=local: pasta `privado/` ao lado da `media/` (fora do que o Django serve em /media/).
- ARMAZENAMENTO=s3: outro bucket, sem domínio público e com URLs assinadas (S3_BUCKET_PRIVADO).
"""

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.utils.functional import cached_property


class PastaPrivada(FileSystemStorage):
    """Pasta `privado/` irmã da MEDIA_ROOT. Sem URL pública (`url()` não é usado: as views servem)."""

    @cached_property
    def base_location(self) -> str:
        """Recalculada quando a MEDIA_ROOT muda (o storage limpa o cache; os testes usam pasta temporária)."""
        return str(Path(settings.MEDIA_ROOT).parent / "privado")

    def url(self, name: str) -> str:
        """Nunca há endereço direto: o arquivo sai só pela view que confere a permissão."""
        raise ValueError("Arquivo privado: use a view do comprovante.")


def armazenamento_privado():
    """O storage "privado" do settings (callable: a migration não guarda o caminho nem o bucket)."""
    return storages["privado"]
