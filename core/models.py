"""Modelos do app core: abrangência geográfica (estados, cidades, regiões, bairros) e identidade do site.

Ver docs/ARQUITETURA.md §9. Os registros vêm do comando `carregar_municipios`;
o admin só liga e desliga o que aparece no site.
"""

import uuid
from pathlib import PurePath

from django.contrib.gis.db import models
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator


class MarcaDemo(models.Model):
    """Marca registros de demonstração (regra do CLAUDE.md, "Dados de demonstração").

    Todo modelo com dados que o `criar_dados_demo` cria herda daqui; o
    `apagar_dados_demo` remove tudo com `demo=True` de uma vez. Não editável no admin:
    só os comandos de demonstração ligam a marca.
    """

    demo = models.BooleanField(
        "demonstração",
        default=False,
        db_index=True,
        editable=False,
        help_text="Criado pelo criar_dados_demo. Some com o apagar_dados_demo e nunca vai para produção.",
    )

    class Meta:
        abstract = True


class Estado(models.Model):
    """Unidade da federação. Só estados `liberado=True` aparecem no site."""

    uf = models.CharField("UF", max_length=2, unique=True, help_text="Sigla em maiúsculas, ex.: MT.")
    nome = models.CharField("nome", max_length=50)
    liberado = models.BooleanField(
        "liberado",
        default=False,
        help_text="Mostra o estado no site. Com dois ou mais liberados, o seletor de estado aparece sozinho.",
    )

    class Meta:
        verbose_name = "estado"
        verbose_name_plural = "estados"
        ordering = ["nome"]

    def __str__(self) -> str:
        """Ex.: 'Mato Grosso (MT)'."""
        return f"{self.nome} ({self.uf})"


class Cidade(models.Model):
    """Município do IBGE. Só cidades `liberada=True` de estados liberados aparecem no site.

    `uf` é chave estrangeira para `Estado.uf` (e não para o id): no banco a
    coluna guarda a própria sigla ("MT"), o que deixa consultas e URLs simples.
    O slug é único dentro do estado, não no país: existem cidades com o mesmo
    nome em estados diferentes (ex.: Tangará/RN e Tangará/SC), e por isso a UF
    está em todas as URLs.
    """

    codigo_ibge = models.PositiveIntegerField(
        "código IBGE", unique=True, help_text="Código de 7 dígitos do município no IBGE."
    )
    nome = models.CharField("nome", max_length=100)
    slug = models.SlugField("slug", max_length=100, help_text="Nome na URL, sem acentos. Gerado na carga.")
    uf = models.ForeignKey(
        Estado,
        to_field="uf",
        db_column="uf",
        on_delete=models.PROTECT,
        related_name="cidades",
        verbose_name="UF",
    )
    liberada = models.BooleanField(
        "liberada",
        default=False,
        help_text="Mostra a cidade no site e no cadastro de anúncios.",
    )
    liberada_pela_demo = models.BooleanField(
        "liberada pela demonstração",
        default=False,
        editable=False,
        help_text="Liberada pelo criar_dados_demo; o apagar_dados_demo desfaz só essas.",
    )
    ponto = models.PointField("ponto", srid=4326, help_text="Sede do município (longitude/latitude, WGS 84).")

    class Meta:
        verbose_name = "cidade"
        verbose_name_plural = "cidades"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["uf", "slug"], name="cidade_slug_unico_por_uf"),
        ]
        indexes = [
            models.Index(fields=["liberada", "uf"], name="cidade_liberada_uf_idx"),
        ]

    def __str__(self) -> str:
        """Ex.: 'Tangará da Serra/MT'."""
        return f"{self.nome}/{self.uf_id}"


# --- Regiões e bairros (ARQUITETURA §9) ----------------------------------------------------


