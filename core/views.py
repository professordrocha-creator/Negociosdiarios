"""Views do app core: home, páginas institucionais, "em breve" e verificação de saúde."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.services import (
    PAGINAS_EM_BREVE,
    banco_disponivel,
    cidades_atendidas,
    destaques,
    formatos_publicidade,
    lojas_verificadas,
    planos,
    recem_anunciados,
    textos_ajuda,
)


@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    """Home: busca (visual, ainda sem buscar), destaques, recém-anunciados, lojas e cidades atendidas.

    Os anúncios e as lojas vêm de core.services (hoje do demo.json com MOSTRAR_DEMO; da
    Sprint 3 em diante, do banco, sem mudar esta view). Sem dados, a página mostra "em breve".
    """
    estados = cidades_atendidas()
    return render(
        request,
        "core/inicio.html",
        {
            "tela": "inicio",
            "estados_atendidos": estados,
            "mostrar_estado": len(estados) > 1,  # 1 estado: seletor e nome do estado ficam ocultos (ARQ. §9)
            "destaques": destaques(),
            "recem_anunciados": recem_anunciados(),
            "lojas_verificadas": lojas_verificadas(),
            "mostrar_demo": settings.MOSTRAR_DEMO,
        },
    )


@require_GET
def sobre(request: HttpRequest) -> HttpResponse:
    """Página Sobre: quem somos, missão, visão e valores.

    Provisório: textos fixos no template. Na Sprint 1 vêm de `PaginaInstitucional`
    e `ValorEmpresa`, editáveis no admin.
    """
    return render(request, "core/sobre.html", {"tela": "sobre"})


def _pagina(request: HttpRequest, template: str, tela: str, **contexto) -> HttpResponse:
    """Renderiza uma página institucional com a caixa "Sobre esta tela" da tela, se houver texto."""
    return render(request, template, {"tela": tela, "ajuda_itens": textos_ajuda(tela), **contexto})


@require_GET
def privacidade(request: HttpRequest) -> HttpResponse:
    """Política de Privacidade (rascunho até a revisão do advogado; baseada em docs/LGPD.md)."""
    return _pagina(request, "core/privacidade.html", "privacidade")


@require_GET
def termos(request: HttpRequest) -> HttpResponse:
    """Termos de Uso (rascunho até a revisão do advogado)."""
    return _pagina(request, "core/termos.html", "termos")


@require_GET
def cookies(request: HttpRequest) -> HttpResponse:
    """Política de Cookies: hoje o site só usa cookies essenciais (rascunho até a revisão)."""
    return _pagina(request, "core/cookies.html", "cookies")


@require_GET
def planos_view(request: HttpRequest) -> HttpResponse:
    """Planos de assinatura com alternância mensal/anual (valores do settings até a Sprint 2)."""
    return _pagina(request, "core/planos.html", "planos", planos=planos())


@require_GET
def anuncie(request: HttpRequest) -> HttpResponse:
    """Mídia kit: espaços de publicidade, tamanhos, posições e preços (docs/PUBLICIDADE.md)."""
    return _pagina(request, "core/anuncie.html", "anuncie", formatos=formatos_publicidade())


@require_GET
def contato(request: HttpRequest) -> HttpResponse:
    """Contato: WhatsApp, e-mails e endereço do site (sem formulário por enquanto)."""
    return _pagina(request, "core/contato.html", "contato")


@require_GET
def em_breve(request: HttpRequest, pagina: str) -> HttpResponse:
    """Página "Em breve" para links que já existem no menu e no rodapé (nunca 404)."""
    return _pagina(request, "core/em_breve.html", "em_breve", pagina=PAGINAS_EM_BREVE[pagina])


@require_GET
def favicon(request: HttpRequest) -> HttpResponsePermanentRedirect:
    """Redireciona /favicon.ico para o arquivo estático.

    Navegadores e robôs pedem /favicon.ico na raiz mesmo sem `<link rel="icon">`.
    O endereço é calculado na requisição (e não na importação das URLs) para
    funcionar também com arquivos estáticos versionados em produção.
    """
    return HttpResponsePermanentRedirect(static("img/favicon.ico"))


@never_cache
@require_GET
def saude(request: HttpRequest) -> JsonResponse:
    """Responde se a aplicação e o banco estão de pé.

    Usado pelo healthcheck do Docker e pelo monitor de uptime externo.
    Devolve 200 se tudo ok e 503 se o banco não responde, para o monitor
    disparar alerta. Não expõe detalhes do erro (versões, hosts, mensagens).
    """
    if banco_disponivel():
        return JsonResponse({"status": "ok"})
    return JsonResponse({"status": "erro", "banco": "indisponivel"}, status=503)
