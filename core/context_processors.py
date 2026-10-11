"""Context processors do app core: dados disponíveis em todos os templates."""

from django.conf import settings
from django.http import HttpRequest


def site(request: HttpRequest) -> dict:
    """Expõe a identidade do site como `{{ site.nome }}`, `{{ site.slogan }}` etc.

    Provisório: lê do settings. Na Sprint 1 passa a ler do modelo `Configuracao`
    (registro único editável no admin, guardado em cache e limpo ao salvar),
    sem mudar os nomes usados nos templates.
    """
    return {
        "site": {
            "nome": settings.SITE_NOME,
            "slogan": settings.SITE_SLOGAN,
            "linha_regiao": settings.SITE_LINHA_REGIAO,
            "email_contato": settings.SITE_EMAIL_CONTATO,
            "email_privacidade": settings.SITE_EMAIL_PRIVACIDADE,
            "empresa": settings.SITE_EMPRESA,
            "cidade_sede": settings.SITE_CIDADE_SEDE,
        }
    }
