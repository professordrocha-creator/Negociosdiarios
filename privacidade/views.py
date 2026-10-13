"""Views do app privacidade: Termos e Política (versão em vigor), aceite da versão nova e "Meus dados"
(baixar os dados e excluir a conta). Regras em privacidade.services."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from anunciantes.views import anunciante_ativo
from core.services import configuracao, limite_por_ip_excedido, textos_ajuda
from privacidade import services
from privacidade.forms import AceiteForm, ExcluirContaForm, SenhaForm
from privacidade.models import DocumentoLegal

# Tentativas de senha por hora em "Meus dados" (por IP), contra adivinhação numa sessão roubada.
TENTATIVAS_POR_HORA = 10


def documento(request: HttpRequest, tipo: str) -> HttpResponse:
    """Termos ou Política na versão em vigor (a Política traz o Encarregado e a seção Cookies)."""
    doc = services.documento_vigente(tipo)
    if doc is None:
        raise Http404("Documento ainda não publicado.")
    return render(
        request,
        "privacidade/documento.html",
        {
            "tela": tipo,
            "ajuda_itens": textos_ajuda(tipo),
            "documento": doc,
            "blocos": services.blocos_do_texto(doc.texto),
            "privacidade": tipo == DocumentoLegal.Tipo.PRIVACIDADE,
            "cookies": services.COOKIES,
            "config": configuracao(),
        },
    )


def _destino_seguro(request: HttpRequest, padrao: str) -> str:
    """O `next` só se for deste site (sem redirecionamento aberto)."""
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return padrao


@login_required
@require_http_methods(["GET", "POST"])
def aceitar(request: HttpRequest) -> HttpResponse:
    """Versão nova dos Termos/Política: mostra o que mudou e pede o aceite (ou sai)."""
    destino = _destino_seguro(request, reverse("anunciantes:painel"))
    pendentes = services.pendencias_de_aceite(request.user)
    if not pendentes:
        return redirect(destino)
    form = AceiteForm(request.POST if "aceitar" in request.POST else None)
    if request.method == "POST" and "recusar" in request.POST:
        logout(request)
        messages.info(
            request,
            "Sem aceitar as versões atualizadas não dá para usar o painel. Dúvidas: fale com a gente.",
        )
        return redirect("core:inicio")
    if form.is_valid():
        services.registrar_aceites(request.user, pendentes)
        messages.success(request, "Obrigado! Versões atualizadas aceitas.")
        return redirect(destino)
    return render(
        request,
        "privacidade/aceitar.html",
        {
            "tela": "aceitar_termos",
            "ajuda_itens": textos_ajuda("aceitar_termos"),
            "pendentes": pendentes,
            "form": form,
            "next": destino,
        },
    )


def _contexto_meus_dados(request: HttpRequest, form_baixar: SenhaForm | None = None) -> dict:
    """Resumo do que guardamos, aceites, pedidos e o formulário de baixar."""
    usuario = request.user
    return {
        "tela": "meus_dados",
        "ajuda_itens": textos_ajuda("meus_dados"),
        "anunciante": usuario.anunciante,
        "aceites": usuario.aceites.order_by("-aceito_em"),
        "pedidos": usuario.pedidos_titular.order_by("-recebido_em")[:10],
        "form_baixar": form_baixar or SenhaForm(usuario=usuario),
        "config": configuracao(),
    }


@require_GET
@anunciante_ativo(exigir_aceite=False)
def meus_dados(request: HttpRequest) -> HttpResponse:
    """Painel › Meus dados: o que guardamos, baixar uma cópia e excluir a conta (vale sem o aceite novo)."""
    return render(request, "privacidade/meus_dados.html", _contexto_meus_dados(request))


@require_POST
@anunciante_ativo(exigir_aceite=False)
def baixar(request: HttpRequest) -> HttpResponse:
    """Confere a senha de novo e entrega o JSON com todos os dados (anexo, sem cache)."""
    form = SenhaForm(request.POST, usuario=request.user)
    if limite_por_ip_excedido(request, "meus_dados_senha", limite=TENTATIVAS_POR_HORA, janela_segundos=3600):
        form.add_error(None, "Muitas tentativas na última hora. Aguarde e tente de novo.")
        return render(request, "privacidade/meus_dados.html", _contexto_meus_dados(request, form), status=429)
    if not form.is_valid():
        return render(request, "privacidade/meus_dados.html", _contexto_meus_dados(request, form), status=400)
    resposta = HttpResponse(
        services.exportar_json(request.user), content_type="application/json; charset=utf-8"
    )
    resposta["Content-Disposition"] = (
        f'attachment; filename="meus-dados-{timezone.localdate():%Y-%m-%d}.json"'
    )
    resposta["Cache-Control"] = "private, no-store"
    return resposta


@require_http_methods(["GET", "POST"])
@anunciante_ativo(exigir_aceite=False)
def excluir(request: HttpRequest) -> HttpResponse:
    """Excluir minha conta: avisa o que acontece (e fatura em aberto), pede senha e a palavra EXCLUIR."""
    form = ExcluirContaForm(request.POST or None, usuario=request.user)
    bloqueado = request.method == "POST" and limite_por_ip_excedido(
        request, "meus_dados_senha", limite=TENTATIVAS_POR_HORA, janela_segundos=3600
    )
    if bloqueado:
        form.add_error(None, "Muitas tentativas na última hora. Aguarde e tente de novo.")
    elif request.method == "POST" and form.is_valid():
        services.anonimizar_conta(request.user)
        logout(request)
        messages.success(
            request, "Sua conta foi excluída. Enviamos a confirmação para o e-mail que você usava."
        )
        return redirect("core:inicio")
    return render(
        request,
        "privacidade/excluir.html",
        {
            "tela": "excluir_conta",
            "ajuda_itens": textos_ajuda("excluir_conta"),
            "anunciante": request.user.anunciante,
            "form": form,
            "faturas_em_aberto": services.faturas_em_aberto(request.user),
            "config": configuracao(),
        },
        status=429 if bloqueado else (400 if request.method == "POST" else 200),
    )
