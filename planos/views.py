"""Views do app planos: Painel › Meu plano (sempre a loja de quem está logado)."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from anunciantes.views import anunciante_ativo
from core.services import configuracao, textos_ajuda
from planos.forms import PedidoPlanoForm
from planos.models import PedidoTrocaPlano
from planos.services import (
    assinatura_de,
    escolher_anuncios_para_manter,
    pedir_troca,
    planos_a_venda,
    precisa_escolher_anuncios,
    uso_do_plano,
)


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def meu_plano(request: HttpRequest) -> HttpResponse:
    """Plano atual, uso, vencimento e pedido de troca (sem pagamento por enquanto)."""
    anunciante = request.user.anunciante
    planos = planos_a_venda()
    assinatura = assinatura_de(anunciante)
    form = PedidoPlanoForm(request.POST or None, planos=planos)
    if request.method == "POST" and form.is_valid():
        try:
            pedido = pedir_troca(anunciante, form.cleaned_data["plano"], form.cleaned_data["periodicidade"])
        except ValueError as erro:
            form.add_error(None, str(erro))
        else:
            if precisa_escolher_anuncios(pedido):
                messages.success(
                    request, "Pedido enviado! Agora escolha quais anúncios ficam no ar no plano novo."
                )
                return redirect("planos:escolher_anuncios")
            messages.success(request, "Pedido enviado! A equipe vai analisar e avisar por e-mail.")
            return redirect("planos:meu_plano")
    pendente = PedidoTrocaPlano.objects.filter(
        anunciante=anunciante, status=PedidoTrocaPlano.Status.PENDENTE
    ).first()
    return render(
        request,
        "planos/meu_plano.html",
        {
            "tela": "meu_plano",
            "ajuda_itens": textos_ajuda("meu_plano"),
            "anunciante": anunciante,
            "assinatura": assinatura,
            "uso": uso_do_plano(anunciante),
            "planos": planos,
            "form": form,
            "pendente": pendente,
            "escolha_pendente": bool(
                pendente and precisa_escolher_anuncios(pendente) and not pendente.anuncios_manter
            ),
            "carencia_dias": configuracao().carencia_dias,
        },
    )


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def escolher_anuncios(request: HttpRequest) -> HttpResponse:
    """Plano menor: o anunciante marca quais anúncios ficam no ar; o resto será pausado na aprovação.

    Só o pedido pendente da própria loja (sem id na URL: sem IDOR).
    """
    from anuncios.services import anuncios_do_dono, ids_no_plano

    anunciante = request.user.anunciante
    pedido = get_object_or_404(
        PedidoTrocaPlano.objects.select_related("plano_novo"),
        anunciante=anunciante,
        status=PedidoTrocaPlano.Status.PENDENTE,
    )
    if not precisa_escolher_anuncios(pedido):
        messages.info(request, "Seus anúncios cabem no plano pedido: não é preciso escolher.")
        return redirect("planos:meu_plano")
    erro = ""
    if request.method == "POST":
        try:
            escolher_anuncios_para_manter(
                pedido, [int(i) for i in request.POST.getlist("manter") if i.isdigit()]
            )
        except ValueError as falha:
            erro = str(falha)
        else:
            messages.success(request, "Escolha guardada. A equipe aplica junto com a troca de plano.")
            return redirect("planos:meu_plano")
    ids = ids_no_plano(anunciante)
    anuncios = sorted(anuncios_do_dono(anunciante).filter(pk__in=ids), key=lambda a: ids.index(a.pk))
    return render(
        request,
        "planos/escolher_anuncios.html",
        {
            "tela": "escolher_anuncios",
            "ajuda_itens": textos_ajuda("escolher_anuncios"),
            "anunciante": anunciante,
            "pedido": pedido,
            "anuncios": anuncios,
            "marcados": set(pedido.anuncios_manter)
            if request.method == "GET"
            else {int(i) for i in request.POST.getlist("manter") if i.isdigit()},
            "erro": erro,
        },
    )
