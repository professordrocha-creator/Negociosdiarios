"""Modelos do app publicidade: venda direta de espaços (docs/PUBLICIDADE.md, Sprint 7A).

Patrocinador (empresa que compra) → Campanha (posições, cidades, início, fim, valor, situação) → Banner
(a peça: imagem por formato, texto, link) → MetricaDiaria (impressões e cliques por dia, SEM IP nem cookie).
Sem AdSense. Nada se apaga (campanha se cancela/encerra); histórico com django-simple-history.
"""

import uuid
from pathlib import PurePath

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.models import Anunciante
from core.models import Cidade, MarcaDemo

# Link do banner: só http/https (nada de javascript:, data:, etc.).
validar_link = URLValidator(
    schemes=["http", "https"], message="Use um endereço que comece com https:// ou http://."
)


def caminho_banner(instancia, nome_arquivo: str) -> str:
    """Nome aleatório (nunca o nome enviado)."""
    return f"publicidade/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


class Formato(models.TextChoices):
    """Formatos de peça (docs/PUBLICIDADE.md)."""

    BANNER = "banner", "Banner (computador + celular)"
    CARD = "card", "Card patrocinador (logo + frase)"
    NATIVO = "nativo", "Anúncio nativo (título + texto)"


class Posicao(models.TextChoices):
    """Onde a publicidade aparece. No máximo 3 espaços por página (docs/PUBLICIDADE.md)."""

    HOME_TOPO = "home_topo", "Home: banner no topo"
    BUSCA_TOPO = "busca_topo", "Busca: banner no topo"
    BUSCA_NATIVO = "busca_nativo", "Busca: anúncio nativo no topo dos resultados"
    ANUNCIO_TOPO = "anuncio_topo", "Página do anúncio: banner"
    RODAPE_CARD = "rodape_card", "Rodapé da home: card patrocinador (3 vagas)"


FORMATO_DA_POSICAO = {
    Posicao.HOME_TOPO: Formato.BANNER,
    Posicao.BUSCA_TOPO: Formato.BANNER,
    Posicao.ANUNCIO_TOPO: Formato.BANNER,
    Posicao.RODAPE_CARD: Formato.CARD,
    Posicao.BUSCA_NATIVO: Formato.NATIVO,
}


class Patrocinador(MarcaDemo):
    """Empresa que compra publicidade (construtora, material de construção, autopeças...).

    `anunciante` liga o patrocinador a uma loja do site: loja só compra publicidade se for assinante
    (regra 4 do PUBLICIDADE.md, conferida em `publicidade.services`).
    """

    nome = models.CharField("nome", max_length=120)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True, help_text="Opcional. Só dígitos.")
    contato_nome = models.CharField("pessoa de contato", max_length=120, blank=True)
    email = models.EmailField("e-mail", help_text="Recebe a fatura, os lembretes e o link de pagamento.")
    whatsapp = models.CharField(
        "WhatsApp", max_length=16, blank=True, help_text="Opcional. Ex.: (65) 99999-0000."
    )
    anunciante = models.ForeignKey(
        Anunciante,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="patrocinios",
        verbose_name="loja do site (se for uma)",
        help_text="Imobiliária, corretor ou revenda só compra publicidade se tiver assinatura ativa.",
    )
    observacao = models.TextField("observação", blank=True)
    criado_em = models.DateTimeField("cadastrado em", default=timezone.now, editable=False)

    history = HistoricalRecords(verbose_name="histórico do patrocinador")

    class Meta:
        verbose_name = "patrocinador"
        verbose_name_plural = "patrocinadores"
        ordering = ["nome"]

    def __str__(self) -> str:
        """Nome do patrocinador."""
        return self.nome


