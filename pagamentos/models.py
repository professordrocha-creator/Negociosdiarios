"""Modelos do app pagamentos: Fatura e os textos dos e-mails de cobrança (docs/PAGAMENTOS.md).

V1 = cobrança manual assistida: o sistema gera a fatura, mostra o Pix estático (copia e cola + QR
Code), recebe o comprovante e a equipe confirma no admin. Sem gateway (Mercado Pago fica para a V2).
Dinheiro em DecimalField; nada se apaga (cancelar é uma situação); histórico com django-simple-history.
"""

import re
import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import MarcaDemo
from pagamentos.armazenamento import armazenamento_privado
from planos.models import Assinatura


def caminho_comprovante(instancia, nome_arquivo: str) -> str:
    """Nome aleatório (nunca o nome enviado, que pode ter o nome de quem pagou)."""
    return f"comprovantes/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


class Fatura(MarcaDemo):
    """Cobrança de um ciclo da assinatura (mensal ou anual) ou de uma campanha de publicidade (Sprint 7A).

    Sempre de uma das duas: `assinatura` (loja, paga pelo painel) ou `campanha` (patrocinador sem login,
    paga pela página pública com `token`).

    Gerada pela rotina diária X dias antes do vencimento da assinatura
    (`Configuracao.fatura_antecedencia_dias`). Situações:
    - `aberta`: a pagar, dentro do prazo;
    - `vencida`: passou do vencimento sem pagamento (depois da carência, a assinatura fica em atraso
      e os anúncios são pausados);
    - `aguardando_confirmacao`: o anunciante enviou o comprovante ("Já paguei"); a equipe confere;
    - `paga`: confirmada pela equipe (renova a assinatura e reativa os anúncios);
    - `cancelada`: não vale mais (com motivo no histórico).
    """

    class Situacao(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        AGUARDANDO = "aguardando_confirmacao", "Aguardando confirmação"
        PAGA = "paga", "Paga"
        VENCIDA = "vencida", "Vencida"
        CANCELADA = "cancelada", "Cancelada"

    class Forma(models.TextChoices):
        PIX = "pix", "Pix"
        BOLETO = "boleto", "Boleto"
        TRANSFERENCIA = "transferencia", "Transferência"
        DINHEIRO = "dinheiro", "Dinheiro"
        OUTRO = "outro", "Outro"

    A_PAGAR = (Situacao.ABERTA, Situacao.VENCIDA)  # o anunciante ainda pode pagar / enviar comprovante
    EM_ABERTO = (Situacao.ABERTA, Situacao.VENCIDA, Situacao.AGUARDANDO)  # ainda não paga nem cancelada

    assinatura = models.ForeignKey(
        Assinatura,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="faturas",
        verbose_name="assinatura",
    )
    campanha = models.ForeignKey(
        "publicidade.Campanha",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="faturas",
        verbose_name="campanha de publicidade",
    )
    # Endereço da página pública de pagamento (/fatura/<token>/): aleatório, não dá para adivinhar.
    token = models.UUIDField("token do link de pagamento", default=uuid.uuid4, unique=True, editable=False)
    codigo = models.CharField("código", max_length=16, unique=True, null=True, blank=True, editable=False)
    competencia = models.DateField("competência", help_text="Início do período pago por esta fatura.")
    periodo_fim = models.DateField("fim do período")
    descricao = models.CharField("descrição", max_length=120, help_text='Ex.: "Profissional · mensal".')
    valor = models.DecimalField("valor (R$)", max_digits=9, decimal_places=2)
    vencimento = models.DateField("vencimento", db_index=True)
    situacao = models.CharField(
        "situação", max_length=24, choices=Situacao.choices, default=Situacao.ABERTA, db_index=True
    )
    pago_em = models.DateTimeField("pago em", null=True, blank=True)
    forma = models.CharField("forma de pagamento", max_length=15, choices=Forma.choices, blank=True)
    link_boleto = models.URLField(
        "link do boleto",
        blank=True,
        max_length=500,
        help_text="Opcional: link de um boleto gerado no banco; aparece para o anunciante junto do Pix.",
    )
    comprovante = models.FileField(
        "comprovante",
        storage=armazenamento_privado,
        upload_to=caminho_comprovante,
        blank=True,
        editable=False,
        help_text="Enviado pelo anunciante (imagem ou PDF). Guardado fora da mídia pública.",
    )
    comprovante_enviado_em = models.DateTimeField("comprovante enviado em", null=True, blank=True)
    observacao = models.TextField(
        "observação",
        blank=True,
        help_text="Anotações da equipe e o recado do anunciante ao enviar o comprovante.",
    )
    motivo_recusa = models.TextField("motivo da recusa do comprovante", blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="confirmado por",
    )
    # Lembretes já enviados (chaves de ModeloEmailCobranca): a régua nunca manda o mesmo duas vezes.
    avisos_enviados = models.JSONField("avisos enviados", default=list, blank=True, editable=False)
    criado_em = models.DateTimeField("criada em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizada em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico da fatura", excluded_fields=["avisos_enviados"])

    class Meta:
        verbose_name = "fatura"
        verbose_name_plural = "faturas"
        ordering = ["-vencimento", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["assinatura", "competencia"],
                condition=~Q(situacao="cancelada"),
                name="fatura_unica_por_competencia",
            ),
            models.CheckConstraint(
                condition=Q(assinatura__isnull=False, campanha__isnull=True)
                | Q(assinatura__isnull=True, campanha__isnull=False),
                name="fatura_de_assinatura_ou_campanha",
            ),
        ]

    def __str__(self) -> str:
        """Ex.: 'ND-FT-00012 · Loja X · R$ 99,90'."""
        return f"{self.codigo or 'nova'} · {self.cliente_nome} · R$ {self.valor}"

    @property
    def cliente_nome(self) -> str:
        """Quem paga: a loja ou o patrocinador."""
        if self.assinatura_id:
            return self.assinatura.anunciante.nome_publico
        return self.campanha.patrocinador.nome

    @property
    def cliente_email(self) -> str:
        """Para onde vão a fatura e os lembretes."""
        if self.assinatura_id:
            return self.assinatura.anunciante.usuario.email
        return self.campanha.patrocinador.email

    @property
    def link_pagamento(self) -> str:
        """Caminho onde o cliente paga: o painel (loja) ou a página pública com o token (patrocinador)."""
        from django.urls import reverse

        if self.assinatura_id:
            return reverse("pagamentos:faturas")
        return reverse("pagamentos:fatura_publica", args=[self.token])

    def save(self, *args, **kwargs) -> None:
        """Na primeira gravação, gera o código público a partir do id (ND-FT-00001)."""
        novo = self.pk is None
        super().save(*args, **kwargs)
        if novo and not self.codigo:
            self.codigo = f"ND-FT-{self.pk:05d}"
            type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)
            self.history.filter(id=self.pk).update(codigo=self.codigo)

    @property
    def identificador_pix(self) -> str:
        """Identificador da fatura no Pix (campo txid: só letras e números), ex.: NDFT00012."""
        return re.sub(r"[^A-Za-z0-9]", "", self.codigo or "")

    @property
    def a_pagar(self) -> bool:
        """Ainda pode ser paga pelo anunciante (aberta ou vencida)."""
        return self.situacao in self.A_PAGAR

    @property
    def comprovante_e_pdf(self) -> bool:
        """O comprovante enviado é PDF (senão, imagem)."""
        return self.comprovante.name.lower().endswith(".pdf")


