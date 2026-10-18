"""Views públicas do app guia: páginas do Guia de Negócios (G2) e a página de aceite (G1).

Páginas (docs/GUIA.md §6): só com o guia no ar; desligado, 404 para o público e pré-visualização para a
equipe logada (com a faixa "Guia desligado"). Perfil que não está publicado dá 404. Contato (§7): o número
nunca vai em texto ao HTML; WhatsApp e telefone passam por URLs que contam o clique, com limite por hora.
Aceite: link secreto, fora dos buscadores, sem cache e sem vazar o endereço (com o token) para outros sites;
token inválido, usado ou vencido dão a mesma resposta ("link já utilizado"), sem nenhum dado do perfil.
Regras em guia.services; aqui só se orquestra.
"""

from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.vary import vary_on_headers

from busca.services import cidade_escolhida
from core.services import cidades_atendidas, limite_por_ip_excedido, textos_ajuda
from guia import services
from guia.forms import AceiteForm
from guia.models import CategoriaServico, PerfilGuia


def _privada(resposta: HttpResponse) -> HttpResponse:
    """noindex, no-referrer e sem cache (o endereço tem o token)."""
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    resposta["Referrer-Policy"] = "no-referrer"
    resposta["Cache-Control"] = "private, no-store"
    return resposta


def _link_invalido(request: HttpRequest) -> HttpResponse:
    """Mesma tela para token inexistente, usado ou vencido (não revela se existiu)."""
    return _privada(render(request, "guia/aceite_invalido.html", {"tela": "guia_aceite"}, status=410))


@require_http_methods(["GET", "POST"])
def aceite(request: HttpRequest, token: str) -> HttpResponse:
    """Prévia da ficha + termo (versão e data) + nome digitado + "Autorizo". Confirmado, publica na hora.

    Limite de tentativas por visitante e por hora (`ConfiguracaoGuia`; o IP só entra como resumo).
    Campo-armadilha preenchido (robô): mesma tela de sucesso, sem gravar nada.
    """
    convite = services.convite_valido(token)
    termo = services.termo_vigente()
    if convite is None or termo is None:
        return _link_invalido(request)
    perfil = convite.perfil
    form = AceiteForm(request.POST or None)
    status = 200
    if request.method == "POST":
        status = 400
        limite = services.configuracao_guia().tentativas_aceite_por_hora
        if limite_por_ip_excedido(request, "guia_aceite", limite=limite, janela_segundos=3600):
            form.add_error(None, "Muitas tentativas na última hora. Aguarde um pouco e tente de novo.")
            status = 429
        elif form.is_valid():
            if form.cleaned_data["site_empresa"]:  # robô: finge que deu certo
                return _privada(render(request, "guia/aceite_concluido.html", {"tela": "guia_aceite"}))
            try:
                registro = services.aceitar_convite(
                    token,
                    form.cleaned_data["nome"],
                    request.META.get("REMOTE_ADDR", ""),
                    request.META.get("HTTP_USER_AGENT", ""),
                )
            except services.PublicacaoRecusada:
                form.add_error(
                    None,
                    "Não foi possível publicar agora: falta completar o cadastro. "
                    "Fale com quem enviou o link.",
                )
            except ValueError:
                return _link_invalido(request)
            else:
                contexto = {"tela": "guia_aceite", "aceite": registro, "perfil": registro.perfil}
                return _privada(render(request, "guia/aceite_concluido.html", contexto))
    contexto = {
        "tela": "guia_aceite",
        "ajuda_itens": textos_ajuda("guia_aceite"),
        "previa": services.previa(perfil),
        "termo": termo,
        "blocos": services.blocos_do_termo(termo),
        "nome_guia": services.configuracao_guia().nome_guia,
        "form": form,
    }
    return _privada(render(request, "guia/aceite.html", contexto, status=status))


# --- Páginas públicas (G2) -------------------------------------------------------------------------------


def _liberar(request: HttpRequest) -> bool:
    """Guia desligado: 404 para o público; a equipe logada vê (pré-visualização). Devolve se é prévia."""
    pode, previa = services.pode_ver(request.user)
    if not pode:
        raise Http404("Guia desligado.")
    return previa


