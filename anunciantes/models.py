"""Modelos do app anunciantes: a "loja" de cada corretor ou revenda (docs/ARQUITETURA.md §4)."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from core.models import Cidade, MarcaDemo


class Anunciante(MarcaDemo):
    """Loja de um profissional verificado (corretor com CRECI ou empresa com CNPJ).

    Um usuário tem no máximo um anunciante. Só anunciante `ativo` entra no painel e
    aparece no site; o status muda pelas ações "Aprovar" e "Suspender" do admin, que
    registram o motivo (e o histórico guarda quem mudou e quando).
    """

    class Tipo(models.TextChoices):
        CORRETOR_AUTONOMO = "corretor_autonomo", "Corretor autônomo"
        IMOBILIARIA = "imobiliaria", "Imobiliária"
        REVENDA = "revenda", "Revenda de veículos"
        CONCESSIONARIA = "concessionaria", "Concessionária"
        GARAGEM = "garagem", "Garagem"

    class DocumentoTipo(models.TextChoices):
        CRECI = "creci", "CRECI"
        CNPJ = "cnpj", "CNPJ"

    class Status(models.TextChoices):
        # inadimplente e encerrado chegam com planos/pagamentos (Sprints 2 e 6) e LGPD (Sprint 7).
        PENDENTE = "pendente", "Pendente (em análise)"
        ATIVO = "ativo", "Ativo"
        SUSPENSO = "suspenso", "Suspenso"

    # Corretor autônomo prova a profissão pelo CRECI; os demais tipos são empresas (CNPJ).
    DOCUMENTO_POR_TIPO = {Tipo.CORRETOR_AUTONOMO: DocumentoTipo.CRECI}

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="anunciante",
        verbose_name="usuário",
        help_text="Conta de login do anunciante (e-mail e senha).",
    )
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices)
    nome_publico = models.CharField(
        "nome público", max_length=80, help_text="Como a loja aparece no site. Até 80 caracteres."
    )
    slug = models.SlugField(
        "endereço da loja",
        max_length=80,
        unique=True,
        help_text="Usado em /loja/<endereço>/. Só letras minúsculas, números e hífen.",
    )
    sigla = models.CharField(
        "sigla", max_length=3, blank=True, help_text="Letras do monograma (até 3). Vazio = iniciais do nome."
    )
    cor = models.PositiveSmallIntegerField(
        "cor do monograma",
        default=1,
        choices=[(n, f"Cor {n}") for n in range(1, 7)],
        help_text="Uma das 6 cores da identidade do site (usada enquanto não houver logo).",
    )
    documento_tipo = models.CharField("tipo de documento", max_length=5, choices=DocumentoTipo.choices)
    documento_numero = models.CharField(
        "número do documento",
        max_length=20,
        help_text="CNPJ (14 dígitos; pontuação opcional) ou CRECI no formato CRECI/MT 12345-F.",
    )
    whatsapp = models.CharField(
        "WhatsApp",
        max_length=16,
        help_text="Com DDD, ex.: (65) 99999-0000. Guardado no formato +5565999990000.",
    )
    email_publico = models.EmailField(
        "e-mail público", blank=True, help_text="Opcional. Aparece na página da loja."
    )
    cidade = models.ForeignKey(
        Cidade,
        on_delete=models.PROTECT,
        related_name="anunciantes",
        verbose_name="cidade",
        help_text="Cidade da loja. Só cidades liberadas no site.",
    )
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    motivo_status = models.TextField(
        "motivo da última mudança de situação",
        blank=True,
        help_text="Registrado pelas ações Aprovar/Suspender do admin.",
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico do anunciante")

    class Meta:
        verbose_name = "anunciante"
        verbose_name_plural = "anunciantes"
        ordering = ["nome_publico"]
        constraints = [
            models.UniqueConstraint(
                fields=["documento_tipo", "documento_numero"], name="anunciante_documento_unico"
            ),
        ]

    def __str__(self) -> str:
        """Nome público da loja."""
        return self.nome_publico

    @property
    def iniciais(self) -> str:
        """Sigla do monograma: a escolhida ou as iniciais das duas primeiras palavras."""
        if self.sigla:
            return self.sigla.upper()
        palavras = [p for p in self.nome_publico.split() if p[:1].isalnum()]
        return "".join(p[0] for p in palavras[:2]).upper() or "?"

    @property
    def ativo(self) -> bool:
        """Pode usar o painel e aparecer no site."""
        return self.status == self.Status.ATIVO

    def documento_esperado(self) -> str:
        """Tipo de documento exigido para o tipo de anunciante (CRECI ou CNPJ)."""
        return self.DOCUMENTO_POR_TIPO.get(self.tipo, self.DocumentoTipo.CNPJ)

    def clean(self) -> None:
        """Confere documento x tipo, normaliza CNPJ/CRECI/WhatsApp e exige cidade liberada."""
        super().clean()
        erros = {}
        if self.tipo and self.documento_tipo and self.documento_tipo != self.documento_esperado():
            esperado = self.DocumentoTipo(self.documento_esperado()).label
            erros["documento_tipo"] = f"Para {self.get_tipo_display().lower()} o documento é o {esperado}."
        if self.documento_numero and self.documento_tipo:
            try:
                if self.documento_tipo == self.DocumentoTipo.CNPJ:
                    self.documento_numero = normalizar_cnpj(self.documento_numero)
                else:
                    uf = self.cidade.uf_id if self.cidade_id else "MT"
                    self.documento_numero = normalizar_creci(self.documento_numero, uf_padrao=uf)
            except ValidationError as erro:
                erros["documento_numero"] = erro.messages
        if self.whatsapp:
            try:
                self.whatsapp = normalizar_whatsapp(self.whatsapp)
            except ValidationError as erro:
                erros["whatsapp"] = erro.messages
        if self.cidade_id and not (self.cidade.liberada and self.cidade.uf.liberado):
            erros["cidade"] = "Esta cidade ainda não é atendida pelo site. Escolha uma cidade liberada."
        if erros:
            raise ValidationError(erros)
