"""Receptores dos sinais do app planos (conectados em AnunciosConfig.ready).

Assinatura em atraso → anúncios publicados ficam pausados (nunca apagados).
Pagamento registrado → os pausados por atraso voltam ao ar.
"""

from django.dispatch import receiver

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
