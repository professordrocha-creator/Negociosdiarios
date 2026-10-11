"""Views do app planos: Painel › Meu plano (sempre a loja de quem está logado)."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from anunciantes.views import anunciante_ativo
from core.services import configuracao, textos_ajuda
from planos.forms import PedidoPlanoForm
from planos.models import PedidoTrocaPlano
from planos.services import assinatura_de, pedir_troca, planos_a_venda, uso_do_plano


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
            pedir_troca(anunciante, form.cleaned_data["plano"], form.cleaned_data["periodicidade"])
        except ValueError as erro:
            form.add_error(None, str(erro))
        else:
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
            "carencia_dias": configuracao().carencia_dias,
        },
    )
