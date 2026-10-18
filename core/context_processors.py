"""Context processors do app core: dados disponíveis em todos os templates."""

from django.http import HttpRequest

from core.services import dados_do_site


def site(request: HttpRequest) -> dict:
    """Expõe a identidade do site (`{{ site.nome }}`, `{{ site.simbolo_escuro }}`...).

    Lê do modelo `Configuracao` (registro único editado no admin, em cache e limpo ao
    salvar). Os valores `SITE_*` do settings são só o ponto de partida do registro.
    """
    return {"site": dados_do_site()}