def _contexto(request: HttpRequest, tela: str, previa: bool, **extra) -> dict:
    """O que toda página do guia recebe: nome da aba, prévia da equipe, faixa de demonstração e ajuda."""
    return {
        "tela": tela,
        "ajuda_itens": textos_ajuda(tela),
        "nome_guia": services.configuracao_guia().nome_guia,
        "previa_equipe": previa,
        "mostrar_demo": settings.MOSTRAR_DEMO,
        **extra,
    }


def _url_completa(caminho: str) -> str:
    """Endereço absoluto (canonical, Open Graph, schema.org)."""
    return settings.SITE_URL + caminho


@require_GET
def inicio(request: HttpRequest) -> HttpResponse:
    """/guia/: escolher a cidade (e o estado, com 2+ liberados) e buscar por texto.

    Só a cidade escolhida (sem texto): vai direto para a página da cidade. Com texto: resultados
    (noindex), na cidade escolhida ou em todas.
    """
    previa = _liberar(request)
    termo = request.GET.get("q", "").strip()[:100]
    valor_cidade = request.GET.get("cidade", "")
    cidade = cidade_escolhida(valor_cidade) if valor_cidade else None
    if cidade is not None and not termo:
        return redirect("guia:cidade", cidade.uf_id.lower(), cidade.slug)
    perfis, categorias = services.buscar_no_guia(termo, cidade) if termo else ([], [])
    agora = timezone.now()
    itens = [(p, None if p.regulamentado else services.aberto_agora(p, agora)) for p in perfis]
    estados = cidades_atendidas()
    contexto = _contexto(
        request,
        "guia_inicio",
        previa,
        estados_atendidos=estados,
        mostrar_estado=len(estados) > 1,
        termo=termo,
        cidade=cidade,
        valor_cidade=valor_cidade,
        itens=itens,
        categorias=categorias,
        buscou=bool(termo),
        url_canonica=_url_completa(reverse("guia:inicio")),
    )
    return render(request, "guia/inicio.html", contexto)


@require_GET
def cidade(request: HttpRequest, uf: str, cidade: str) -> HttpResponse:
    """/guia/<uf>/<cidade>/: grupos e categorias com a contagem de empresas da cidade."""
    previa = _liberar(request)
    atual = services.cidade_do_guia(uf, cidade)
    if atual is None:
        raise Http404("Cidade não atendida.")
    grupos = services.grupos_da_cidade(atual)
    contexto = _contexto(
        request,
        "guia_cidade",
        previa,
        cidade=atual,
        grupos=grupos,
        total=services.perfis_da_cidade(atual).count(),
        url_canonica=_url_completa(reverse("guia:cidade", args=[uf.lower(), atual.slug])),
    )
    return render(request, "guia/cidade.html", contexto)


@require_GET
@vary_on_headers("HX-Request")
def categoria(request: HttpRequest, uf: str, cidade: str, categoria: str) -> HttpResponse:
    """/guia/<uf>/<cidade>/<categoria>/: lista + mapa, filtros "Aberto agora" e bairro (GET; com HTMX
    troca só os resultados). Rodízio estável por dia; página fina (< mínimo) e filtrada: noindex, follow."""
    previa = _liberar(request)
    atual = services.cidade_do_guia(uf, cidade)
    escolhida = CategoriaServico.objects.filter(slug=categoria, ativa=True).first()
    if atual is None or escolhida is None:
        raise Http404("Página não encontrada.")
    todos = services.rodizio(
        services.perfis_da_cidade(atual).filter(categorias=escolhida),
        f"{timezone.localdate()}-{atual.pk}-{escolhida.pk}",
    )
    aberto = request.GET.get("aberto") == "1"
    bairro = request.GET.get("bairro", "")[:100]
    perfis = services.filtrar_lista(todos, aberto, bairro)
    pagina = Paginator(perfis, 24).get_page(request.GET.get("pagina"))
    agora = timezone.now()
    itens = [(p, None if p.regulamentado else services.aberto_agora(p, agora)) for p in pagina.object_list]
    bairros = sorted({(p.bairro.slug, p.bairro.nome) for p in todos if p.bairro_id}, key=lambda b: b[1])
    filtrada = aberto or bool(bairro) or pagina.number > 1
    titulo = f"{escolhida.nome} em {atual.nome} - {atual.uf_id}"
    contexto = _contexto(
        request,
        "guia_categoria",
        previa,
        cidade=atual,
        categoria=escolhida,
        titulo=titulo,
        descricao=(
            f"{len(todos)} {'opção' if len(todos) == 1 else 'opções'} de {escolhida.nome.lower()} em "
            f"{atual.nome}/{atual.uf_id}: WhatsApp, endereço ou área de atendimento e horário. "
            f"Grátis no {services.configuracao_guia().nome_guia}."
        ),
        total=len(todos),
        itens=itens,
        pagina=pagina,
        aberto=aberto,
        bairro=bairro,
        bairros=bairros,
        pontos=services.pontos_do_mapa(perfis),
        a_domicilio=sum(1 for p in perfis if p.atendimento == p.Atendimento.DOMICILIO),
        indexavel=services.indexavel(len(todos)) and not filtrada,
        url_canonica=_url_completa(services.url_categoria(atual, escolhida)),
    )
    return render(request, "guia/categoria.html", contexto)


