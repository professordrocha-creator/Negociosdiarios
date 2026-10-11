"""Views do app anunciantes: painel do anunciante (/painel/).

Toda view do painel usa `anunciante_ativo`: o anunciante vem SEMPRE de
`request.user.anunciante`, nunca de um id na URL (sem IDOR; docs/SEGURANCA.md).
"""

from collections.abc import Callable
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from anunciantes.services import MENSAGENS_SEM_ACESSO, anuncios_da_loja, motivo_sem_painel, plano_de_exemplo
from core.services import textos_ajuda


def anunciante_ativo(view: Callable) -> Callable:
    """Só deixa passar anunciante ativo. Anônimo vai ao /entrar/; equipe, pendente e suspenso veem 403.

    Equipe recebe 403 (e não o login) porque já está logada: o painel dela é o admin.
    """

    @wraps(view)
    def _view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        motivo = motivo_sem_painel(request.user)
        if motivo == "anonimo":
            return redirect_to_login(request.get_full_path())
        if motivo:
            contexto = {"tela": "painel", "mensagem": MENSAGENS_SEM_ACESSO[motivo], "motivo": motivo}
            return render(request, "anunciantes/sem_acesso.html", contexto, status=403)
        return view(request, *args, **kwargs)

    return _view


@require_GET
@anunciante_ativo
def painel(request: HttpRequest) -> HttpResponse:
    """Painel: dados da loja, resumo do plano (exemplo, "em breve") e meus anúncios."""
    anunciante = request.user.anunciante
    anuncios = anuncios_da_loja(anunciante)
    plano = plano_de_exemplo()
    return render(
        request,
        "anunciantes/painel.html",
        {
            "tela": "painel",
            "ajuda_itens": textos_ajuda("painel"),
            "anunciante": anunciante,
            "anuncios": anuncios,
            "plano": plano,
            "uso_plano": min(len(anuncios), plano.limite_anuncios),
        },
    )
