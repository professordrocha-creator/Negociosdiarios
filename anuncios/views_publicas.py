"""Views públicas do anúncio: a página /anuncio/<codigo>-<slug>/ e o botão do WhatsApp.

Regras: só anúncio visível (publicado, loja ativa, cidade liberada) aparece. O que já esteve no
ar e saiu (pausado, expirado, excluído, loja suspensa) mostra "não está mais disponível" com
anúncios parecidos (noindex; nunca um 404 seco). O dono vê a própria página em qualquer
situação (pré-visualização, sem contar visita). O número do WhatsApp nunca vai no HTML.
"""

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from anuncios import services
from anuncios.models import Anuncio
from estatisticas import services as estatisticas


def _do_dono(request: HttpRequest, anuncio: Anuncio) -> bool:
    """O visitante logado é o dono do anúncio?"""
    return request.user.is_authenticated and request.user.pk == anuncio.anunciante.usuario_id


def _contexto_pagina(request: HttpRequest, anuncio: Anuncio, previa: bool) -> dict:
    """Tudo o que a página do anúncio mostra (SEO, galeria, ficha, mapa, loja e "mais desta loja")."""
    fotos = [foto for foto in anuncio.fotos.all() if foto.imagem]
    url = settings.SITE_URL + services.url_publica(anuncio)
    imovel = anuncio.imovel
    descricao = (anuncio.descricao or "").strip().replace("\n", " ")
    resumo_seo = f"{imovel} em {anuncio.local}: {imovel.resumo}. {descricao}"[:300].rstrip()
    capa = fotos[0] if fotos else None
    return {
        "tela": "anuncio",
        "anuncio": anuncio,
        "imovel": imovel,
        "loja": anuncio.anunciante,
        "fotos": fotos,
        "url_canonica": url,
        "descricao_seo": resumo_seo,
        "imagem_og": settings.SITE_URL + capa.compartilhamento.url if capa and capa.compartilhamento else "",
        "localizacao": services.localizacao_publica(anuncio),
        "mensagem_whatsapp": services.mensagem_whatsapp(anuncio),
        "mais_da_loja": [services.para_vitrine(a) for a in services.mais_da_loja(anuncio)],
        "visualizacoes": estatisticas.total_de_visualizacoes(anuncio),
        "previa": previa,
        "schema": _schema(anuncio, url, fotos),
    }


def _schema(anuncio: Anuncio, url: str, fotos: list) -> dict:
    """schema.org (oferta de imóvel) para os buscadores. Sem endereço exato nem telefone."""
    imovel = anuncio.imovel
    dados = {
        "@context": "https://schema.org",
        "@type": "Offer",
        "url": url,
        "name": anuncio.titulo,
        "description": (anuncio.descricao or "")[:500],
        "sku": anuncio.codigo,
        "price": str(anuncio.preco),
        "priceCurrency": "BRL",
        "availability": "https://schema.org/InStock",
        "businessFunction": "http://purl.org/goodrelations/v1#" + ("LeaseOut" if imovel.aluguel else "Sell"),
        "seller": {
            "@type": "RealEstateAgent",
            "name": anuncio.anunciante.nome_publico,
            "url": settings.SITE_URL + f"/loja/{anuncio.anunciante.slug}/",
        },
        "itemOffered": {
            "@type": "Accommodation"
            if imovel.tipo not in ("terreno", "fazenda", "sitio", "chacara")
            else "Place",
            "name": anuncio.titulo,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": anuncio.cidade.nome,
                "addressRegion": anuncio.cidade.uf_id,
                "addressCountry": "BR",
            },
        },
    }
    if fotos:
        dados["image"] = [settings.SITE_URL + foto.imagem.url for foto in fotos[:5]]
    if imovel.quartos:
        dados["itemOffered"]["numberOfRooms"] = imovel.quartos
    dados["itemOffered"]["floorSize"] = {
        "@type": "QuantitativeValue",
        "value": str(imovel.area_total),
        "unitCode": "MTK",
    }
    return dados


@require_GET
def publico(request: HttpRequest, codigo: str, slug: str = "") -> HttpResponse:
    """Página do anúncio. Slug diferente do atual redireciona (301) para a URL canônica."""
    anuncio = get_object_or_404(
        Anuncio.objects.select_related("anunciante", "anunciante__cidade", "cidade", "bairro", "imovel"),
        codigo=codigo.upper(),
    )
    if getattr(anuncio, "imovel", None) is None:
        raise Http404
    if services.visivel(anuncio):
        if slug != anuncio.slug or codigo != anuncio.codigo:
            return HttpResponseRedirect(services.url_publica(anuncio), status=301)
        estatisticas.registrar(request, anuncio, estatisticas.VISUALIZACAO)
        return render(request, "anuncios/publico.html", _contexto_pagina(request, anuncio, previa=False))
    if _do_dono(request, anuncio) and anuncio.situacao != Anuncio.Situacao.REMOVIDO:
        return render(request, "anuncios/publico.html", _contexto_pagina(request, anuncio, previa=True))
    nunca_publicado = anuncio.publicado_em is None
    demo_escondido = anuncio.demo and not settings.MOSTRAR_DEMO
    if nunca_publicado or demo_escondido:
        raise Http404  # nunca esteve no ar (ou é demonstração desligada): não existe para o público
    removido = anuncio.situacao == Anuncio.Situacao.REMOVIDO
    return render(
        request,
        "anuncios/indisponivel.html",
        {
            "tela": "anuncio_indisponivel",
            "anuncio": anuncio,
            "parecidos": [services.para_vitrine(a) for a in services.parecidos(anuncio)],
        },
        status=410 if removido else 404,
    )


@require_GET
def whatsapp(request: HttpRequest, codigo: str) -> HttpResponse:
    """Conta o clique e redireciona para o wa.me com a mensagem pronta (o número não fica no HTML).

    Anúncio fora do ar volta para a página dele (que explica que não está mais disponível).
    """
    anuncio = get_object_or_404(Anuncio.objects.select_related("anunciante"), codigo=codigo.upper())
    if not services.visivel(anuncio):
        return redirect(services.url_publica(anuncio))
    estatisticas.registrar(request, anuncio, estatisticas.CLIQUE_WHATSAPP)
    resposta = HttpResponseRedirect(services.link_whatsapp(anuncio))
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    return resposta
