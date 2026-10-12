"""Views da busca: /imoveis/, /veiculos/ e as versões por cidade (/imoveis/mt/tangara-da-serra/).

Funciona sem JavaScript (formulário GET; a URL "suja" do formulário é redirecionada para a limpa) e
com HTMX (o formulário pede a mesma página; o HTMX troca só a lista e os campos dependentes e a
barra de endereço recebe a URL limpa pelo cabeçalho HX-Push-Url). Regras em busca.services.
"""

from urllib.parse import parse_qsl

from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers

from anunciantes.services import lojas_visiveis, total_anuncios
from anuncios.services import anuncios_visiveis, para_vitrine
from busca import services
from busca.forms import FORMULARIOS
from core.services import cidades_atendidas, textos_ajuda


def _mesma_url(request: HttpRequest, url_limpa: str) -> bool:
    """A requisição já está na URL limpa? Compara caminho e parâmetros decodificados (não o texto)."""
    caminho, _, parametros = url_limpa.partition("?")
    return request.path == caminho and parse_qsl(request.META.get("QUERY_STRING", "")) == parse_qsl(
        parametros
    )


def _ler_busca(request: HttpRequest, categoria: str, uf: str, cidade: str):
    """Cidade (do caminho ou do seletor), formulário, filtros válidos e opções do banco. 404 se a
    cidade do caminho não é atendida. Usado pela lista e pelo mapa (os mesmos filtros nos dois)."""
    cidade_url = services.cidade_da_url(uf, cidade) if uf else None
    if uf and cidade_url is None:
        raise Http404("Cidade não atendida.")
    dados = request.GET.copy()
    escolha = dados.pop("cidade", None)  # seletor de cidade do formulário: vira o caminho da URL
    cidade_atual = services.cidade_escolhida(escolha[-1]) if escolha is not None else cidade_url
    opcoes = services.opcoes(categoria, cidade_atual, dados.get("marca", ""))
    form = FORMULARIOS[categoria](dados, opcoes=opcoes)
    return cidade_atual, form, form.filtros(), opcoes


@require_GET
def mapa(request: HttpRequest, categoria: str, uf: str = "", cidade: str = "") -> JsonResponse:
    """JSON do mapa (Sprint 5): os mesmos filtros da lista, só o necessário por ponto (id, título curto,
    preço curto, latitude e longitude) e no máximo `MAPA_LIMITE_PONTOS`. Imóvel: o ponto PÚBLICO
    (aproximada = deslocado); só o bairro fica fora. Veículo: as lojas que permitiram o mapa."""
    cidade_atual, _form, filtros, _opcoes = _ler_busca(request, categoria, uf, cidade)
    resposta = JsonResponse(services.dados_do_mapa(categoria, cidade_atual, filtros))
    resposta["Cache-Control"] = "public, max-age=60"
    resposta["X-Robots-Tag"] = "noindex"
    return resposta


@require_GET
def cartao_anuncio(request: HttpRequest, codigo: str) -> HttpResponse:
    """Card do marcador de imóvel (foto, preço, título e link). Só anúncio visível."""
    anuncio = get_object_or_404(anuncios_visiveis(), codigo=codigo.upper())
    return render(request, "busca/_cartao_anuncio.html", {"anuncio": para_vitrine(anuncio)})


@require_GET
def cartao_loja(request: HttpRequest, slug: str) -> HttpResponse:
    """Card do marcador de loja (mapa de veículos): nome, endereço (a loja permitiu) e link."""
    loja = get_object_or_404(lojas_visiveis().filter(mostrar_no_mapa=True, ponto__isnull=False), slug=slug)
    return render(request, "busca/_cartao_loja.html", {"loja": loja, "veiculos": total_anuncios(loja)})


@require_GET
@vary_on_headers("HX-Request")
def busca(request: HttpRequest, categoria: str, uf: str = "", cidade: str = "") -> HttpResponse:
    """Lista de anúncios da categoria com filtros, busca por texto, ordem e paginação de 24."""
    cidade_atual, form, filtros, opcoes = _ler_busca(request, categoria, uf, cidade)
    url_limpa = services.url(categoria, cidade_atual, filtros)
    htmx = request.headers.get("HX-Request") == "true"
    if not htmx and not _mesma_url(request, url_limpa):
        return HttpResponseRedirect(url_limpa)

    anuncios = services.buscar(categoria, cidade_atual, filtros)
    pagina = Paginator(anuncios, services.POR_PAGINA).get_page(filtros.get("pagina", 1))
    rotulos = services.rotulos(categoria, opcoes)
    titulo = services.titulo(categoria, cidade_atual, filtros, rotulos)
    estados = cidades_atendidas()
    resposta = render(
        request,
        "busca/resultados.html",
        {
            "tela": categoria,
            "ajuda_itens": textos_ajuda(f"busca_{categoria}"),
            "categoria": categoria,
            "cidade": cidade_atual,
            "form": form,
            "filtros": filtros,
            "pagina": pagina,
            "anuncios": [para_vitrine(a) for a in pagina.object_list],
            "titulo": titulo,
            "descricao": services.descricao(categoria, titulo, pagina.paginator.count),
            "url_canonica": request.build_absolute_uri(
                services.url_canonica(categoria, cidade_atual, filtros)
            ),
            "indexavel": services.indexavel(filtros),
            "chips": services.chips(categoria, cidade_atual, filtros, rotulos),
            "url_limpar": services.caminho(categoria, cidade_atual),
            "url_todas_cidades": services.url(categoria, None, filtros, sem={"pagina"}),
            "url_pagina": services.url(categoria, cidade_atual, filtros, sem={"pagina"}),
            "url_mapa": services.url_do_mapa(categoria, cidade_atual, filtros),
            "area": filtros.get("area", ""),
            "valor_cidade": f"{cidade_atual.uf_id.lower()}/{cidade_atual.slug}" if cidade_atual else "",
            "estados_atendidos": estados,
            "mostrar_estado": len(estados) > 1,
        },
    )
    if htmx:
        resposta["HX-Push-Url"] = url_limpa
    return resposta
