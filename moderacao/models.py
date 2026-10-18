"""Modelos do app moderacao: denúncia de anúncio (Sprint 7B parte 2; docs/LGPD.md, docs/SEGURANCA.md).

Qualquer visitante denuncia, sem login. A equipe aceita (pausa ou remove o anúncio e avisa o anunciante) ou
descarta. O anunciante nunca vê quem denunciou: o e-mail (opcional) e a origem só aparecem para a equipe.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anuncios.models import Anuncio
from core.models import MarcaDemo


class Denuncia(MarcaDemo):
    """Uma denúncia de um anúncio.

    `origem` é um resumo (hash) do visitante NAQUELE DIA (IP + navegador + sal aleatório do dia, guardado
    só no cache por 2 dias, como nas estatísticas): serve para limitar envios por dia e contar origens
    diferentes, mas não dá para voltar ao IP nem ligar dias diferentes. Nenhum IP é gravado.
    """

    class Motivo(models.TextChoices):
        GOLPE = "golpe", "Golpe ou fraude"
        VENDIDO = "vendido", "Já foi vendido ou alugado"
        FALSO = "falso", "Preço ou dados falsos"
        IMPROPRIO = "improprio", "Conteúdo impróprio"
        DADOS_TERCEIROS = "dados_terceiros", "Uso de dados de terceiros (fotos, documentos, pessoas)"
        OUTRO = "outro", "Outro"

    class Situacao(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ACEITA = "aceita", "Aceita"
        DESCARTADA = "descartada", "Descartada"

    class Acao(models.TextChoices):
        PAUSAR = "pausar", "Anúncio pausado"
        REMOVER = "remover", "Anúncio removido"

    anuncio = models.ForeignKey(
        Anuncio, on_delete=models.PROTECT, related_name="denuncias", verbose_name="anúncio"
    )
    motivo = models.CharField("motivo", max_length=16, choices=Motivo.choices)
    texto = models.TextField("detalhes", max_length=1000, blank=True)
    email = models.EmailField(
        "e-mail de quem denunciou",
        blank=True,
        help_text="Opcional. Só para a equipe dar retorno; nunca ao anunciante.",
    )
    origem = models.CharField("origem (resumo do dia)", max_length=32, db_index=True, editable=False)
    situacao = models.CharField(
        "situação", max_length=10, choices=Situacao.choices, default=Situacao.PENDENTE, db_index=True
    )
    acao = models.CharField("o que foi feito", max_length=8, choices=Acao.choices, blank=True)
    motivo_decisao = models.TextField("motivo da decisão", blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="decidido por",
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)
    criado_em = models.DateTimeField("recebida em", default=timezone.now, editable=False, db_index=True)

    history = HistoricalRecords(verbose_name="histórico da denúncia", excluded_fields=["origem"])

    class Meta:
        verbose_name = "denúncia"
        verbose_name_plural = "denúncias"
        ordering = ["situacao", "criado_em"]

    def __str__(self) -> str:
        """Ex.: 'Golpe ou fraude · ND-IM-00012'."""
        return f"{self.get_motivo_display()} · {self.anuncio.codigo}"
