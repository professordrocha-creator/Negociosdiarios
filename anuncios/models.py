"""Modelos do app anuncios: o anúncio (base comum), os detalhes de imóvel e de veículo e as fotos.

Cada anúncio tem um detalhe conforme a categoria: `DetalheImovel` (imóvel) ou `DetalheVeiculo`
(veículo, com a versão do catálogo FIPE). Nada é apagado pelo anunciante: "excluir" muda a
situação para `removido` (exclusão lógica).
"""

import uuid
from decimal import Decimal
from pathlib import PurePath

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.utils import timezone
from simple_history.models import HistoricalRecords

from anunciantes.models import Anunciante
from catalogo.models import Versao
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

    @property
    def e_veiculo(self) -> bool:
        """Anúncio de veículo?"""
        return self.categoria == self.Categoria.VEICULO

    @property
    def detalhe(self) -> "DetalheImovel | DetalheVeiculo | None":
        """A ficha da categoria (imóvel ou veículo), ou None se ainda não existe."""
        return getattr(self, "veiculo" if self.e_veiculo else "imovel", None)

    @property
    def aluguel(self) -> bool:
        """Preço mensal (só imóvel para alugar)."""
        detalhe = self.detalhe
        return bool(detalhe and getattr(detalhe, "aluguel", False))


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


class DetalheVeiculo(models.Model):
    """Ficha do veículo: versão do catálogo FIPE (marca → modelo → versão), ano, km e equipamentos.

    Placa: só o último dígito, e só se o anunciante quiser (docs/LGPD.md §4: nunca a placa inteira).
    """

    class Combustivel(models.TextChoices):
        FLEX = "flex", "Flex"
        GASOLINA = "gasolina", "Gasolina"
        ETANOL = "etanol", "Etanol"
        DIESEL = "diesel", "Diesel"
        HIBRIDO = "hibrido", "Híbrido"
        ELETRICO = "eletrico", "Elétrico"
        GNV = "gnv", "GNV"

    class Cambio(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATICO = "automatico", "Automático"
        AUTOMATIZADO = "automatizado", "Automatizado"
        CVT = "cvt", "CVT"

    class Cor(models.TextChoices):
        BRANCO = "branco", "Branco"
        PRETO = "preto", "Preto"
        PRATA = "prata", "Prata"
        CINZA = "cinza", "Cinza"
        VERMELHO = "vermelho", "Vermelho"
        AZUL = "azul", "Azul"
        VERDE = "verde", "Verde"
        AMARELO = "amarelo", "Amarelo"
        MARROM = "marrom", "Marrom"
        BEGE = "bege", "Bege"
        LARANJA = "laranja", "Laranja"
        DOURADO = "dourado", "Dourado"
        OUTRA = "outra", "Outra"

    class Opcional(models.TextChoices):
        AR_CONDICIONADO = "ar_condicionado", "Ar-condicionado"
        DIRECAO = "direcao", "Direção hidráulica ou elétrica"
        VIDROS_ELETRICOS = "vidros_eletricos", "Vidros elétricos"
        TRAVAS_ELETRICAS = "travas_eletricas", "Travas elétricas"
        ALARME = "alarme", "Alarme"
        AIRBAG = "airbag", "Airbag"
        FREIO_ABS = "freio_abs", "Freio ABS"
        MULTIMIDIA = "multimidia", "Central multimídia"
        CAMERA_DE_RE = "camera_de_re", "Câmera de ré"
        SENSOR_ESTACIONAMENTO = "sensor_estacionamento", "Sensor de estacionamento"
        RODAS_LIGA = "rodas_liga", "Rodas de liga leve"
        BANCOS_COURO = "bancos_couro", "Bancos de couro"
        PILOTO_AUTOMATICO = "piloto_automatico", "Piloto automático"
        TETO_SOLAR = "teto_solar", "Teto solar"
        TRACAO_4X4 = "tracao_4x4", "Tração 4x4"
        CAPOTA = "capota", "Capota marítima"
        UNICO_DONO = "unico_dono", "Único dono"
        REVISOES_EM_DIA = "revisoes_em_dia", "Revisões em dia"

    PORTAS = [(2, "2"), (3, "3"), (4, "4"), (5, "5")]

    anuncio = models.OneToOneField(
        Anuncio, on_delete=models.CASCADE, primary_key=True, related_name="veiculo", verbose_name="anúncio"
    )
    versao = models.ForeignKey(
        Versao, on_delete=models.PROTECT, related_name="anuncios", verbose_name="versão"
    )
    ano_fabricacao = models.PositiveSmallIntegerField(
        "ano de fabricação", validators=[MinValueValidator(1950), MaxValueValidator(2100)]
    )
    ano_modelo = models.PositiveSmallIntegerField(
        "ano do modelo", validators=[MinValueValidator(1950), MaxValueValidator(2101)]
    )
    quilometragem = models.PositiveIntegerField(
        "quilometragem (km)", validators=[MaxValueValidator(3_000_000)]
    )
    combustivel = models.CharField("combustível", max_length=10, choices=Combustivel.choices)
    cambio = models.CharField("câmbio", max_length=12, choices=Cambio.choices)
    cor = models.CharField("cor", max_length=10, choices=Cor.choices)
    portas = models.PositiveSmallIntegerField("portas", choices=PORTAS, null=True, blank=True)
    final_placa = models.CharField(
        "final da placa",
        max_length=1,
        blank=True,
        validators=[RegexValidator(r"^\d$", "Só o último dígito da placa (0 a 9).")],
        help_text=(
            "Opcional: só o último dígito (ajuda no rodízio e no licenciamento). Nunca a placa inteira."
        ),
    )
    opcionais = ArrayField(
        models.CharField(max_length=24, choices=Opcional.choices),
        default=list,
        blank=True,
        verbose_name="opcionais",
    )

    history = HistoricalRecords(verbose_name="histórico da ficha do veículo")

    class Meta:
        verbose_name = "ficha do veículo"
        verbose_name_plural = "fichas de veículo"

    def __str__(self) -> str:
        """Ex.: 'Toyota Hilux CD SRV 2019/2020'."""
        return f"{self.versao} {self.ano_fabricacao}/{self.ano_modelo}"

    @property
    def tipo(self) -> str:
        """carro, caminhonete, moto ou caminhão (do catálogo)."""
        return self.versao.modelo.tipo

    @property
    def aluguel(self) -> bool:
        """Veículo é sempre venda."""
        return False

    @property
    def resumo(self) -> str:
        """Linha de ficha do card. Ex.: "2019/2020 · 98.000 km · Automático"."""
        km = f"{self.quilometragem:,}".replace(",", ".")
        return f"{self.ano_fabricacao}/{self.ano_modelo} · {km} km · {self.get_cambio_display()}"

    @property
    def opcionais_rotulos(self) -> list[str]:
        """Nomes dos opcionais marcados, na ordem da lista."""
        rotulos = dict(self.Opcional.choices)
        return [rotulos[o] for o in self.opcionais if o in rotulos]


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
