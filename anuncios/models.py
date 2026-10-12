"""Modelos do app anuncios: o anúncio (base comum), o detalhe de imóvel e as fotos.

Veículo (DetalheVeiculo, catálogo FIPE) chega na Sprint 4 com a mesma base `Anuncio`.
Nada é apagado pelo anunciante: "excluir" muda a situação para `removido` (exclusão lógica).
"""

import uuid
from decimal import Decimal
from pathlib import PurePath

from django.contrib.gis.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.models import Anunciante
from core.models import Bairro, Cidade, MarcaDemo

PREFIXO_CODIGO = {"imovel": "ND-IM", "veiculo": "ND-VE"}


def caminho_foto_original(instancia, nome_arquivo: str) -> str:
    """Envio ainda não processado: nome aleatório; apagado depois que o Celery gera os WebP."""
    return f"originais/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


def caminho_foto(instancia, nome_arquivo: str) -> str:
    """WebP das fotos de anúncio: pasta anuncios/, nome aleatório (nunca o nome enviado)."""
    return f"anuncios/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


class Anuncio(MarcaDemo):
    """Base comum de todo anúncio (imóvel agora; veículo na Sprint 4).

    O código público (`ND-IM-00001`) nasce do id na primeira gravação e nunca muda: é o que
    aparece para o cliente e na URL (`/anuncio/<codigo>-<slug>/`, Parte B).
    """

    class Categoria(models.TextChoices):
        IMOVEL = "imovel", "Imóvel"
        VEICULO = "veiculo", "Veículo"

    class Situacao(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EM_MODERACAO = "em_moderacao", "Em análise"
        PUBLICADO = "publicado", "Publicado"
        PAUSADO = "pausado", "Pausado"
        EXPIRADO = "expirado", "Expirado"
        REMOVIDO = "removido", "Excluído"

    class PausadoPor(models.TextChoices):
        """Quem pausou: só a pausa por atraso volta sozinha quando o pagamento entra."""

        CLIENTE = "cliente", "Anunciante"
        ATRASO = "atraso", "Pagamento em atraso"
        DOWNGRADE = "downgrade", "Troca para plano menor"

    # Contam no limite do plano (ARQUITETURA §5, regra 1). Pausados e rascunhos não contam.
    SITUACOES_NO_PLANO = (Situacao.PUBLICADO, Situacao.EM_MODERACAO)

    anunciante = models.ForeignKey(
        Anunciante, on_delete=models.PROTECT, related_name="anuncios", verbose_name="anunciante"
    )
    categoria = models.CharField(
        "categoria", max_length=10, choices=Categoria.choices, default=Categoria.IMOVEL
    )
    codigo = models.CharField("código", max_length=16, unique=True, null=True, blank=True, editable=False)
    titulo = models.CharField("título", max_length=120)
    slug = models.SlugField("slug", max_length=140, blank=True, editable=False)
    descricao = models.TextField("descrição", blank=True)
    preco = models.DecimalField(
        "preço", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name="anuncios", verbose_name="cidade"
    )
    bairro = models.ForeignKey(
        Bairro,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anuncios",
        verbose_name="bairro",
    )
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.RASCUNHO, db_index=True
    )
    pausado_por = models.CharField("pausado por", max_length=10, choices=PausadoPor.choices, blank=True)
    motivo_moderacao = models.TextField(
        "motivo da moderação", blank=True, help_text="Mostrado ao anunciante quando o anúncio é recusado."
    )
    moderado_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True)
    expira_em = models.DateTimeField("expira em", null=True, blank=True, db_index=True)
    destaque_ate = models.DateTimeField("destaque até", null=True, blank=True)
    removido_em = models.DateTimeField("excluído em", null=True, blank=True, editable=False)
    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    history = HistoricalRecords(verbose_name="histórico do anúncio")

    class Meta:
        verbose_name = "anúncio"
        verbose_name_plural = "anúncios"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["anunciante", "situacao"], name="anuncio_loja_situacao")]

    def __str__(self) -> str:
        """Ex.: 'ND-IM-00012 · Casa 3 quartos'."""
        return f"{self.codigo or 'novo'} · {self.titulo}"

    def save(self, *args, **kwargs) -> None:
        """Na primeira gravação gera o código público a partir do id (sem corrida: o id é do banco)."""
        novo = self.pk is None
        super().save(*args, **kwargs)
        if novo and not self.codigo:
            self.codigo = f"{PREFIXO_CODIGO[self.categoria]}-{self.pk:05d}"
            type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)
            self.history.filter(id=self.pk).update(codigo=self.codigo)  # o 1º registro do histórico também

    @property
    def capa(self) -> "Foto | None":
        """A primeira foto já processada (ordem do anunciante)."""
        return next((foto for foto in self.fotos.all() if foto.imagem), None)

    @property
    def local(self) -> str:
        """Ex.: 'Tangará da Serra · Jardim Europa'."""
        return f"{self.cidade.nome} · {self.bairro.nome}" if self.bairro else self.cidade.nome

    @property
    def dias_para_expirar(self) -> int | None:
        """Dias inteiros até expirar (só publicado)."""
        if self.situacao != self.Situacao.PUBLICADO or not self.expira_em:
            return None
        return max((self.expira_em - timezone.now()).days, 0)