class ModeloEmailCobranca(models.Model):
    """Texto de um e-mail de cobrança, editável no admin (sem deploy).

    Variáveis entre chaves no assunto e no texto: {loja}, {valor}, {vencimento}, {competencia},
    {codigo}, {link}, {motivo}, {site}. Texto puro (sem HTML). Desligado = não é enviado.
    """

    class Chave(models.TextChoices):
        FATURA_DISPONIVEL = "fatura_disponivel", "Fatura disponível"
        LEMBRETE_3_DIAS = "lembrete_3_dias", "Lembrete: vence em 3 dias"
        VENCE_HOJE = "vence_hoje", "Lembrete: vence hoje"
        VENCIDA_1_DIA = "vencida_1_dia", "Cobrança: vencida há 1 dia"
        VENCIDA_3_DIAS = "vencida_3_dias", "Cobrança: vencida há 3 dias"
        PAGAMENTO_CONFIRMADO = "pagamento_confirmado", "Pagamento confirmado"
        COMPROVANTE_RECUSADO = "comprovante_recusado", "Comprovante recusado"

    VARIAVEIS = ("loja", "valor", "vencimento", "competencia", "codigo", "link", "motivo", "site")

    chave = models.CharField("e-mail", max_length=30, choices=Chave.choices, unique=True)
    assunto = models.CharField("assunto", max_length=150)
    corpo = models.TextField(
        "texto",
        help_text="Texto puro. Variáveis: {loja}, {valor}, {vencimento}, {competencia}, {codigo}, {link}, "
        "{motivo} (só na recusa) e {site}.",
    )
    ativo = models.BooleanField("enviar", default=True, help_text="Desmarcado, este e-mail não é enviado.")
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico do texto")

    class Meta:
        verbose_name = "e-mail de cobrança"
        verbose_name_plural = "e-mails de cobrança"
        ordering = ["chave"]

    def __str__(self) -> str:
        """Nome do e-mail."""
        return self.get_chave_display()

    def clean(self) -> None:
        """Só variáveis conhecidas (uma chave errada sairia literalmente no e-mail do cliente)."""
        desconhecidas = {
            nome
            for texto in (self.assunto, self.corpo)
            for nome in re.findall(r"\{(\w*)\}", texto)
            if nome not in self.VARIAVEIS
        }
        if desconhecidas:
            raise ValidationError(
                f"Variáveis desconhecidas: {', '.join(sorted('{' + n + '}' for n in desconhecidas))}. "
                f"Use: {', '.join('{' + v + '}' for v in self.VARIAVEIS)}."
            )
