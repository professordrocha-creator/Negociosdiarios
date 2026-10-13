"""Views do app anunciantes: cadastro, confirmação de e-mail, painel e vitrine pública das lojas.

Toda view do painel usa `anunciante_ativo`: o anunciante vem SEMPRE de
`request.user.anunciante`, nunca de um id na URL (sem IDOR; docs/SEGURANCA.md).
"""

from collections.abc import Callable
from functools import wraps
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from anunciantes.forms import CadastroForm, PaginaLojaForm
from anunciantes.models import Anunciante
from anunciantes.services import (
    MENSAGENS_SEM_ACESSO,
    DadosCadastro,
    anuncios_da_loja,
    cadastrar_anunciante,
    cidades_com_lojas,
    confirmar_email,
    listar_lojas,
    localizacao_da_loja,
    loja_para_vitrine,
    lojas_visiveis,
    motivo_sem_painel,
    reenviar_confirmacao,
)
from anunciantes.tasks import processar_imagem_loja as processar_imagem_loja_tarefa
from anuncios.services import ponto
from core.services import configuracao, limite_por_ip_excedido, textos_ajuda


def anunciante_ativo(view: Callable | None = None, *, exigir_aceite: bool = True) -> Callable:
    """Só deixa passar anunciante ativo. Anônimo vai ao /entrar/; equipe, pendente e suspenso veem 403.

    Equipe recebe 403 (e não o login) porque já está logada: o painel dela é o admin. Com versão nova dos
    Termos/Política ainda não aceita, vai para o aceite (Sprint 7B), menos nas telas de "Meus dados"
    (`exigir_aceite=False`): baixar os dados e excluir a conta valem sem aceitar nada.
    Uso: `@anunciante_ativo` ou `@anunciante_ativo(exigir_aceite=False)`.
    """
    if view is None:
        return lambda v: anunciante_ativo(v, exigir_aceite=exigir_aceite)

    @wraps(view)
    def _view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        motivo = motivo_sem_painel(request.user)
        if motivo == "anonimo":
            return redirect_to_login(request.get_full_path())
        if motivo:
            contexto = {"tela": "painel", "mensagem": MENSAGENS_SEM_ACESSO[motivo], "motivo": motivo}
            return render(request, "anunciantes/sem_acesso.html", contexto, status=403)
        if exigir_aceite:
            from privacidade.services import pendencias_de_aceite  # import local: privacidade usa este módulo

            if pendencias_de_aceite(request.user):
                destino = reverse("privacidade:aceitar") + "?" + urlencode({"next": request.get_full_path()})
                return redirect(destino)
        return view(request, *args, **kwargs)

    return _view


