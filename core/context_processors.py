"""Context processors do app core: dados disponíveis em todos os templates."""

from django.conf import settings
from django.http import HttpRequest

from core.services import dados_do_site, mostrar_link_admin


def site(request: HttpRequest) -> dict:
    """Expõe a identidade do site (`{{ site.nome }}`, `{{ site.simbolo_escuro }}`...) e `mostrar_link_admin`.

    Lê do modelo `Configuracao` (registro único editado no admin, em cache e limpo ao
    salvar). Os valores `SITE_*` do settings são só o ponto de partida do registro.
    """
    return {
        "site": dados_do_site(),
        # Atalho do admin no rodapé: só em dev ou para a equipe logada (core.services).
        "mostrar_link_admin": mostrar_link_admin(getattr(request, "user", None), settings.DEBUG),
    }