class Regiao(MarcaDemo):
    """Agrupamento de cidades criado pelo admin (ex.: "Região de Tangará"), para filtros e vitrines."""

    nome = models.CharField("nome", max_length=80, unique=True, help_text="Até 80 caracteres.")
    slug = models.SlugField("endereço", max_length=80, unique=True, help_text="Usado em URLs e filtros.")
    cidades = models.ManyToManyField(Cidade, related_name="regioes", blank=True, verbose_name="cidades")

    class Meta:
        verbose_name = "região"
        verbose_name_plural = "regiões"
        ordering = ["nome"]

    def __str__(self) -> str:
        """Nome da região."""
        return self.nome


class Bairro(MarcaDemo):
    """Bairro de uma cidade (escolhido no anúncio; nunca texto livre). Inativo some das listas."""

    cidade = models.ForeignKey(
        Cidade, on_delete=models.PROTECT, related_name="bairros", verbose_name="cidade"
    )
    nome = models.CharField("nome", max_length=100)
    slug = models.SlugField("endereço", max_length=100, help_text="Único dentro da cidade.")
    ativo = models.BooleanField(
        "ativo", default=True, help_text="Desmarque para tirar das listas sem apagar."
    )

    class Meta:
        verbose_name = "bairro"
        verbose_name_plural = "bairros"
        ordering = ["cidade__nome", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["cidade", "slug"], name="bairro_slug_unico_por_cidade")
        ]

    def __str__(self) -> str:
        """Ex.: 'Jardim Europa (Tangará da Serra/MT)'."""
        return f"{self.nome} ({self.cidade})"


# --- Identidade do site, valores e textos de ajuda (editáveis no admin) -------------------

CHAVE_CACHE_CONFIGURACAO = "core:configuracao"
CHAVE_CACHE_AJUDA = "core:textos_ajuda"


def caminho_identidade(instancia, nome_arquivo: str) -> str:
    """Arquivos da identidade com nome aleatório (UUID): nunca o nome enviado (SEGURANCA.md)."""
    return f"identidade/{uuid.uuid4().hex}{PurePath(nome_arquivo).suffix.lower()}"


