"""Views do app core: home, página Sobre e verificação de saúde."""

from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.services import banco_disponivel, cidades_atendidas


@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    """Home provisória: busca visual (ainda sem buscar) e cidades atendidas.

    Destaques e Recém-anunciados aparecem como "em breve" até existirem anúncios (Sprint 3).
    """
    estados = cidades_atendidas()
    return render(
        request,
        "core/inicio.html",
        {
            "tela": "inicio",
            "estados_atendidos": estados,
            "mostrar_estado": len(estados) > 1,  # 1 estado: seletor e nome do estado ficam ocultos (ARQ. §9)
        },
    )


@require_GET
def sobre(request: HttpRequest) -> HttpResponse:
    """Página Sobre: quem somos, missão, visão e valores.

    Provisório: textos fixos no template. Na Sprint 1 vêm de `PaginaInstitucional`
    e `ValorEmpresa`, editáveis no admin.
    """
    return render(request, "core/sobre.html", {"tela": "sobre"})


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
