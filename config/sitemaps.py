"""sitemap.xml do site: páginas públicas fixas, a vitrine de cada loja visível (ARQUITETURA §7) e
os anúncios publicados (só os visíveis ao público).

Rascunhos legais e páginas "em breve" ficam de fora (elas também pedem noindex).
O domínio vem da própria requisição (sem o app django.contrib.sites).
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from anunciantes.models import Anunciante
from anunciantes.services import lojas_visiveis
from anuncios.models import Anuncio
from anuncios.services import anuncios_visiveis, url_publica


class PaginasSitemap(Sitemap):
    """Páginas públicas prontas."""

    changefreq = "weekly"

    def items(self) -> list[str]:
        """Nomes das rotas."""
        return [
            "core:inicio",
            "core:sobre",
            "core:planos",
            "core:anuncie",
            "core:contato",
            "anunciantes:lojas",
        ]

    def location(self, item: str) -> str:
        """URL da rota."""
        return reverse(item)

    def priority(self, item: str) -> float:
        """Home e lista de lojas acima das institucionais."""
        return 1.0 if item in ("core:inicio", "anunciantes:lojas") else 0.5


class LojasSitemap(Sitemap):
    """Uma entrada por loja visível (ativa, em cidade atendida)."""

    changefreq = "daily"
    priority = 0.8

    def items(self):
        """Lojas visíveis, em ordem estável."""
        return lojas_visiveis().order_by("pk")

    def location(self, item: Anunciante) -> str:
        """/loja/<slug>/."""
        return reverse("anunciantes:loja", args=[item.slug])

    def lastmod(self, item: Anunciante):
        """Última alteração da loja."""
        return item.atualizado_em


class AnunciosSitemap(Sitemap):
    """Uma entrada por anúncio visível (publicado, loja ativa, cidade liberada)."""

    changefreq = "daily"
    priority = 0.9
    limit = 5000

    def items(self):
        """Anúncios visíveis, em ordem estável."""
        return anuncios_visiveis().order_by("pk")

    def location(self, item: Anuncio) -> str:
        """/anuncio/<codigo>-<slug>/."""
        return url_publica(item)

    def lastmod(self, item: Anuncio):
        """Última alteração do anúncio."""
        return item.atualizado_em


SITEMAPS = {"paginas": PaginasSitemap, "lojas": LojasSitemap, "anuncios": AnunciosSitemap}