class Configuracao(models.Model):
    """Identidade do site e contatos: registro único (pk=1), editado no admin.

    O context processor `site` lê daqui (com cache, limpo ao salvar). Na primeira
    leitura o registro nasce com os valores `SITE_*` do settings (`core.services.configuracao`).
    Os favicons são gerados a partir do símbolo para fundo claro (`gerar_favicons`).
    """

    ID_UNICO = 1

    nome = models.CharField("nome do site", max_length=60)
    linha_regiao = models.CharField(
        "linha da região",
        max_length=80,
        help_text=(
            'Ex.: "Imóveis, veículos e serviços de MT". Aparece no topo do celular (com o símbolo), '
            "no texto alternativo do logo e nos e-mails."
        ),
    )
    slogan = models.CharField(
        "slogan", max_length=120, help_text="Até 120 caracteres. Usado na Sobre e no rodapé."
    )
    empresa = models.CharField(
        "empresa responsável", max_length=120, help_text="Quem opera o site (documentos legais)."
    )
    cidade_sede = models.CharField("cidade-sede", max_length=80, help_text='Ex.: "Tangará da Serra, MT".')

    logo_completo = models.FileField(
        "logo completo",
        upload_to=caminho_identidade,
        blank=True,
        help_text=(
            "SVG ou PNG horizontal para fundo escuro, com o nome e o subtítulo (ideal 5:1). Usado no topo "
            "(computador e tablet) e no rodapé. No celular o topo mostra o símbolo + o nome. "
            "Vazio = logo padrão."
        ),
    )
    simbolo_claro = models.FileField(
        "símbolo para fundo claro",
        upload_to=caminho_identidade,
        blank=True,
        help_text=(
            "SVG ou PNG quadrado (ideal 512×512), fundo transparente. Gera o favicon. Vazio = símbolo padrão."
        ),
    )
    simbolo_escuro = models.FileField(
        "símbolo para fundo escuro",
        upload_to=caminho_identidade,
        blank=True,
        help_text="SVG ou PNG para o topo e o rodapé (fundo azul). Vazio = símbolo padrão.",
    )
    imagem_compartilhamento = models.FileField(
        "imagem de compartilhamento",
        upload_to=caminho_identidade,
        blank=True,
        help_text="JPG ou PNG 1200×630 que aparece ao compartilhar o site (WhatsApp, Facebook).",
    )
    favicon_ico = models.FileField(upload_to=caminho_identidade, blank=True, editable=False)
    favicon_32 = models.FileField(upload_to=caminho_identidade, blank=True, editable=False)
    favicon_180 = models.FileField(upload_to=caminho_identidade, blank=True, editable=False)
    favicon_512 = models.FileField(upload_to=caminho_identidade, blank=True, editable=False)

    whatsapp = models.CharField(
        "WhatsApp", max_length=16, blank=True, help_text='Com DDD, ex.: (65) 99999-0000. Vazio = "em breve".'
    )
    email_contato = models.EmailField("e-mail de contato")
    email_privacidade = models.EmailField("e-mail de privacidade (LGPD)")
    endereco = models.CharField("endereço", max_length=200, blank=True)
    cnpj = models.CharField(
        "CNPJ", max_length=18, blank=True, help_text="Pontuação opcional; guardado só com dígitos."
    )
    instagram = models.CharField(
        "Instagram", max_length=30, blank=True, help_text="Só o usuário, sem @ (ex.: negociosdiarios)."
    )

    sobre_quem_somos = models.TextField(
        "Sobre: quem somos", help_text="Separe os parágrafos com uma linha em branco."
    )
    sobre_missao = models.TextField("Sobre: missão", max_length=400, help_text="Até 400 caracteres.")
    sobre_visao = models.TextField("Sobre: visão", max_length=400, help_text="Até 400 caracteres.")

    limite_simbolo_kb = models.PositiveIntegerField(
        "limite do símbolo (KB)", default=500, help_text="Tamanho máximo de cada arquivo de símbolo."
    )
    limite_compartilhamento_kb = models.PositiveIntegerField(
        "limite da imagem de compartilhamento (KB)", default=1024
    )
    # Logo e capa das lojas (docs/TELAS.md §1).
    limite_logo_kb = models.PositiveIntegerField("limite do logo da loja (KB)", default=2048)
    logo_min_px = models.PositiveIntegerField(
        "lado mínimo do logo (px)",
        default=400,
        help_text="O logo é recortado em quadrado a partir do centro.",
    )
    limite_capa_kb = models.PositiveIntegerField("limite da capa da loja (KB)", default=4096)
    capa_min_largura_px = models.PositiveIntegerField("largura mínima da capa (px)", default=1200)
    capa_min_altura_px = models.PositiveIntegerField(
        "altura mínima da capa (px)", default=300, help_text="A capa é recortada na proporção 4:1 (1600×400)."
    )
    # Fotos e textos dos anúncios (docs/TELAS.md §1).
    max_fotos_anuncio = models.PositiveSmallIntegerField(
        "fotos por anúncio", default=10, help_text="A primeira foto é a capa do anúncio."
    )
    limite_foto_anuncio_kb = models.PositiveIntegerField("limite de cada foto de anúncio (KB)", default=8192)
    foto_min_largura_px = models.PositiveIntegerField("largura mínima da foto de anúncio (px)", default=800)
    foto_min_altura_px = models.PositiveIntegerField("altura mínima da foto de anúncio (px)", default=600)
    titulo_min_caracteres = models.PositiveSmallIntegerField(
        "título do anúncio: mínimo de caracteres", default=10
    )
    titulo_max_caracteres = models.PositiveSmallIntegerField(
        "título do anúncio: máximo de caracteres",
        default=80,
        validators=[MaxValueValidator(120)],
        help_text="No máximo 120.",
    )
    descricao_max_caracteres = models.PositiveIntegerField(
        "descrição do anúncio: máximo de caracteres", default=3000
    )

    # Regras do negócio: prazos e moderação (nunca fixos no código).
    class Moderacao(models.TextChoices):
        PRIMEIRO = "primeiro", "Só o primeiro anúncio de cada loja"
        TODOS = "todos", "Todos os anúncios"
        NENHUM = "nenhum", "Nenhum (publicação direta)"

    carencia_dias = models.PositiveSmallIntegerField(
        "carência de pagamento (dias)",
        default=5,
        help_text="Dias depois do vencimento até a assinatura ficar em atraso e os anúncios serem pausados.",
    )
    expiracao_dias = models.PositiveSmallIntegerField(
        "validade do anúncio (dias)",
        default=60,
        validators=[MinValueValidator(1)],
        help_text="Depois disso o anúncio sai do ar (expira) até o anunciante clicar em Renovar.",
    )
    aviso_expiracao_dias = models.PositiveSmallIntegerField(
        "aviso de expiração (dias antes)",
        default=5,
        help_text='Quantos dias antes de expirar o painel mostra "Expira em X dias" e o botão Renovar.',
    )
    moderacao = models.CharField(
        "anúncios que passam por moderação",
        max_length=10,
        choices=Moderacao.choices,
        default=Moderacao.PRIMEIRO,
        help_text="Os que não passam são publicados direto ao enviar.",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "identidade do site"
        verbose_name_plural = "identidade do site"

    def __str__(self) -> str:
        """Nome fixo no admin."""
        return "Identidade do site"

    def save(self, *args, **kwargs) -> None:
        """Sempre o registro 1 (registro único); limpa o cache lido pelo context processor."""
        self.pk = self.ID_UNICO
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_CONFIGURACAO)

    def delete(self, *args, **kwargs):
        """O registro único nunca é apagado."""
        raise PermissionError("A identidade do site não pode ser apagada.")

    @property
    def paragrafos_quem_somos(self) -> list[str]:
        """Parágrafos do "quem somos" (separados por linha em branco)."""
        return [p.strip() for p in self.sobre_quem_somos.split("\n\n") if p.strip()]


