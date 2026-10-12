"""Testes da publicidade (Sprint 7A): escolha e rodízio, rótulo e rel sponsored, clique só http/https,
métricas sem IP nem cookie, imagens (WebP no tamanho da Configuracao, sem EXIF), rotina diária
(encerrar e avisar), loja só compra se for assinante, fatura da campanha pela página pública,
painel/CSV e demonstração."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.services import configuracao
from pagamentos.models import Fatura
from pagamentos.services import confirmar_pagamento, gerar_fatura_campanha
from publicidade import services
from publicidade.forms import BannerForm, CampanhaForm
from publicidade.models import Banner, Campanha, Formato, MetricaDiaria, Patrocinador

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate
NAVEGADOR = "Mozilla/5.0"


def png(largura: int, altura: int, exif: bool = False, formato: str = "PNG") -> bytes:
    """Imagem de teste; com `exif`, leva GPS."""
    saida = io.BytesIO()
    imagem = Image.new("RGB", (largura, altura), (20, 90, 120))
    if exif:
        dados = Image.Exif()
        dados[0x8825] = {2: (15.0, 30.0, 0.0)}
        imagem.save(saida, format="JPEG", exif=dados)
    else:
        imagem.save(saida, format=formato)
    return saida.getvalue()


@pytest.fixture
def patrocinador(db):
    """Empresa de fora (não é loja do site)."""
    return Patrocinador.objects.create(nome="Construtora Teste", email="contato@construtora.exemplo.com")


@pytest.fixture
def campanha(patrocinador):
    """Fábrica: campanha ativa (por padrão no ar hoje) com uma peça pronta do formato da 1ª posição."""

    def _criar(posicoes=("home_topo",), inicio=-1, fim=10, situacao="ativa", nome="Lançamento", cidades=()):
        c = Campanha.objects.create(
            patrocinador=patrocinador,
            nome=nome,
            posicoes=list(posicoes),
            inicio=HOJE() + timedelta(days=inicio),
            fim=HOJE() + timedelta(days=fim),
            valor=Decimal("500"),
            situacao=situacao,
        )
        c.cidades.set(cidades)
        formato = services.FORMATO_DA_POSICAO[posicoes[0]]
        banner = Banner(
            campanha=c, formato=formato, link="https://www.exemplo.com/", texto_alternativo="Peça"
        )
        if formato == Formato.NATIVO:
            banner.titulo, banner.texto = "Título nativo", "Texto do anúncio nativo"
        else:
            banner.imagem.save("i.webp", ContentFile(png(10, 10, formato="WEBP")), save=False)
            banner.imagem_celular.save("c.webp", ContentFile(png(10, 10, formato="WEBP")), save=False)
        banner.save()
        return c

    return _criar


def requisicao(agente: str = NAVEGADOR, htmx: bool = False):
    """Requisição falsa para a tag (User-Agent e HTMX)."""
    cabecalhos = {"HTTP_USER_AGENT": agente}
    if htmx:
        cabecalhos["HTTP_HX_REQUEST"] = "true"
    return RequestFactory().get("/", **cabecalhos)


def renderizar(posicao: str, request=None, cidade=None) -> str:
    """Renderiza a tag {% publicidade %}."""
    modelo = Template("{% load publicidade %}{% publicidade posicao cidade %}")
    return modelo.render(Context({"posicao": posicao, "cidade": cidade, "request": request or requisicao()}))


def total(campo: str) -> int:
    """Soma de impressões ou cliques de todas as peças."""
    return sum(MetricaDiaria.objects.values_list(campo, flat=True))


# --- Escolha, rodízio e exibição -------------------------------------------------------------------


def test_so_aparece_campanha_ativa_no_periodo_e_na_posicao(campanha):
    """Rascunho, pausada, antes do início, depois do fim e outra posição: nada."""
    no_ar = campanha(nome="No ar")
    campanha(nome="Rascunho", situacao="rascunho")
    campanha(nome="Futura", inicio=2, fim=5)
    campanha(nome="Passada", inicio=-10, fim=-1)
    campanha(nome="Outra posição", posicoes=("anuncio_topo",))

    assert [p.campanha for p in services.escolher("home_topo", quantos=5)] == [no_ar]


def test_rodizio_entre_campanhas_da_mesma_posicao(campanha, monkeypatch):
    """Duas campanhas na mesma posição: o sorteio alterna entre elas a cada carregamento."""
    a, b = campanha(nome="A"), campanha(nome="B")
    vistas = set()
    for semente in range(20):
        services.random.seed(semente)
        vistas.add(services.escolher("home_topo")[0].campanha)
    assert vistas == {a, b}


def test_cidade_da_campanha(campanha, tangara):
    """Campanha com cidade só aparece nela; sem cidade, em todo lugar (mas a home não tem cidade)."""
    local = campanha(nome="Local", posicoes=("busca_topo",), cidades=[tangara])

    assert services.escolher("busca_topo", tangara)[0].campanha == local
    assert services.escolher("busca_topo", None) == []


def test_demo_so_com_mostrar_demo(campanha, settings):
    """Peça de demonstração nunca aparece sem MOSTRAR_DEMO."""
    c = campanha()
    Banner.objects.update(demo=True)
    assert services.escolher("home_topo") == []
    settings.MOSTRAR_DEMO = True
    assert services.escolher("home_topo")[0].campanha == c


def test_rotulo_publicidade_rel_sponsored_e_link_de_clique(campanha):
    """Rótulo visível, link pela contagem e rel="sponsored noopener"; conta 1 impressão."""
    c = campanha()
    html = renderizar("home_topo")
    peca = c.banners.get()

    assert "Publicidade" in html and 'rel="sponsored noopener"' in html
    assert f'href="{reverse("publicidade:clique", args=[peca.pk])}"' in html
    assert peca.link not in html  # o destino só aparece no redirecionamento
    assert total("impressoes") == 1


def test_robo_e_htmx_nao_contam_impressao(campanha):
    """Robô não conta; troca parcial do HTMX (a peça não foi redesenhada) também não."""
    campanha()
    renderizar("home_topo", requisicao("Googlebot/2.1"))
    renderizar("home_topo", requisicao(htmx=True))
    assert total("impressoes") == 0


def test_nativo_e_cards_do_rodape(campanha):
    """Nativo é texto com o rótulo; o rodapé mostra até 3 cards de campanhas diferentes."""
    campanha(posicoes=("busca_nativo",), nome="Nativo")
    for n in range(4):
        campanha(posicoes=("rodape_card",), nome=f"Card {n}")
    assert "Título nativo" in renderizar("busca_nativo") and "Publicidade" in renderizar("busca_nativo")
    assert renderizar("rodape_card").count('class="nd-pub-card ') == 3


# --- Clique e métricas ----------------------------------------------------------------------------


def test_clique_conta_e_redireciona_sem_cookie(client, campanha):
    """Clique: +1 no dia, 302 para o site do patrocinador, nenhum cookie, noindex."""
    peca = campanha().banners.get()
    resposta = client.get(reverse("publicidade:clique", args=[peca.pk]), HTTP_USER_AGENT=NAVEGADOR)

    assert resposta.status_code == 302 and resposta["Location"] == "https://www.exemplo.com/"
    assert not resposta.cookies and "noindex" in resposta["X-Robots-Tag"]
    assert MetricaDiaria.objects.get().cliques == 1


def test_clique_de_robo_ou_campanha_fora_do_ar_nao_conta(client, campanha):
    """Robô e campanha encerrada levam ao site, mas não contam."""
    peca = campanha().banners.get()
    url = reverse("publicidade:clique", args=[peca.pk])
    client.get(url, HTTP_USER_AGENT="facebookexternalhit/1.1")
    Campanha.objects.update(situacao="encerrada")
    assert client.get(url, HTTP_USER_AGENT=NAVEGADOR).status_code == 302
    assert total("cliques") == 0


@pytest.mark.parametrize(
    "link", ["javascript:alert(1)", "data:text/html,oi", "ftp://exemplo.com/x", "//evil.com"]
)
def test_link_so_http_ou_https(client, campanha, link):
    """Cadastro recusa e, se um link estranho chegar ao banco, o clique dá 404 (nunca redireciona)."""
    peca = campanha().banners.get()
    peca.link = link
    with pytest.raises(ValidationError):
        peca.full_clean()
    Banner.objects.filter(pk=peca.pk).update(link=link)
    assert (
        client.get(reverse("publicidade:clique", args=[peca.pk]), HTTP_USER_AGENT=NAVEGADOR).status_code
        == 404
    )


def test_metrica_nao_guarda_dado_pessoal():
    """Só peça, dia e totais: nenhum campo de IP, navegador, cookie ou identificador."""
    campos = {f.name for f in MetricaDiaria._meta.get_fields()}
    assert campos == {"id", "banner", "dia", "impressoes", "cliques"}


# --- Imagens ------------------------------------------------------------------------------------------


def test_banner_validado_e_processado_em_webp_sem_exif(campanha):
    """Imagem maior na mesma proporção: aceita, vira WebP no tamanho exato da Configuracao, sem EXIF."""
    c = campanha()
    form = BannerForm(
        data={
            "formato": "banner",
            "texto_alternativo": "Oferta",
            "link": "https://x.exemplo.com/",
            "ativo": True,
        },
        files={
            "envio_imagem": SimpleUploadedFile("b.jpg", png(1940, 180, exif=True), "image/jpeg"),
            "envio_imagem_celular": SimpleUploadedFile("c.png", png(640, 200), "image/png"),
        },
        instance=Banner(campanha=c),
    )
    assert form.is_valid(), form.errors
    banner = form.save()
    services.processar_banner(banner)
    banner.refresh_from_db()

    assert not banner.imagem_original and not banner.imagem_celular_original
    with Image.open(banner.imagem.path) as grande, Image.open(banner.imagem_celular.path) as pequena:
        assert grande.format == "WEBP" and grande.size == (970, 90) and not grande.getexif()
        assert pequena.size == (320, 100)


@pytest.mark.parametrize(
    ("arquivo", "erro"),
    [
        (png(970, 300), "fora da proporção"),
        (png(500, 46), "mínimo é 970×90"),
        (b"nao e imagem", "inválida"),
    ],
)
def test_imagem_fora_do_padrao_e_recusada(campanha, arquivo, erro):
    """Proporção errada, pequena demais ou arquivo falso: recusado com mensagem clara."""
    form = BannerForm(
        data={"formato": "banner", "texto_alternativo": "x", "link": "https://x.exemplo.com/", "ativo": True},
        files={
            "envio_imagem": SimpleUploadedFile("b.png", arquivo, "image/png"),
            "envio_imagem_celular": SimpleUploadedFile("c.png", png(320, 100), "image/png"),
        },
        instance=Banner(campanha=campanha()),
    )
    assert not form.is_valid() and erro in str(form.errors)


def test_tamanhos_e_peso_vem_da_configuracao_e_aparecem_na_ajuda():
    """Mudou no admin, muda a ajuda (e a validação)."""
    config = configuracao()
    config.banner_largura_px, config.limite_banner_kb = 728, 500
    config.save()
    ajuda = BannerForm().fields["envio_imagem"].help_text
    assert "728×90" in ajuda and "500 KB" in ajuda


# --- Rotina diária e regras de venda ---------------------------------------------------------------


def test_rotina_encerra_vencida_e_avisa_7_dias_antes_uma_vez(campanha, equipe_comercial):
    """Passou do fim: encerrada. A até 7 dias do fim: e-mail à equipe uma vez só (recupera dia perdido)."""
    vencida = campanha(nome="Vencida", inicio=-30, fim=-1)
    acabando = campanha(nome="Acabando", fim=6)
    campanha(nome="Longe", fim=30)

    assert services.rotina_de_publicidade() == {"encerradas": 1, "avisos": 1}
    vencida.refresh_from_db()
    assert (
        vencida.situacao == "encerrada"
        and "Encerrada" in vencida.history.order_by("-history_id").first().history_change_reason
    )
    (email,) = mail.outbox
    assert email.to == [equipe_comercial.email] and acabando.nome in email.body and "Longe" not in email.body
    assert services.rotina_de_publicidade() == {"encerradas": 0, "avisos": 0}


def test_loja_do_site_so_compra_publicidade_se_for_assinante(criar_anunciante, loja):
    """Patrocinador ligado a loja sem assinatura não ativa campanha; com assinatura ativa, ativa."""
    sem_plano = criar_anunciante("sem@exemplo.com", "Loja Sem Plano")
    assinante = loja("com@exemplo.com", "Loja Com Plano")
    for anunciante, valido in ((sem_plano, False), (assinante, True)):
        p = Patrocinador.objects.create(
            nome=anunciante.nome_publico, email="p@exemplo.com", anunciante=anunciante
        )
        form = CampanhaForm(
            data={
                "patrocinador": p.pk,
                "nome": "Destaque",
                "posicoes": ["home_topo"],
                "inicio": HOJE(),
                "fim": HOJE() + timedelta(days=30),
                "valor": "300",
                "situacao": "ativa",
            }
        )
        assert form.is_valid() is valido, form.errors


# --- Fatura da campanha ----------------------------------------------------------------------------


def test_fatura_da_campanha_pela_pagina_publica(client, campanha, settings):
    """Gera a fatura (e-mail com o link), a página pública mostra o Pix, recebe o comprovante; confirmar não
    mexe em assinatura; uma fatura por campanha."""
    settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE = (
        "12345678000195",
        "Negocios Diarios",
        "Tangara",
    )
    c = campanha()
    fatura = gerar_fatura_campanha(c)
    link = reverse("pagamentos:fatura_publica", args=[fatura.token])

    (email,) = mail.outbox
    assert email.to == ["contato@construtora.exemplo.com"] and link in email.body
    html = client.get(link).content.decode()
    assert "data:image/svg+xml" in html and "R$ 500" in html and "Construtora Teste" in html
    client.post(
        reverse("pagamentos:fatura_publica_ja_paguei", args=[fatura.token]),
        {"comprovante": SimpleUploadedFile("c.png", png(300, 300), "image/png")},
    )
    fatura.refresh_from_db()
    assert fatura.situacao == Fatura.Situacao.AGUARDANDO
    assert confirmar_pagamento(fatura, None).situacao == "paga" and fatura.assinatura is None
    with pytest.raises(ValueError, match="já tem fatura"):
        gerar_fatura_campanha(c)


def test_link_publico_nao_abre_fatura_de_loja(client, loja):
    """Fatura de assinatura só é paga pelo painel (com login): pelo token dá 404."""
    from pagamentos.services import gerar_fatura
    from planos.services import assinatura_de

    fatura = gerar_fatura(assinatura_de(loja()), avisar=False)
    assert client.get(reverse("pagamentos:fatura_publica", args=[fatura.token])).status_code == 404


def test_acao_gerar_fatura_no_admin(entrar_no_admin, equipe_comercial, campanha):
    """Ação na lista de campanhas gera a fatura."""
    c = campanha()
    client = entrar_no_admin(equipe_comercial)
    client.post(
        reverse("admin:publicidade_campanha_changelist"),
        {"action": "gerar_fatura", ACTION_CHECKBOX_NAME: [c.pk]},
    )
    assert c.faturas.count() == 1


# --- Painel do admin e CSV ------------------------------------------------------------------------------


@pytest.fixture
def equipe_comercial(db):
    """Membro do grupo Comercial."""
    usuario = Usuario.objects.create_user(
        email="comercial@exemplo.com", password=SENHA, nome="Com", is_staff=True
    )
    usuario.groups.add(Group.objects.get(name="Comercial"))
    return usuario


def test_painel_e_csv(entrar_no_admin, equipe_comercial, campanha):
    """Números por campanha no período, CTR e CSV com proteção contra fórmula."""
    c = campanha(nome="=HYPERLINK(1)", fim=3)
    MetricaDiaria.objects.create(
        banner=c.banners.get(), dia=HOJE() - timedelta(days=1), impressoes=200, cliques=5
    )
    client = entrar_no_admin(equipe_comercial)

    html = client.get(reverse("admin:publicidade_campanha_painel")).content.decode()
    assert "200" in html and "2,50%" in html and "termina em breve" in html and "Sobre esta tela" in html
    csv = client.get(reverse("admin:publicidade_campanha_painel_csv")).content.decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in csv and ";200;5;2,50%" in csv


def test_moderador_nao_ve_publicidade(entrar_no_admin):
    """Moderador não vende nem vê publicidade (ADMINISTRACAO.md)."""
    usuario = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    usuario.groups.add(Group.objects.get(name="Moderador"))
    client = entrar_no_admin(usuario)
    assert client.get(reverse("admin:publicidade_campanha_painel")).status_code == 403


# --- Demonstração --------------------------------------------------------------------------------------


def test_publicidade_demo(settings):
    """3 campanhas demo com peças, números e faturas; apagar limpa tudo (e só a publicidade)."""
    assert services.criar_publicidade_demo() == 3
    assert Campanha.objects.filter(demo=True, situacao="ativa").count() == 3
    assert MetricaDiaria.objects.exists() and Fatura.objects.filter(campanha__demo=True).count() == 3
    settings.MOSTRAR_DEMO = True
    assert services.escolher("home_topo") and services.escolher("rodape_card")

    services.apagar_publicidade_demo()
    assert not Campanha.objects.exists() and not Banner.objects.exists() and not Patrocinador.objects.exists()
