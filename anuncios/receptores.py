"""Receptores de sinais (conectados em AnunciosConfig.ready).

- planos: assinatura em atraso → anúncios publicados ficam pausados (nunca apagados);
  pagamento registrado → os pausados por atraso voltam ao ar.
- índice de busca: gravou o anúncio ou a ficha (imóvel/veículo) → recalcula `busca`/`texto_busca`.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from anuncios import indice
from anuncios.models import Anuncio, AnuncioEmModeracao, DetalheImovel, DetalheVeiculo
from anuncios.services import pausar_por_atraso, reativar_apos_pagamento
from planos.sinais import assinatura_em_atraso, assinatura_regularizada


@receiver(assinatura_em_atraso, dispatch_uid="anuncios_pausar_por_atraso")
def ao_entrar_em_atraso(sender, assinatura, **kwargs) -> None:
    """Pausa os anúncios publicados da loja."""
    pausar_por_atraso(assinatura.anunciante)


@receiver(assinatura_regularizada, dispatch_uid="anuncios_reativar_apos_pagamento")
def ao_regularizar(sender, assinatura, **kwargs) -> None:
    """Reativa os anúncios que o atraso pausou."""
    reativar_apos_pagamento(assinatura.anunciante)


def _reindexar(anuncio_id: int) -> None:
    """Recalcula o índice de busca lendo o anúncio com cidade, bairro e ficha."""
    anuncio = (
        Anuncio.objects.select_related("cidade", "bairro", "imovel", "veiculo__versao__modelo__marca")
        .filter(pk=anuncio_id)
        .first()
    )
    if anuncio is not None:
        indice.atualizar(anuncio)


@receiver(post_save, sender=Anuncio, dispatch_uid="anuncios_indice_anuncio")
@receiver(post_save, sender=AnuncioEmModeracao, dispatch_uid="anuncios_indice_moderacao")
def ao_gravar_anuncio(sender, instance, raw=False, **kwargs) -> None:
    """Título, descrição ou cidade podem ter mudado."""
    if not raw:
        _reindexar(instance.pk)


@receiver(post_save, sender=DetalheImovel, dispatch_uid="anuncios_indice_imovel")
@receiver(post_save, sender=DetalheVeiculo, dispatch_uid="anuncios_indice_veiculo")
def ao_gravar_ficha(sender, instance, raw=False, **kwargs) -> None:
    """Tipo, marca ou modelo podem ter mudado."""
    if not raw:
        _reindexar(instance.anuncio_id)