def _perfil_visivel(**filtro) -> PerfilGuia:
    """Perfil publicado e visível; qualquer outra situação é 404 (nunca mostra dados)."""
    perfil = services.perfis_visiveis().filter(**filtro).prefetch_related("categorias").first()
    if perfil is None:
        raise Http404("Perfil não encontrado.")
    return perfil


@require_GET
def empresa(request: HttpRequest, slug: str) -> HttpResponse:
    """/guia/empresa/<slug>/: ficha. Regulamentado: só nome, especialidade, registro, contato e local."""
    previa = _liberar(request)
    perfil = _perfil_visivel(slug=slug)
    if not previa:
        services.registrar_evento(request, perfil, services.VISUALIZACAO)
    url = _url_completa(reverse("guia:empresa", args=[perfil.slug]))
    regulamentado = perfil.regulamentado
    categorias = [c for c in perfil.categorias.all() if c.ativa]
    contexto = _contexto(
        request,
        "guia_empresa",
        previa,
        perfil=perfil,
        regulamentado=regulamentado,
        categorias=categorias,
        primeira=categorias[0] if categorias else None,
        aberto=None if regulamentado else services.aberto_agora(perfil),
        semana=[] if regulamentado or not perfil.horarios else services.horarios_da_semana(perfil),
        localizacao=services.ponto_da_ficha(perfil),
        schema=services.schema_da_ficha(perfil, url),
        url_canonica=url,
        imagem_og=settings.SITE_URL + perfil.logo.url if perfil.logo and not regulamentado else "",
    )
    return render(request, "guia/empresa.html", contexto)


def _noindex(resposta: HttpResponse) -> HttpResponse:
    """Endereços de contato: fora dos buscadores e sem cache."""
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    resposta["Cache-Control"] = "private, no-store"
    return resposta


@require_GET
def contato_whatsapp(request: HttpRequest, pk: int) -> HttpResponse:
    """Conta o clique e redireciona para o wa.me (o número nunca está no HTML). Limite por visitante."""
    _liberar(request)
    perfil = _perfil_visivel(pk=pk)
    if not perfil.whatsapp:
        raise Http404("Sem WhatsApp.")
    if not services.contato_liberado(request):
        return _noindex(render(request, "guia/contato_limite.html", {"perfil": perfil}, status=429))
    services.registrar_evento(request, perfil, services.CLIQUE_WHATSAPP)
    return _noindex(HttpResponseRedirect(services.link_whatsapp_perfil(perfil)))


@require_GET
def contato_telefone(request: HttpRequest, pk: int) -> HttpResponse:
    """ "Ver telefone": com HTMX devolve só o número (troca o botão); sem JS, uma página com o número.

    Conta o clique (uma vez por visitante por dia; robôs não contam) e respeita o limite por hora.
    """
    _liberar(request)
    perfil = _perfil_visivel(pk=pk)
    if not perfil.telefone:
        raise Http404("Sem telefone.")
    htmx = request.headers.get("HX-Request") == "true"
    if not services.contato_liberado(request):
        modelo = "guia/_contato_limite.html" if htmx else "guia/contato_limite.html"
        # Com HTMX responde 200 (o HTMX não troca o botão em resposta de erro) com o aviso no lugar.
        return _noindex(render(request, modelo, {"perfil": perfil}, status=200 if htmx else 429))
    services.registrar_evento(request, perfil, services.CLIQUE_TELEFONE)
    contexto = {
        "perfil": perfil,
        "numero": services.telefone_legivel(perfil.telefone),
        "tela": "guia_telefone",
    }
    modelo = "guia/_telefone.html" if htmx else "guia/telefone.html"
    return _noindex(render(request, modelo, contexto))
