"""Context processors do app core: dados disponíveis em todos os templates."""

from django.conf import settings
from django.http import HttpRequest

from core.services import mostrar_link_admin


def site(request: HttpRequest) -> dict:
    """Expõe a identidade do site (`{{ site.nome }}`, `{{ site.slogan }}` etc.) e `mostrar_link_admin`.

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
            "whatsapp": settings.SITE_WHATSAPP,  # E.164; vazio = "em breve"
            "endereco": settings.SITE_ENDERECO,
            "cnpj": settings.SITE_CNPJ,
        },
        # Atalho do admin no rodapé: só em dev ou para a equipe logada (core.services).
        "mostrar_link_admin": mostrar_link_admin(getattr(request, "user", None), settings.DEBUG),
    }
