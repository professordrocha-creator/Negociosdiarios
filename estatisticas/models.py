"""Modelo do app estatisticas: contagem por anúncio e por dia. Só números: nada de IP nem de visitante."""

from django.db import models

from anuncios.models import Anuncio
from core.models import MarcaDemo


class EstatisticaDiaria(MarcaDemo):
    """Visualizações e cliques no WhatsApp de um anúncio num dia (fuso America/Cuiaba).

    A deduplicação ("1 por visitante por dia") acontece no cache, com um hash de sal diário que
    some no fim do dia (`estatisticas.services`); aqui ficam só os totais.
    """

    anuncio = models.ForeignKey(Anuncio, on_delete=models.CASCADE, related_name="estatisticas")
    dia = models.DateField("dia")
    visualizacoes = models.PositiveIntegerField("visualizações", default=0)
    cliques_whatsapp = models.PositiveIntegerField("cliques no WhatsApp", default=0)

    class Meta:
        verbose_name = "estatística diária"
        verbose_name_plural = "estatísticas diárias"
        ordering = ["-dia"]
        constraints = [models.UniqueConstraint(fields=["anuncio", "dia"], name="estatistica_unica_por_dia")]

    def __str__(self) -> str:
        """Ex.: 'ND-IM-00012 em 2026-10-11'."""
        return f"{self.anuncio.codigo} em {self.dia:%Y-%m-%d}"
