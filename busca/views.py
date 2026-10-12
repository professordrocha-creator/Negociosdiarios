"""Views da busca: /imoveis/, /veiculos/ e as versões por cidade (/imoveis/mt/tangara-da-serra/).

Funciona sem JavaScript (formulário GET; a URL "suja" do formulário é redirecionada para a limpa) e
com HTMX (o formulário pede a mesma página; o HTMX troca só a lista e os campos dependentes e a
barra de endereço recebe a URL limpa pelo cabeçalho HX-Push-Url). Regras em busca.services.
"""

from urllib.parse import parse_qsl

from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_headers

from anuncios.services import para_vitrine
from busca import services
from busca.forms import FORMULARIOS
from core.services import cidades_atendidas, textos_ajuda


def _mesma_url(request: HttpRequest, url_limpa: str) -> bool:
    """A requisição já está na URL limpa? Compara caminho e parâmetros decodificados (não o texto)."""
    caminho, _, parametros = url_limpa.partition("?")
    return request.path == caminho and parse_qsl(request.META.get("QUERY_STRING", "")) == parse_qsl(
        parametros
    )


@require_GET
@vary_on_headers("HX-Request")
def busca(request: HttpRequest, categoria: str, uf: str = "", cidade: str = "") -> HttpResponse:
    """Lista de anúncios da categoria com filtros, busca por texto, ordem e paginação de 24."""
    cidade_url = services.cidade_da_url(uf, cidade) if uf else None
    if uf and cidade_url is None:
        raise Http404("Cidade não atendida.")
    dados = request.GET.copy()
    escolha = dados.pop("cidade", None)  # seletor de cidade do formulário: vira o caminho da URL
    cidade_atual = services.cidade_escolhida(escolha[-1]) if escolha is not None else cidade_url

    marca = dados.get("marca", "")
    opcoes = services.opcoes(categoria, cidade_atual, marca)
    form = FORMULARIOS[categoria](dados, opcoes=opcoes)
    filtros = form.filtros()
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
            "valor_cidade": f"{cidade_atual.uf_id.lower()}/{cidade_atual.slug}" if cidade_atual else "",
            "estados_atendidos": estados,
            "mostrar_estado": len(estados) > 1,
        },
    )
    if htmx:
        resposta["HX-Push-Url"] = url_limpa
    return resposta