@require_GET
@anunciante_ativo
def painel(request: HttpRequest) -> HttpResponse:
    """Painel: resumo do plano (assinatura real), meus anúncios (do banco, com as ações) e dados da loja."""
    # Imports locais: planos.views e anuncios.views importam este módulo.
    from anuncios.services import anuncios_do_dono, contar_no_plano, pode_renovar, url_publica
    from estatisticas.services import totais_da_loja, totais_por_anuncio
    from planos.services import assinatura_de, pode_publicar

    anunciante = request.user.anunciante
    anuncios = list(anuncios_do_dono(anunciante))
    totais = totais_por_anuncio([anuncio.pk for anuncio in anuncios])
    for anuncio in anuncios:
        anuncio.renovavel = pode_renovar(anuncio)
        anuncio.totais = totais[anuncio.pk]
        anuncio.url = url_publica(anuncio)
    uso = contar_no_plano(anunciante)
    return render(
        request,
        "anunciantes/painel.html",
        {
            "tela": "painel",
            "ajuda_itens": textos_ajuda("painel"),
            "anunciante": anunciante,
            "anuncios": anuncios,
            "assinatura": assinatura_de(anunciante),
            "uso": uso,
            "pode_publicar": pode_publicar(anunciante, uso=uso),
            "estatisticas_30_dias": totais_da_loja(anunciante.pk, dias=30),
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


# --- Página da loja: painel, vitrine pública e lista de lojas (Sprint 2) ----------------


@require_http_methods(["GET", "POST"])
@anunciante_ativo
def painel_loja(request: HttpRequest) -> HttpResponse:
    """Painel › Página da loja: edita os dados públicos, logo e capa (com prévia ao vivo).

    Sempre a loja de quem está logado (`request.user.anunciante`): não há id na URL.
    Imagens vão para o Celery; a página avisa enquanto estiverem sendo processadas.
    """
    anunciante = request.user.anunciante
    form = PaginaLojaForm(request.POST or None, request.FILES or None, instance=anunciante)
    if request.method == "POST" and form.is_valid():
        anunciante = form.save(commit=False)
        anunciante.ponto = ponto(form.cleaned_data["latitude"], form.cleaned_data["longitude"])
        anunciante._change_reason = "Página da loja editada pelo anunciante."
        anunciante.save()
        for tipo in ("logo", "capa"):
            envio = form.cleaned_data.get(f"{tipo}_envio")
            if envio:
                getattr(anunciante, f"{tipo}_original").save(envio.name, envio, save=True)
                processar_imagem_loja_tarefa.delay(anunciante.pk, tipo)
        messages.success(request, "Alterações salvas. Sua página já está atualizada.")
        return redirect("anunciantes:painel_loja")
    return render(
        request,
        "anunciantes/painel_loja.html",
        {
            "tela": "painel_loja",
            "ajuda_itens": textos_ajuda("painel_loja"),
            "anunciante": anunciante,
            "form": form,
            "endereco_base": f"{settings.SITE_URL.split('://', 1)[-1]}/loja/",
        },
    )


@require_GET
def loja(request: HttpRequest, slug: str) -> HttpResponse:
    """Vitrine pública /loja/<slug>/: só lojas visíveis (ativas, área atendida); o resto dá 404."""
    anunciante = get_object_or_404(lojas_visiveis(), slug=slug)
    anuncios = anuncios_da_loja(anunciante)
    url = settings.SITE_URL + reverse("anunciantes:loja", args=[anunciante.slug])
    descricao = anunciante.sobre or (
        f"{anunciante.get_tipo_display()} em {anunciante.cidade.nome}: "
        "veja os anúncios e fale direto pelo WhatsApp."
    )
    imagem = settings.SITE_URL + anunciante.logo.url if anunciante.logo else ""
    schema = {
        "@context": "https://schema.org",
        "@type": anunciante.tipo_schema,
        "name": anunciante.nome_publico,
        "url": url,
        "description": descricao,
        "areaServed": f"{anunciante.cidade.nome}/{anunciante.cidade.uf_id}",
    }
    if imagem:
        schema["image"] = imagem
    if anunciante.mostrar_no_mapa and anunciante.endereco_publico:
        schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": anunciante.endereco_publico,
            "addressLocality": anunciante.cidade.nome,
            "addressRegion": anunciante.cidade.uf_id,
            "addressCountry": "BR",
        }
    return render(
        request,
        "anunciantes/loja.html",
        {
            "tela": "loja",
            "anunciante": anunciante,
            "anuncios": anuncios,
            "descricao": descricao[:160],
            "url_canonica": url,
            "imagem_og": imagem,
            "schema": schema,
            "localizacao": localizacao_da_loja(anunciante),
            "mostrar_demo": settings.MOSTRAR_DEMO and anunciante.demo,
        },
    )


@require_GET
def loja_whatsapp(request: HttpRequest, slug: str) -> HttpResponse:
    """Botão WhatsApp da loja: redireciona para o wa.me (o número não fica em texto no HTML).

    ARQUITETURA §5: dificulta robôs que coletam telefones. A contagem de cliques entra na Sprint 5.
    """
    anunciante = get_object_or_404(lojas_visiveis(), slug=slug)
    texto = quote(f"Olá! Vi a loja {anunciante.nome_publico} no {configuracao().nome}.")
    return HttpResponseRedirect(f"https://wa.me/{anunciante.whatsapp.lstrip('+')}?text={texto}")


@require_GET
def lojas(request: HttpRequest) -> HttpResponse:
    """/lojas/: lojas verificadas com filtro por tipo e cidade, 24 por página."""
    tipo = request.GET.get("tipo", "")
    cidade = request.GET.get("cidade", "")
    pagina = Paginator(listar_lojas(tipo, cidade), 24).get_page(request.GET.get("pagina"))
    return render(
        request,
        "anunciantes/lojas.html",
        {
            "tela": "lojas",
            "ajuda_itens": textos_ajuda("lojas"),
            "pagina": pagina,
            "lojas_vitrine": [loja_para_vitrine(a) for a in pagina.object_list],
            "tipos": Anunciante.Tipo.choices,
            "cidades": cidades_com_lojas(),
            "tipo_escolhido": tipo,
            "cidade_escolhida": cidade,
            "mostrar_demo": settings.MOSTRAR_DEMO,
        },
    )
