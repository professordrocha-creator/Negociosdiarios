"""Views do app anunciantes: cadastro público, confirmação de e-mail e painel (/painel/).

Toda view do painel usa `anunciante_ativo`: o anunciante vem SEMPRE de
`request.user.anunciante`, nunca de um id na URL (sem IDOR; docs/SEGURANCA.md).
"""

from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from anunciantes.forms import CadastroForm
from anunciantes.services import (
    MENSAGENS_SEM_ACESSO,
    DadosCadastro,
    anuncios_da_loja,
    cadastrar_anunciante,
    confirmar_email,
    motivo_sem_painel,
    plano_de_exemplo,
    reenviar_confirmacao,
)
from core.services import limite_por_ip_excedido, textos_ajuda


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


# --- Cadastro público e confirmação de e-mail --------------------------------------------


def _muitas_tentativas(request: HttpRequest) -> HttpResponse:
    """Resposta 429 quando o limite por IP estoura (cadastro, reenvio de e-mail)."""
    return render(request, "anunciantes/muitas_tentativas.html", {"tela": "cadastro"}, status=429)


@require_http_methods(["GET", "POST"])
def cadastro(request: HttpRequest) -> HttpResponse:
    """Cadastro de anunciante: valida, cria a loja pendente e manda o e-mail de confirmação.

    Robô que preenche o campo-armadilha vê a mesma tela de sucesso, mas nada é criado
    (não ensinamos ao robô o que o denunciou). Cada envio conta no limite por IP.
    """
    if request.user.is_authenticated and not request.user.is_staff:
        return redirect("anunciantes:painel")
    if request.method == "POST":
        if limite_por_ip_excedido(request, "cadastro", settings.LIMITE_CADASTROS_POR_HORA):
            return _muitas_tentativas(request)
        form = CadastroForm(request.POST)
        if form.e_robo:
            return redirect("anunciantes:cadastro_obrigado")
        if form.is_valid():
            dados = form.cleaned_data
            cadastrar_anunciante(
                DadosCadastro(
                    nome=dados["nome"],
                    email=dados["email"],
                    senha=dados["senha"],
                    tipo=dados["tipo"],
                    nome_publico=dados["nome_publico"],
                    documento_tipo=dados["documento_tipo"],
                    documento_numero=dados["documento_numero"],
                    whatsapp=dados["whatsapp"],
                    cidade=dados["cidade"],
                )
            )
            return redirect("anunciantes:cadastro_obrigado")
    else:
        form = CadastroForm()
    return render(
        request,
        "anunciantes/cadastro.html",
        {"tela": "cadastro", "ajuda_itens": textos_ajuda("cadastro"), "form": form},
    )


@require_GET
def cadastro_obrigado(request: HttpRequest) -> HttpResponse:
    """Próximos passos depois do cadastro: confirmar o e-mail e aguardar a análise."""
    return render(
        request,
        "anunciantes/cadastro_obrigado.html",
        {"tela": "cadastro_obrigado", "horas": settings.CONFIRMACAO_EMAIL_HORAS},
    )


@require_GET
def confirmar_email_view(request: HttpRequest, token: str) -> HttpResponse:
    """Clique no link do e-mail: confirma (uma vez só) ou explica por que não deu."""
    resultado = confirmar_email(token)
    status = 200 if resultado.situacao in ("confirmado", "ja_confirmado") else 400
    return render(
        request,
        "anunciantes/confirmacao.html",
        {"tela": "confirmacao", "situacao": resultado.situacao, "horas": settings.CONFIRMACAO_EMAIL_HORAS},
        status=status,
    )


@require_http_methods(["POST"])
def reenviar_confirmacao_view(request: HttpRequest) -> HttpResponse:
    """Pede um link de confirmação novo. Resposta sempre igual (não revela se o e-mail existe)."""
    if limite_por_ip_excedido(request, "pedido_email", settings.LIMITE_PEDIDOS_EMAIL_POR_HORA):
        return _muitas_tentativas(request)
    reenviar_confirmacao(request.POST.get("email", ""))
    return render(request, "anunciantes/confirmacao.html", {"tela": "confirmacao", "situacao": "reenviado"})
