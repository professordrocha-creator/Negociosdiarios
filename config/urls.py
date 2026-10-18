"""URLs raiz do projeto. Cada app inclui as suas próprias rotas."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from config.sitemaps import SITEMAPS


def sitemap_ou_404(request, **kwargs):
    """sitemap.xml normal; com SITE_NOINDEX (servidor de teste) não existe (404)."""
    from django.http import Http404

    if settings.SITE_NOINDEX:
        raise Http404("Sitemap desligado no servidor de teste.")
    return sitemap(request, **kwargs)


urlpatterns = [
    # Admin em endereço secreto (ADMIN_URL no .env) e com código para navegador novo
    # (config/admin_site.py). Não existe rota /admin/: quem tentar recebe 404.
    path(settings.ADMIN_URL, admin.site.urls),
    path("sitemap.xml", sitemap_ou_404, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("", include("contas.urls")),  # /entrar/ e /sair/ (cliente)
    path("", include("anunciantes.urls")),  # /painel/, /loja/, /lojas/, /cadastro/
    path("", include("planos.urls")),  # /painel/plano/
    path("", include("pagamentos.urls")),  # /painel/faturas/, /fatura/<token>/
    path("", include("publicidade.urls")),  # /publicidade/clique/<id>/
    path("", include("privacidade.urls")),  # /painel/meus-dados/, /painel/termos-atualizados/
    path("", include("moderacao.urls")),  # /denunciar/
    path("guia/", include("guia.urls")),  # /guia/aceite/<token>/ (Guia de Negócios)
    path("", include("anuncios.urls")),  # /painel/anuncios/
    path("", include("busca.urls")),  # /imoveis/, /veiculos/ (e por cidade)
    path("", include("core.urls")),
]

# Em dev, com mídia em pasta local, o próprio Django serve /media/. Em produção a mídia
# vem do bucket (R2) pelo domínio público, e o `static()` não faz nada com DEBUG desligado.
if settings.ARMAZENAMENTO == "local":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
