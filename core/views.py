"""Views do app core."""

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.services import banco_disponivel


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
