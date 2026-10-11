"""Views do painel de anúncios: novo/editar em etapas (dados, localização, fotos, revisão) e ações.

Todas usam `anunciante_ativo` e buscam o anúncio por `anuncios_do_dono(request.user.anunciante)`:
o código na URL de outra loja dá 404 (sem IDOR). Regras ficam em anuncios.services.
"""

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from anunciantes.views import anunciante_ativo
from anuncios import services
from anuncios.forms import DadosImovelForm, FotosForm, LocalizacaoForm
from anuncios.models import Anuncio
from anuncios.tasks import processar_foto
from core.services import configuracao, textos_ajuda
from planos.services import LimiteDoPlano, SemAssinaturaAtiva, assinatura_de, pode_publicar

ETAPAS = [
    ("editar", "Dados"),
    ("localizacao", "Localização"),
    ("fotos", "Fotos"),
    ("revisao", "Revisão"),
]


def _anuncio(request: HttpRequest, codigo: str) -> Anuncio:
    """O anúncio do dono logado (404 para código de outra loja ou excluído)."""
    return get_object_or_404(services.anuncios_do_dono(request.user.anunciante), codigo=codigo)


def _editavel(anuncio: Anuncio) -> None:
    """Anúncio expirado continua editável; em análise não (espera a decisão da equipe)."""
    if anuncio.situacao == Anuncio.Situacao.EM_MODERACAO:
        raise Http404("Anúncio em análise.")


def _contexto(request: HttpRequest, etapa: str, anuncio: Anuncio | None, **extra) -> dict:
    """Contexto comum das etapas (menu, ajuda, barra de etapas)."""
    return {
        "tela": f"anuncio_{etapa}",
        "ajuda_itens": textos_ajuda(f"anuncio_{etapa}"),
        "anunciante": request.user.anunciante,
        "anuncio": anuncio,
        "etapas": ETAPAS,
        "etapa": etapa,
        **extra,
    }


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def novo(request: HttpRequest) -> HttpResponse:
    """Etapa 1 de um anúncio novo: ao salvar vira rascunho e segue para a localização."""
    anunciante = request.user.anunciante
    form = DadosImovelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        anuncio = services.criar_anuncio_imovel(anunciante, form.dados_anuncio(), form.dados_ficha())
        messages.success(request, f"Rascunho {anuncio.codigo} criado. Agora marque a localização.")
        return redirect("anuncios:localizacao", anuncio.codigo)
    no_limite = not pode_publicar(anunciante, uso=services.contar_no_plano(anunciante))
    return render(
        request, "anuncios/dados.html", _contexto(request, "editar", None, form=form, no_limite=no_limite)
    )


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def editar(request: HttpRequest, codigo: str) -> HttpResponse:
    """Etapa 1 — dados do imóvel."""
    anuncio = _anuncio(request, codigo)
    _editavel(anuncio)
    form = DadosImovelForm(request.POST or None, initial=DadosImovelForm.inicial(anuncio))
    if request.method == "POST" and form.is_valid():
        services.atualizar_anuncio(anuncio, form.dados_anuncio(), form.dados_ficha())
        messages.success(request, "Dados salvos.")
        return redirect("anuncios:localizacao", anuncio.codigo)
    return render(request, "anuncios/dados.html", _contexto(request, "editar", anuncio, form=form))


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def localizacao(request: HttpRequest, codigo: str) -> HttpResponse:
    """Etapa 2 — cidade, bairro, endereço privado e ponto no mapa (Leaflet servido pelo site)."""
    anuncio = _anuncio(request, codigo)
    _editavel(anuncio)
    form = LocalizacaoForm(request.POST or None, initial=LocalizacaoForm.inicial(anuncio))
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        services.atualizar_anuncio(
            anuncio,
            {"cidade": dados["cidade"], "bairro": dados["bairro"]},
            {
                "endereco": dados["endereco"],
                "ponto": services.ponto(dados["latitude"], dados["longitude"]),
                "exibir_localizacao": dados["exibir_localizacao"],
            },
            motivo="Localização editada pelo anunciante.",
        )
        messages.success(request, "Localização salva.")
        return redirect("anuncios:fotos", anuncio.codigo)
    cidades = {c.pk: [c.ponto.y, c.ponto.x] for c in form.fields["cidade"].queryset if c.ponto}
    return render(
        request,
        "anuncios/localizacao.html",
        _contexto(request, "localizacao", anuncio, form=form, centros=cidades),
    )


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def fotos(request: HttpRequest, codigo: str) -> HttpResponse:
    """Etapa 3 — envio de várias fotos, ordem (arrastar ou setas) e exclusão."""
    anuncio = _anuncio(request, codigo)
    _editavel(anuncio)
    vagas = services.vagas_de_foto(anuncio)
    form = FotosForm(request.POST or None, request.FILES or None, vagas=vagas)
    if request.method == "POST" and form.is_valid():
        try:
            novas = services.adicionar_fotos(anuncio, form.cleaned_data["fotos"])
        except ValueError as erro:
            form.add_error("fotos", str(erro))
        else:
            for foto in novas:
                processar_foto.delay(foto.pk)
            messages.success(
                request, f"{len(novas)} foto(s) enviada(s). Estamos otimizando: recarregue em instantes."
            )
            return redirect("anuncios:fotos", anuncio.codigo)
    lista = list(anuncio.fotos.order_by("ordem", "pk"))
    return render(
        request,
        "anuncios/fotos.html",
        _contexto(
            request,
            "fotos",
            anuncio,
            form=form,
            fotos=lista,
            vagas=vagas,
            processando=any(f.processando for f in lista),
        ),
    )


