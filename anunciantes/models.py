"""Modelos do app anunciantes: a "loja" de cada corretor ou revenda (docs/ARQUITETURA.md §4)."""

import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from core.models import Cidade, MarcaDemo


def caminho_original(instancia, nome_arquivo: str) -> str:
    """Envio ainda não processado: nome aleatório; apagado depois que o Celery gera os WebP."""
    return f"originais/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


def caminho_loja(instancia, nome_arquivo: str) -> str:
    """WebP gerados para a loja: pasta lojas/, nome aleatório (nunca o nome enviado)."""
    return f"lojas/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


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
        help_text="Cidade da loja. Cidade ainda não atendida gera uma solicitação de liberação.",
    )
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    motivo_status = models.TextField(
        "motivo da última mudança de situação",
        blank=True,
        help_text="Registrado pelas ações Aprovar/Suspender do admin.",
    )
    # Página da loja (Sprint 2): editados pelo próprio anunciante em /painel/loja/.
    sobre = models.TextField(
        "sobre a loja", max_length=500, blank=True, help_text="Até 500 caracteres. Texto puro."
    )
    endereco_publico = models.CharField(
        "endereço da loja", max_length=200, blank=True, help_text="Ex.: Av. Brasil, 1.250 · Centro."
    )
    mostrar_no_mapa = models.BooleanField(
        "mostrar endereço e mapa", default=False, help_text="Desmarcado, o endereço não aparece na página."
    )
    horario = models.CharField(
        "horário de atendimento", max_length=120, blank=True, help_text="Ex.: Seg a sex 8h–18h · Sáb 8h–12h."
    )
    instagram = models.CharField("Instagram", max_length=30, blank=True, help_text="Só o usuário, sem @.")
    site = models.URLField("site", blank=True, help_text="Endereço completo, com https://.")
    # Imagens: o envio fica em *_original até o Celery gerar os WebP; aí o original é apagado.
    logo_original = models.FileField(upload_to=caminho_original, blank=True, editable=False)
    capa_original = models.FileField(upload_to=caminho_original, blank=True, editable=False)
    logo = models.FileField("logo (400 px)", upload_to=caminho_loja, blank=True, editable=False)
    logo_mini = models.FileField("logo (96 px)", upload_to=caminho_loja, blank=True, editable=False)
    capa = models.FileField("capa (1600 px)", upload_to=caminho_loja, blank=True, editable=False)
    capa_media = models.FileField("capa (800 px)", upload_to=caminho_loja, blank=True, editable=False)
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
    def imagens_processando(self) -> bool:
        """Há logo ou capa enviados esperando o Celery gerar os WebP."""
        return bool(self.logo_original or self.capa_original)

    @property
    def tipo_schema(self) -> str:
        """Tipo do schema.org para buscadores: imobiliária/corretor ou revenda de veículos."""
        imoveis = (self.Tipo.CORRETOR_AUTONOMO, self.Tipo.IMOBILIARIA)
        return "RealEstateAgent" if self.tipo in imoveis else "AutoDealer"

    @property
    def ativo(self) -> bool:
        """Pode usar o painel e aparecer no site."""
        return self.status == self.Status.ATIVO

    def documento_esperado(self) -> str:
        """Tipo de documento exigido para o tipo de anunciante (CRECI ou CNPJ)."""
        return self.DOCUMENTO_POR_TIPO.get(self.tipo, self.DocumentoTipo.CNPJ)

    def clean(self) -> None:
        """Confere documento x tipo, normaliza CNPJ/CRECI/WhatsApp e confere a cidade."""
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
        # Cidade ainda não atendida é aceita no cadastro (vira SolicitacaoCidade), mas loja ativa
        # só em cidade liberada; e nunca fora de um estado liberado (ARQUITETURA §9, regra 3).
        if self.cidade_id and not self.cidade.uf.liberado:
            erros["cidade"] = "O site ainda não atende este estado."
        elif self.cidade_id and self.status == self.Status.ATIVO and not self.cidade.liberada:
            erros["cidade"] = "Esta cidade ainda não é atendida: libere a cidade antes de ativar a loja."
        if erros:
            raise ValidationError(erros)


class SolicitacaoCidade(MarcaDemo):
    """Pedido para atender uma cidade ainda não liberada, gerado pelo cadastro (ARQUITETURA §9).

    O admin decide: "Liberar cidade" (a cidade entra no site e todas as solicitações
    pendentes dela são atendidas) ou "Recusar" (com motivo, enviado por e-mail).
    """

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        LIBERADA = "liberada", "Cidade liberada"
        RECUSADA = "recusada", "Recusada"

    anunciante = models.ForeignKey(
        Anunciante, on_delete=models.CASCADE, related_name="solicitacoes_cidade", verbose_name="anunciante"
    )
    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name="solicitacoes", verbose_name="cidade"
    )
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    motivo = models.TextField("motivo da decisão", blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="decidido por",
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)
    criado_em = models.DateTimeField("pedido em", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "solicitação de cidade"
        verbose_name_plural = "solicitações de cidade"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        """Ex.: 'Sinop/MT (Loja X)'."""
        return f"{self.cidade} ({self.anunciante})"
