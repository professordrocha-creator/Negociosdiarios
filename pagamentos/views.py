"""Views do app pagamentos: Painel › Faturas, "Já paguei" e o comprovante (sempre a loja logada)."""

from pathlib import PurePath

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from anunciantes.views import anunciante_ativo
from core.services import configuracao, textos_ajuda
from pagamentos.forms import ComprovanteForm
from pagamentos.models import Fatura
from pagamentos.services import dados_pix, enviar_comprovante, faturas_da_loja, faturas_em_aberto
from planos.services import assinatura_de

TIPOS_COMPROVANTE = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def resposta_do_comprovante(fatura: Fatura) -> HttpResponse:
    """Entrega o comprovante (já conferida a permissão por quem chama).

    Arquivo privado: sem cache compartilhado, tipo fixo pela extensão gravada (nunca o que o navegador
    "adivinhar") e `sandbox` na CSP: um PDF aberto no navegador não roda script nem navega. Lido inteiro
    (no máximo `limite_comprovante_kb`): funciona igual na pasta local e no bucket, sem arquivo aberto.
    """
    if not fatura.comprovante:
        raise Http404("Fatura sem comprovante.")
    extensao = PurePath(fatura.comprovante.name).suffix.lower()
    with fatura.comprovante.open("rb") as arquivo:
        conteudo = arquivo.read()
    resposta = HttpResponse(
        conteudo, content_type=TIPOS_COMPROVANTE.get(extensao, "application/octet-stream")
    )
    resposta["Content-Disposition"] = f'inline; filename="comprovante-{fatura.codigo}{extensao}"'
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Content-Security-Policy"] = "sandbox"
    return resposta


def _fatura_da_loja(request: HttpRequest, codigo: str) -> Fatura:
    """Fatura pelo código, só da loja logada (outra loja: 404, sem revelar que existe)."""
    return get_object_or_404(faturas_da_loja(request.user.anunciante), codigo=codigo)


def _contexto(request: HttpRequest, form: ComprovanteForm, form_de: str = "") -> dict:
    """Faturas em aberto (as a pagar com o Pix), as aguardando confirmação e o histórico da loja logada."""
    anunciante = request.user.anunciante
    em_aberto = faturas_em_aberto(anunciante)
    return {
        "tela": "faturas",
        "ajuda_itens": textos_ajuda("faturas"),
        "anunciante": anunciante,
        "assinatura": assinatura_de(anunciante),
        "a_pagar": [
            {
                "fatura": fatura,
                "pix": dados_pix(fatura),
                # um formulário por fatura (ids únicos); o que voltou com erro mantém as mensagens
                "form": form
                if fatura.codigo == form_de
                else ComprovanteForm(auto_id=f"id_{fatura.codigo}_%s"),
            }
            for fatura in em_aberto
            if fatura.a_pagar
        ],
        "aguardando": [fatura for fatura in em_aberto if fatura.situacao == Fatura.Situacao.AGUARDANDO],
        "historico": faturas_da_loja(anunciante).exclude(situacao__in=Fatura.EM_ABERTO)[:24],
        "form_de": form_de,  # fatura cujo formulário "Já paguei" voltou com erro (fica aberto)
        "carencia_dias": configuracao().carencia_dias,
    }


@require_GET
@anunciante_ativo
def faturas(request: HttpRequest) -> HttpResponse:
    """Faturas em aberto (Pix copia e cola, QR Code, vencimento, "Já paguei") e o histórico."""
    return render(request, "pagamentos/faturas.html", _contexto(request, ComprovanteForm()))


@require_POST
@anunciante_ativo
def ja_paguei(request: HttpRequest, codigo: str) -> HttpResponse:
    """Recebe o comprovante; erro de arquivo volta para a tela com a mensagem no formulário da fatura."""
    fatura = _fatura_da_loja(request, codigo)
    form = ComprovanteForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            enviar_comprovante(fatura, form.cleaned_data["comprovante"], form.cleaned_data["recado"])
        except ValidationError as erro:
            form.add_error("comprovante", erro)
        except ValueError as erro:
            messages.warning(request, str(erro))
            return redirect("pagamentos:faturas")
        else:
            messages.success(request, "Comprovante enviado! A equipe confere e avisa por e-mail.")
            return redirect("pagamentos:faturas")
    return render(request, "pagamentos/faturas.html", _contexto(request, form, fatura.codigo), status=400)


@require_GET
@anunciante_ativo
def comprovante(request: HttpRequest, codigo: str) -> HttpResponse:
    """O comprovante que a própria loja enviou."""
    return resposta_do_comprovante(_fatura_da_loja(request, codigo))