@require_POST
@anunciante_ativo
def ordenar_fotos(request: HttpRequest, codigo: str) -> HttpResponse:
    """Nova ordem do arrastar (lista de ids) ou setas (uma foto sobe/desce)."""
    anuncio = _anuncio(request, codigo)
    _editavel(anuncio)
    try:
        if "mover" in request.POST:
            foto_id, passo = request.POST["mover"].split(":")
            services.mover_foto(anuncio, int(foto_id), -1 if passo == "subir" else 1)
        else:
            services.reordenar_fotos(anuncio, [int(i) for i in request.POST.getlist("ordem")])
    except (ValueError, KeyError) as erro:
        messages.error(request, str(erro) or "Não foi possível mudar a ordem.")
    else:
        messages.success(request, "Ordem das fotos salva. A primeira é a capa.")
    return redirect("anuncios:fotos", anuncio.codigo)


@require_POST
@anunciante_ativo
def excluir_foto(request: HttpRequest, codigo: str, foto_id: int) -> HttpResponse:
    """Apaga uma foto do anúncio."""
    anuncio = _anuncio(request, codigo)
    _editavel(anuncio)
    try:
        services.excluir_foto(anuncio, foto_id)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Foto excluída.")
    return redirect("anuncios:fotos", anuncio.codigo)


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def revisao(request: HttpRequest, codigo: str) -> HttpResponse:
    """Etapa 4 — confere tudo e escolhe: continuar como rascunho ou enviar para publicação."""
    anuncio = _anuncio(request, codigo)
    anunciante = request.user.anunciante
    if request.method == "POST":
        if request.POST.get("acao") != "enviar":
            messages.success(request, f"{anuncio.codigo} guardado como rascunho.")
            return redirect("anunciantes:painel")
        try:
            situacao = services.enviar_para_publicacao(anuncio)
        except (services.AnuncioIncompleto, SemAssinaturaAtiva, LimiteDoPlano, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect("anuncios:revisao", anuncio.codigo)
        if situacao == Anuncio.Situacao.EM_MODERACAO:
            messages.success(request, "Enviado! A equipe confere o anúncio e avisa por e-mail.")
        else:
            messages.success(request, "Publicado! Seu anúncio já está no ar.")
        return redirect("anunciantes:painel")
    uso = services.contar_no_plano(anunciante)
    return render(
        request,
        "anuncios/revisao.html",
        _contexto(
            request,
            "revisao",
            anuncio,
            pendencias=services.pendencias(anuncio) if anuncio.situacao == Anuncio.Situacao.RASCUNHO else [],
            pode_publicar=pode_publicar(anunciante, uso=uso),
            assinatura=assinatura_de(anunciante),
            uso=uso,
            vai_para_moderacao=services.precisa_moderacao(anunciante),
            fotos=list(anuncio.fotos.order_by("ordem", "pk")),
        ),
    )


ACOES = {
    "pausar": (services.pausar, "Anúncio pausado. Ele não conta mais no limite do plano."),
    "reativar": (services.reativar, "Anúncio de volta ao ar."),
    "renovar": (services.renovar, "Anúncio renovado por mais {dias} dias."),
    "excluir": (services.excluir, "Anúncio excluído."),
}


@require_POST
@anunciante_ativo
def acao(request: HttpRequest, codigo: str, nome: str) -> HttpResponse:
    """Botões da lista "Meus anúncios": pausar, reativar, renovar e excluir (sempre POST)."""
    if nome not in ACOES:
        raise Http404
    anuncio = _anuncio(request, codigo)
    servico, sucesso = ACOES[nome]
    try:
        servico(anuncio)
    except (ValueError, LimiteDoPlano, SemAssinaturaAtiva) as erro:
        messages.error(request, f"{anuncio.codigo}: {erro}")
    else:
        messages.success(request, f"{anuncio.codigo}: {sucesso.format(dias=configuracao().expiracao_dias)}")
    return redirect("anunciantes:painel")
