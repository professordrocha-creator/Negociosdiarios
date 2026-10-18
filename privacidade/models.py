"""Modelos do app privacidade (LGPD; docs/LGPD.md): documentos legais com versão e pedidos do titular.

O aceite em si fica em `contas.AceiteDocumento` (usuário, documento, versão, data e hora), criado na Sprint 1.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import MarcaDemo


class DocumentoLegal(models.Model):
    """Termos de Uso ou Política de Privacidade numa versão, editável no admin.

    Vale a versão publicada com a vigência mais recente que já começou. Publicada e em vigor, o texto não
    muda mais (é o que as pessoas aceitaram): para mudar, crie uma versão nova. Quem não aceitou a versão
    vigente vê o resumo das mudanças e aceita no próximo acesso ao painel.
    """

    class Tipo(models.TextChoices):
        TERMOS = "termos", "Termos de Uso"
        PRIVACIDADE = "privacidade", "Política de Privacidade"

    tipo = models.CharField("documento", max_length=20, choices=Tipo.choices)
    versao = models.CharField(
        "versão", max_length=40, help_text='Ex.: "2026-11". Aparece no aceite de cada pessoa.'
    )
    vigencia = models.DateField(
        "em vigor a partir de", help_text="A partir desta data, todos precisam aceitar."
    )
    resumo = models.TextField(
        "o que mudou",
        blank=True,
        help_text="Resumo mostrado a quem precisa aceitar a versão nova. Texto puro, um item por linha.",
    )
    texto = models.TextField(
        "texto",
        help_text="Texto puro. Título de seção: linha começando com ## . Item de lista: linha começando "
        "com - . Parágrafos separados por linha em branco. Variáveis: {site}, {empresa}, {cidade_sede}, "
        "{email_contato}, {email_privacidade}.",
    )
    revisao_juridica_pendente = models.BooleanField(
        "rascunho: revisão jurídica pendente",
        default=True,
        help_text="Aviso só para a equipe (no admin). Desmarque quando o advogado aprovar o texto.",
    )
    publicado = models.BooleanField(
        "publicado", default=False, help_text="Desmarcado, ninguém vê esta versão."
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico do documento")

    class Meta:
        verbose_name = "documento legal"
        verbose_name_plural = "documentos legais (termos e privacidade)"
        ordering = ["tipo", "-vigencia", "-pk"]
        constraints = [models.UniqueConstraint(fields=["tipo", "versao"], name="documento_versao_unica")]

    def __str__(self) -> str:
        """Ex.: 'Termos de Uso v2026-11'."""
        return f"{self.get_tipo_display()} v{self.versao}"

    def em_vigor(self, hoje=None) -> bool:
        """Publicado e com a vigência já começada (o texto fica travado)."""
        hoje = hoje or timezone.localdate()
        return self.publicado and self.vigencia <= hoje


class PedidoTitular(MarcaDemo):
    """Pedido de um titular de dados (LGPD, art. 18): acesso, portabilidade, correção, exclusão...

    Os feitos pelo painel ("Baixar meus dados", "Excluir minha conta") já nascem atendidos. Os que chegam
    por e-mail a equipe registra no admin. Prazo: `Configuracao.prazo_titular_dias` (padrão 15 dias).
    """

    class Tipo(models.TextChoices):
        ACESSO = "acesso", "Confirmação e acesso aos dados"
        EXPORTACAO = "exportacao", "Portabilidade (cópia dos dados)"
        CORRECAO = "correcao", "Correção"
        EXCLUSAO = "exclusao", "Exclusão / anonimização"
        OUTRO = "outro", "Outro (informação, revogação...)"

    class Origem(models.TextChoices):
        PAINEL = "painel", "Painel do anunciante"
        EMAIL = "email", "E-mail"
        OUTRO = "outro", "Outro canal"

    class Situacao(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        ATENDIDO = "atendido", "Atendido"
        RECUSADO = "recusado", "Recusado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_titular",
        verbose_name="conta",
    )
    contato = models.CharField(
        "contato de quem pediu",
        max_length=200,
        blank=True,
        help_text="Só para pedidos por e-mail ou outro canal (e-mail ou telefone para responder).",
    )
    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices)
    origem = models.CharField("origem", max_length=8, choices=Origem.choices, default=Origem.EMAIL)
    descricao = models.TextField("o que foi pedido", blank=True)
    situacao = models.CharField(
        "situação", max_length=14, choices=Situacao.choices, default=Situacao.ABERTO, db_index=True
    )
    recebido_em = models.DateTimeField("recebido em", default=timezone.now)
    prazo = models.DateField(
        "prazo", blank=True, help_text="Vazio = recebido + o prazo das Configurações do site (15 dias)."
    )
    atendido_em = models.DateTimeField("respondido em", null=True, blank=True)
    resposta = models.TextField("resposta / o que foi feito", blank=True)

    history = HistoricalRecords(verbose_name="histórico do pedido")

    class Meta:
        verbose_name = "pedido do titular (LGPD)"
        verbose_name_plural = "pedidos dos titulares (LGPD)"
        ordering = ["situacao", "prazo"]

    def __str__(self) -> str:
        """Ex.: 'Exclusão / anonimização · 12/10/2026'."""
        return f"{self.get_tipo_display()} · {timezone.localtime(self.recebido_em):%d/%m/%Y}"

    def save(self, *args, **kwargs) -> None:
        """Prazo padrão: data do recebimento + o prazo da Configuracao."""
        if not self.prazo:
            from core.services import configuracao

            recebido = timezone.localtime(self.recebido_em).date()
            self.prazo = recebido + timedelta(days=configuracao().prazo_titular_dias)
        super().save(*args, **kwargs)

    @property
    def em_aberto(self) -> bool:
        """Ainda sem resposta final."""
        return self.situacao in (self.Situacao.ABERTO, self.Situacao.EM_ANDAMENTO)

    def atrasado(self, hoje=None) -> bool:
        """Em aberto e com o prazo vencido."""
        return self.em_aberto and self.prazo < (hoje or timezone.localdate())