class Campanha(MarcaDemo):
    """Contrato de publicidade: onde (posições e, se quiser, cidades), quando (início e fim) e quanto.

    No ar = situação "ativa" e hoje entre início e fim (entra e sai sozinha pela data). A tarefa diária
    marca como "encerrada" a que passou do fim e avisa a equipe X dias antes (Configuracao).
    """

    class Situacao(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        ATIVA = "ativa", "Ativa"
        PAUSADA = "pausada", "Pausada"
        ENCERRADA = "encerrada", "Encerrada"
        CANCELADA = "cancelada", "Cancelada"

    patrocinador = models.ForeignKey(
        Patrocinador, on_delete=models.PROTECT, related_name="campanhas", verbose_name="patrocinador"
    )
    nome = models.CharField(
        "nome da campanha", max_length=120, help_text='Ex.: "Lançamento Residencial Ipê".'
    )
    posicoes = ArrayField(
        models.CharField(max_length=20, choices=Posicao.choices),
        verbose_name="posições",
        help_text="Onde as peças aparecem.",
    )
    cidades = models.ManyToManyField(
        Cidade,
        blank=True,
        related_name="campanhas",
        verbose_name="cidades",
        limit_choices_to={"liberada": True},
        help_text="Opcional: só nas buscas e anúncios destas cidades. Vazio = em todo o site.",
    )
    inicio = models.DateField("início")
    fim = models.DateField("fim")
    valor = models.DecimalField(
        "valor (R$)", max_digits=9, decimal_places=2, validators=[MinValueValidator(0)]
    )
    situacao = models.CharField(
        "situação", max_length=10, choices=Situacao.choices, default=Situacao.RASCUNHO, db_index=True
    )
    aviso_fim_enviado = models.BooleanField("aviso de fim enviado", default=False, editable=False)
    criado_em = models.DateTimeField("criada em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizada em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico da campanha")

    class Meta:
        verbose_name = "campanha"
        verbose_name_plural = "campanhas"
        ordering = ["-inicio", "nome"]

    def __str__(self) -> str:
        """Ex.: 'Lançamento Ipê (Construtora X)'."""
        return f"{self.nome} ({self.patrocinador})"

    def clean(self) -> None:
        """Fim depois do início e ao menos uma posição."""
        if self.inicio and self.fim and self.fim < self.inicio:
            raise ValidationError({"fim": "O fim não pode ser antes do início."})
        if not self.posicoes:
            raise ValidationError({"posicoes": "Escolha pelo menos uma posição."})

    @property
    def formatos(self) -> set[str]:
        """Formatos de peça que as posições pedem."""
        return {FORMATO_DA_POSICAO[p] for p in self.posicoes}

    def no_ar(self, hoje=None) -> bool:
        """Ativa e dentro do período."""
        hoje = hoje or timezone.localdate()
        return self.situacao == self.Situacao.ATIVA and self.inicio <= hoje <= self.fim


class Banner(MarcaDemo):
    """A peça de uma campanha, num formato. Imagens passam pelo mesmo tratamento das fotos (Celery: WebP
    no tamanho da Configuracao, sem EXIF, original apagado). Nativo é só texto."""

    campanha = models.ForeignKey(
        Campanha, on_delete=models.PROTECT, related_name="banners", verbose_name="campanha"
    )
    formato = models.CharField("formato", max_length=10, choices=Formato.choices, default=Formato.BANNER)
    imagem_original = models.FileField(upload_to=caminho_banner, blank=True, editable=False)
    imagem = models.FileField("imagem (WebP)", upload_to=caminho_banner, blank=True, editable=False)
    imagem_celular_original = models.FileField(upload_to=caminho_banner, blank=True, editable=False)
    imagem_celular = models.FileField(
        "imagem do celular (WebP)", upload_to=caminho_banner, blank=True, editable=False
    )
    texto_alternativo = models.CharField(
        "texto alternativo",
        max_length=125,
        blank=True,
        help_text="O que a imagem diz, para quem usa leitor de tela. Obrigatório quando há imagem.",
    )
    titulo = models.CharField("título", max_length=60, blank=True, help_text="Nativo: até 60 caracteres.")
    texto = models.CharField(
        "texto", max_length=120, blank=True, help_text="Nativo: até 120 caracteres. Card: frase de até 80."
    )
    link = models.URLField("link", max_length=500, validators=[validar_link])
    ativo = models.BooleanField("ativo", default=True, help_text="Desmarcado, a peça sai do rodízio.")
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "peça (banner)"
        verbose_name_plural = "peças (banners)"
        ordering = ["campanha", "formato", "pk"]

    def __str__(self) -> str:
        """Ex.: 'Banner · Lançamento Ipê'."""
        return f"{self.get_formato_display().split(' (')[0]} · {self.campanha.nome}"

    def clean(self) -> None:
        """Card: frase até 80; nativo: título e texto obrigatórios."""
        if self.formato == Formato.CARD and len(self.texto) > 80:
            raise ValidationError({"texto": "No card, a frase tem até 80 caracteres."})
        if self.formato == Formato.NATIVO and not (self.titulo and self.texto):
            raise ValidationError("O anúncio nativo precisa de título e texto.")

    @property
    def pronto(self) -> bool:
        """Pode ir ao ar: nativo sempre; banner com as duas imagens; card com a imagem."""
        if self.formato == Formato.NATIVO:
            return True
        if self.formato == Formato.BANNER:
            return bool(self.imagem and self.imagem_celular)
        return bool(self.imagem)


class MetricaDiaria(models.Model):
    """Impressões e cliques de uma peça num dia. Só totais: nenhum IP, cookie ou identificador."""

    banner = models.ForeignKey(Banner, on_delete=models.CASCADE, related_name="metricas", verbose_name="peça")
    dia = models.DateField("dia")
    impressoes = models.PositiveIntegerField("impressões", default=0)
    cliques = models.PositiveIntegerField("cliques", default=0)

    class Meta:
        verbose_name = "métrica diária"
        verbose_name_plural = "métricas diárias"
        constraints = [models.UniqueConstraint(fields=["banner", "dia"], name="metrica_unica_por_dia")]
        ordering = ["-dia"]

    def __str__(self) -> str:
        """Ex.: 'Banner · Ipê em 12/10/2026'."""
        return f"{self.banner} em {self.dia:%d/%m/%Y}"