class ValorEmpresa(models.Model):
    """Valor da empresa mostrado na página Sobre, na ordem escolhida no admin."""

    ICONES = [
        ("verificado", "Escudo (verificado)"),
        ("pin", "Marcador de mapa"),
        ("olho", "Olho"),
        ("alerta", "Alerta"),
        ("lista", "Lista"),
        ("casa", "Casa"),
        ("carro", "Carro"),
        ("loja", "Loja"),
        ("relogio", "Relógio"),
    ]

    ordem = models.PositiveSmallIntegerField("ordem", default=0, help_text="Menor aparece primeiro.")
    icone = models.CharField("ícone", max_length=20, choices=ICONES, default="verificado")
    titulo = models.CharField("título", max_length=40, help_text="Até 40 caracteres.")
    texto = models.CharField("texto", max_length=160, help_text="Até 160 caracteres.")
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "valor da empresa"
        verbose_name_plural = "valores da empresa"
        ordering = ["ordem", "id"]

    def __str__(self) -> str:
        """Título do valor."""
        return self.titulo


class TextoAjuda(models.Model):
    """Texto da caixa "Sobre esta tela" (docs/TELAS.md), editável sem deploy.

    A `chave` é a variável "tela" da view (ex.: "planos", "cadastro"). Um item por linha.
    """

    chave = models.SlugField(
        "tela", max_length=40, unique=True, help_text='Identificador da tela, ex.: "planos".'
    )
    descricao = models.CharField("onde aparece", max_length=120, blank=True)
    texto = models.TextField(
        "texto",
        blank=True,
        help_text="Um item por linha. Sem HTML (texto puro). Em branco = a caixa não aparece.",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "texto de ajuda"
        verbose_name_plural = "textos de ajuda"
        ordering = ["chave"]

    def __str__(self) -> str:
        """Chave da tela."""
        return self.chave

    @property
    def itens(self) -> list[str]:
        """Linhas não vazias do texto."""
        return [linha.strip() for linha in self.texto.splitlines() if linha.strip()]

    def save(self, *args, **kwargs) -> None:
        """Salva e limpa o cache dos textos de ajuda."""
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_AJUDA)
