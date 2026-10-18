"""Context processor do app guia: a entrada do guia no menu, na home e no rodapé (só com o guia no ar)."""

from django.http import HttpRequest


def guia(request: HttpRequest) -> dict:
    """`{{ guia_menu.no_ar }}` e `{{ guia_menu.nome }}` (ConfiguracaoGuia, lida com cache).

    Desligado, nada aparece para ninguém (a equipe pré-visualiza digitando /guia/). Sem banco (ex.: build
    sem migrations), o guia fica fora em vez de derrubar a página.
    """
    from django.db import DatabaseError

    from guia.services import configuracao_guia

    try:
        config = configuracao_guia()
    except DatabaseError:
        return {"guia_menu": {"no_ar": False, "nome": ""}}
    return {"guia_menu": {"no_ar": config.ativo, "nome": config.nome_guia}}
