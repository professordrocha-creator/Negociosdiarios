"""Catálogo de veículos: marca → modelo → versão (Tabela FIPE). Nunca texto livre (BOAS_PRATICAS §1).

Carregado de `catalogo/dados/fipe.csv` pelo comando `carregar_catalogo` (idempotente). Nada é
apagado na recarga: versões que saíram da FIPE continuam valendo para os anúncios antigos; o admin
pode só desmarcar "ativo" para esconder do formulário. Preço FIPE não é guardado por enquanto.
"""

from django.db import models


class TipoVeiculo(models.TextChoices):
    """Tipo de veículo. "Caminhonete" separa as picapes dos carros (a FIPE junta os dois)."""

    CARRO = "carro", "Carro"
    CAMINHONETE = "caminhonete", "Caminhonete"
    MOTO = "moto", "Moto"
    CAMINHAO = "caminhao", "Caminhão"


class Marca(models.Model):
    """Fabricante (ex.: Toyota). Uma só marca serve a vários tipos (Agrale faz carro, moto e caminhão)."""

    nome = models.CharField("nome", max_length=60)
    slug = models.SlugField("slug", max_length=70, unique=True)
    ativo = models.BooleanField("ativo", default=True, help_text="Desmarque para esconder do formulário.")

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        ordering = ["nome"]

    def __str__(self) -> str:
        """Nome da marca."""
        return self.nome


class Modelo(models.Model):
    """Modelo de uma marca num tipo (ex.: Toyota Hilux, caminhonete)."""

    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="modelos", verbose_name="marca")
    tipo = models.CharField("tipo", max_length=12, choices=TipoVeiculo.choices, db_index=True)
    nome = models.CharField("nome", max_length=80)
    slug = models.SlugField("slug", max_length=90)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "modelo"
        verbose_name_plural = "modelos"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["marca", "tipo", "slug"], name="modelo_unico_por_marca_e_tipo")
        ]

    def __str__(self) -> str:
        """Ex.: 'Toyota Hilux'."""
        return f"{self.marca.nome} {self.nome}"


class Versao(models.Model):
    """Versão do modelo como na FIPE (ex.: 'CD SRV 4x4 2.8 Diesel Aut.'), com o código FIPE do modelo."""

    modelo = models.ForeignKey(
        Modelo, on_delete=models.PROTECT, related_name="versoes", verbose_name="modelo"
    )
    nome = models.CharField("nome", max_length=120)
    codigo_fipe = models.CharField(
        "código FIPE", max_length=20, blank=True, db_index=True, help_text="Código do modelo na API da FIPE."
    )
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "versão"
        verbose_name_plural = "versões"
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(fields=["modelo", "nome"], name="versao_unica_por_modelo")]

    def __str__(self) -> str:
        """Ex.: 'Toyota Hilux CD SRV 4x4 2.8 Diesel Aut.'."""
        return f"{self.modelo} {self.nome}"
