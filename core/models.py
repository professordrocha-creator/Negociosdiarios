"""Modelos do app core: abrangência geográfica (estados e cidades do IBGE).

Ver docs/ARQUITETURA.md §9. Os registros vêm do comando `carregar_municipios`;
o admin só liga e desliga o que aparece no site.
"""

from django.contrib.gis.db import models


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