class DetalheImovel(models.Model):
    """Ficha do imóvel. Endereço e ponto exato são privados: o público vê conforme `exibir_localizacao`."""

    class Tipo(models.TextChoices):
        CASA = "casa", "Casa"
        APARTAMENTO = "apartamento", "Apartamento"
        KITNET = "kitnet", "Kitnet"
        TERRENO = "terreno", "Terreno"
        CHACARA = "chacara", "Chácara"
        SITIO = "sitio", "Sítio"
        FAZENDA = "fazenda", "Fazenda"
        SALA_COMERCIAL = "sala_comercial", "Sala comercial"
        BARRACAO = "barracao", "Barracão"

    class Modalidade(models.TextChoices):
        VENDA = "venda", "Venda"
        ALUGUEL = "aluguel", "Aluguel"

    class ExibirLocalizacao(models.TextChoices):
        EXATA = "exata", "Exata (o ponto marcado)"
        APROXIMADA = "aproximada", "Aproximada (círculo de cerca de 300 m)"
        SO_BAIRRO = "so_bairro", "Só o bairro"

    anuncio = models.OneToOneField(
        Anuncio, on_delete=models.CASCADE, primary_key=True, related_name="imovel", verbose_name="anúncio"
    )
    tipo = models.CharField("tipo de imóvel", max_length=16, choices=Tipo.choices)
    modalidade = models.CharField(
        "modalidade", max_length=8, choices=Modalidade.choices, default=Modalidade.VENDA
    )
    quartos = models.PositiveSmallIntegerField("quartos", default=0)
    banheiros = models.PositiveSmallIntegerField("banheiros", default=0)
    vagas = models.PositiveSmallIntegerField("vagas de garagem", default=0)
    area_total = models.DecimalField(
        "área total (m²)", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("1"))]
    )
    area_construida = models.DecimalField(
        "área construída (m²)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    iptu = models.DecimalField(
        "IPTU por ano (R$)", max_digits=10, decimal_places=2, null=True, blank=True, help_text="Opcional."
    )
    endereco = models.CharField(
        "endereço (privado)",
        max_length=200,
        blank=True,
        help_text=(
            "Nunca aparece no site; serve para a equipe conferir. "
            "O público vê só o que você escolher no mapa."
        ),
    )
    ponto = models.PointField("ponto no mapa", srid=4326, null=True, blank=True)
    exibir_localizacao = models.CharField(
        "localização no site",
        max_length=10,
        choices=ExibirLocalizacao.choices,
        default=ExibirLocalizacao.APROXIMADA,
    )

    history = HistoricalRecords(verbose_name="histórico da ficha do imóvel")

    class Meta:
        verbose_name = "ficha do imóvel"
        verbose_name_plural = "fichas de imóvel"

    def __str__(self) -> str:
        """Ex.: 'Casa para venda'."""
        return f"{self.get_tipo_display()} para {self.get_modalidade_display().lower()}"

    @property
    def aluguel(self) -> bool:
        """Preço mensal (mostra "/mês")."""
        return self.modalidade == self.Modalidade.ALUGUEL

    @property
    def resumo(self) -> str:
        """Linha de ficha do card. Ex.: "3 qts · 2 banh · 2 vagas · 180 m²" (2 ha acima de 10.000 m²)."""
        partes = [
            f"{valor} {sufixo}"
            for valor, sufixo in ((self.quartos, "qts"), (self.banheiros, "banh"), (self.vagas, "vagas"))
            if valor
        ]
        area = self.area_total
        if area >= 10000:
            partes.append(f"{area / 10000:g} ha".replace(".", ","))
        else:
            partes.append(f"{area:g} m²".replace(".", ","))
        return " · ".join(partes)


class Foto(models.Model):
    """Foto do anúncio. A de menor `ordem` é a capa. O envio (`original`) é apagado depois do WebP."""

    anuncio = models.ForeignKey(
        Anuncio, on_delete=models.CASCADE, related_name="fotos", verbose_name="anúncio"
    )
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    original = models.FileField(upload_to=caminho_foto_original, blank=True, editable=False)
    imagem = models.FileField("foto (1600 px)", upload_to=caminho_foto, blank=True, editable=False)
    miniatura = models.FileField("miniatura (400 px)", upload_to=caminho_foto, blank=True, editable=False)
    # JPEG 1200×630 para a prévia de compartilhamento (WhatsApp/Facebook não exibem WebP com segurança).
    compartilhamento = models.FileField(
        "compartilhamento (JPEG 1200×630)", upload_to=caminho_foto, blank=True, editable=False
    )
    criado_em = models.DateTimeField("enviada em", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "foto"
        verbose_name_plural = "fotos"
        ordering = ["ordem", "pk"]

    def __str__(self) -> str:
        """Ex.: 'Foto 1 de ND-IM-00012'."""
        return f"Foto {self.ordem + 1} de {self.anuncio.codigo}"

    @property
    def processando(self) -> bool:
        """Ainda sem o WebP (o Celery não terminou)."""
        return not self.imagem


class AnuncioEmModeracao(Anuncio):
    """Proxy para a "Fila de moderação" no admin: só anúncios em análise, com as fotos grandes."""

    class Meta:
        proxy = True
        verbose_name = "anúncio em moderação"
        verbose_name_plural = "fila de moderação"
