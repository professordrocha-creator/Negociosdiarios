"""Views do app moderacao: o formulário público de denúncia (sem login). A fila fica no admin."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from anuncios.services import anuncios_visiveis, url_publica
from core.services import textos_ajuda
from moderacao import services
from moderacao.forms import DenunciaForm


@require_http_methods(["GET", "POST"])
def denunciar(request: HttpRequest) -> HttpResponse:
    """Denúncia de anúncio: código (preenchido pelo botão do anúncio), motivo, detalhes e e-mail opcionais.

    Robô (campo-armadilha preenchido) recebe a mesma tela de sucesso, sem gravar nada. Limite por
    visitante por dia (sem IP). Depois de enviar, volta ao anúncio com o aviso.
    """
    inicial = {"anuncio": request.GET.get("anuncio", "")[:20]}
    form = DenunciaForm(request.POST or None, initial=inicial)
    anuncio = None
    if request.method == "POST" and form.is_valid():
        anuncio = anuncios_visiveis().filter(codigo=form.cleaned_data["anuncio"]).first()
        if form.cleaned_data["site_empresa"]:  # robô: finge que deu certo
            messages.success(request, "Denúncia recebida. Obrigado por ajudar a manter o site seguro.")
            return redirect("core:inicio")
        if anuncio is None:
            form.add_error(
                "anuncio", "Não achamos este anúncio no ar. Confira o código na página do anúncio."
            )
        else:
            try:
                services.denunciar(
                    anuncio,
                    form.cleaned_data["motivo"],
                    form.cleaned_data["texto"],
                    form.cleaned_data["email"],
                    services.origem_do_visitante(request),
                )
            except services.LimiteDeDenuncias as erro:
                form.add_error(None, str(erro))
            else:
                messages.success(request, "Denúncia recebida. A equipe vai analisar. Obrigado por ajudar.")
                return redirect(url_publica(anuncio))
    elif request.method == "GET" and inicial["anuncio"]:
        anuncio = anuncios_visiveis().filter(codigo=inicial["anuncio"].strip().upper()).first()
    resposta = render(
        request,
        "moderacao/denunciar.html",
        {"tela": "denunciar", "ajuda_itens": textos_ajuda("denunciar"), "form": form, "anuncio": anuncio},
        status=400 if request.method == "POST" else 200,
    )
    resposta["X-Robots-Tag"] = "noindex"
    return resposta


@require_http_methods(["GET"])
def como_denunciar(request: HttpRequest) -> HttpResponse:
    """Página do rodapé: a denúncia é feita pelo botão "Denunciar" de cada anúncio; o que acontece depois."""
    return render(
        request,
        "moderacao/como_denunciar.html",
        {"tela": "como_denunciar", "ajuda_itens": textos_ajuda("como_denunciar")},
    )
