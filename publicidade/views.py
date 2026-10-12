"""Views do app publicidade: o clique na peça (conta e redireciona). O resto é admin."""

from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from publicidade import services
from publicidade.models import Banner


@require_GET
def clique(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """Conta o clique do dia (sem IP, sem cookie, sem robôs) e leva ao site do patrocinador.

    Só http/https: um link estranho (javascript:, data:...) dá 404 em vez de redirecionar. Peça fora do ar
    ainda leva ao site (o link pode estar salvo), mas não conta.
    """
    banner = get_object_or_404(Banner.objects.select_related("campanha"), pk=pk)
    destino = services.link_seguro(banner)
    if destino is None:
        raise Http404("Link inválido.")
    if banner.ativo and banner.campanha.no_ar():
        services.registrar(banner, services.CLIQUES, request)
    resposta = HttpResponseRedirect(destino)
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    resposta["Cache-Control"] = "no-store"
    resposta["Referrer-Policy"] = "origin"  # o patrocinador vê que veio do site, não de qual página
    return resposta
