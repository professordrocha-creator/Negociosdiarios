"""Modelos do app planos: Plano, Assinatura e pedido de troca de plano (docs/ARQUITETURA.md §4 e §5).

Preços e limites ficam no banco (editáveis no admin), nunca fixos no código. Dinheiro em
DecimalField. Assinatura e plano guardam histórico (django-simple-history).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.models import Anunciante
from core.models import MarcaDemo


class Plano(models.Model):
    """Plano de assinatura: quantos anúncios ficam ativos ao mesmo tempo e quanto custa."""

    nome = models.CharField("nome", max_length=40, unique=True)
    slug = models.SlugField("identificador", max_length=40, unique=True)
    limite_anuncios = models.PositiveIntegerField(
        "limite de anúncios",
        help_text="Anúncios publicados + em análise ao mesmo tempo. Pausados não contam.",
    )
    preco_mensal = models.DecimalField(
        "preço mensal (R$)", max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    preco_anual = models.DecimalField(
        "preço anual (R$)", max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    ativo = models.BooleanField(
        "à venda", default=True, help_text="Desmarcado, some de /planos/ (quem já tem, continua)."
    )
    ordem = models.PositiveSmallIntegerField("ordem", default=0, help_text="Menor aparece primeiro.")

    history = HistoricalRecords(verbose_name="histórico do plano")

    class Meta:
        verbose_name = "plano"
        verbose_name_plural = "planos"
        ordering = ["ordem", "limite_anuncios"]

    def __str__(self) -> str:
        """Ex.: 'Profissional (25 anúncios)'."""
        return f"{self.nome} ({self.limite_anuncios} anúncios)"

    @property
    def economia_anual(self) -> Decimal:
        """Quanto o anual economiza frente a 12 mensalidades."""
        return self.preco_mensal * 12 - self.preco_anual

    @property
    def meses_pagos_no_anual(self) -> int:
        """O anual equivale a quantas mensalidades (ex.: 10)."""
        return round(self.preco_anual / self.preco_mensal) if self.preco_mensal else 12

    @property
    def meses_gratis(self) -> int:
        """Meses de graça no anual."""
        return 12 - self.meses_pagos_no_anual


class Periodicidade(models.TextChoices):
    """Como a assinatura é paga."""

    MENSAL = "mensal", "Mensal"
    ANUAL = "anual", "Anual"


class Assinatura(MarcaDemo):
    """Plano atual de um anunciante (uma por anunciante) e a situação do pagamento.

    `ativa`: anúncios no ar dentro do limite. `em_atraso`: venceu e passou a carência
    (Configuracao.carencia_dias): anúncios pausados, nunca apagados, até o pagamento.
    `cancelada`: sem plano. As trocas de situação disparam sinais (planos.sinais) que o app
    de anúncios usa para pausar e reativar (Sprint 3).
    """

    class Situacao(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        EM_ATRASO = "em_atraso", "Em atraso"
        CANCELADA = "cancelada", "Cancelada"

    anunciante = models.OneToOneField(
        Anunciante, on_delete=models.CASCADE, related_name="assinatura", verbose_name="anunciante"
    )
    plano = models.ForeignKey(
        Plano, on_delete=models.PROTECT, related_name="assinaturas", verbose_name="plano"
    )
    periodicidade = models.CharField(
        "periodicidade", max_length=6, choices=Periodicidade.choices, default=Periodicidade.MENSAL
    )
    inicio = models.DateField("início", default=timezone.localdate)
    vencimento = models.DateField(
        "vencimento", help_text="Próximo pagamento. Depois da carência, vira atraso."
    )
    situacao = models.CharField(
        "situação", max_length=10, choices=Situacao.choices, default=Situacao.ATIVA, db_index=True
    )
    criado_em = models.DateTimeField("criada em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizada em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico da assinatura")

    class Meta:
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"
        ordering = ["vencimento"]

    def __str__(self) -> str:
        """Ex.: 'Loja X · Profissional (mensal)'."""
        return f"{self.anunciante} · {self.plano.nome} ({self.get_periodicidade_display().lower()})"

    @property
    def valor(self) -> Decimal:
        """Valor da periodicidade escolhida."""
        return (
            self.plano.preco_anual if self.periodicidade == Periodicidade.ANUAL else self.plano.preco_mensal
        )


class PedidoTrocaPlano(MarcaDemo):
    """Pedido do anunciante para assinar ou trocar de plano (sem pagamento por enquanto).

    A equipe aprova (aplica o plano) ou recusa (com motivo); o anunciante recebe e-mail.
    """

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"

    anunciante = models.ForeignKey(
        Anunciante, on_delete=models.CASCADE, related_name="pedidos_plano", verbose_name="anunciante"
    )
    plano_atual = models.ForeignKey(
        Plano, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="plano atual"
    )
    plano_novo = models.ForeignKey(
        Plano, on_delete=models.PROTECT, related_name="+", verbose_name="plano pedido"
    )
    periodicidade = models.CharField("periodicidade", max_length=6, choices=Periodicidade.choices)
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    motivo = models.TextField("motivo da decisão", blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)
    criado_em = models.DateTimeField("pedido em", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "pedido de troca de plano"
        verbose_name_plural = "pedidos de troca de plano"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        """Ex.: 'Loja X: Básico → Premium (anual)'."""
        atual = self.plano_atual.nome if self.plano_atual else "sem plano"
        periodo = self.get_periodicidade_display().lower()
        return f"{self.anunciante}: {atual} → {self.plano_novo.nome} ({periodo})"

    @property
    def e_downgrade(self) -> bool:
        """O plano pedido tem limite menor que o atual."""
        return bool(self.plano_atual) and self.plano_novo.limite_anuncios < self.plano_atual.limite_anuncios
