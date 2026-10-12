"""Testes da busca: páginas por cidade, filtros de imóvel e de veículo, busca por texto (sem acento,
com erro de digitação), ordem, paginação, URL limpa sem JS, HTMX, chips, lista vazia, SEO e sitemap."""

from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from anuncios import services as anuncios
from anuncios.models import Anuncio
from busca import services
from core.models import Bairro, Cidade

pytestmark = pytest.mark.django_db

NAVEGADOR = {"HTTP_USER_AGENT": "Mozilla/5.0"}


@pytest.fixture
def barra(tangara):
    """Barra do Bugres liberada (outra cidade)."""
    return Cidade.objects.create(
        codigo_ibge=5101704,
        nome="Barra do Bugres",
        slug="barra-do-bugres",
        uf=tangara.uf,
        liberada=True,
        ponto=Point(-57.18, -15.07),
    )


@pytest.fixture
def cenario(loja, publicado, veiculo, tangara, barra):
    """Imóveis e veículos publicados em duas cidades, com bairros e preços variados."""
    centro = Bairro.objects.create(cidade=tangara, nome="Centro", slug="centro")
    europa = Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")
    alfa = loja()
    casa = publicado(alfa, "Casa 3 quartos com área gourmet")
    casa.bairro = europa
    casa.save()
    apto = publicado(alfa, "Apartamento 2 quartos mobiliado")
    apto.bairro, apto.preco = centro, Decimal("1600")
    apto.save()
    anuncios.atualizar_anuncio(
        apto,
        {},
        {
            "tipo": "apartamento",
            "modalidade": "aluguel",
            "quartos": 2,
            "vagas": 1,
            "area_total": Decimal("64"),
        },
    )
    chacara = publicado(alfa, "Chácara 2 ha com represa")
    chacara.cidade, chacara.preco = barra, Decimal("380000")
    chacara.save()
    anuncios.atualizar_anuncio(
        chacara, {}, {"tipo": "chacara", "area_total": Decimal("20000"), "vagas": 4, "quartos": 2}
    )
    beta = loja("b@exemplo.com", "Garagem Beta")
    hilux = veiculo(beta)
    cg = veiculo(
        beta,
        "cg_fan",
        titulo="Honda CG 160 Fan Flex 2023",
        cambio="manual",
        combustivel="flex",
        quilometragem=9000,
        ano_fabricacao=2023,
        ano_modelo=2023,
        portas=None,
    )
    for anuncio in (hilux, cg):
        if anuncios.enviar_para_publicacao(anuncio) == Anuncio.Situacao.EM_MODERACAO:
            anuncios.aprovar(anuncio, None)
    Anuncio.objects.filter(pk=cg.pk).update(preco=Decimal("16900"))
    return {"casa": casa, "apto": apto, "chacara": chacara, "hilux": hilux, "cg": cg, "tangara": tangara}


def titulos(client, url: str, **extra) -> list[str]:
    """Títulos dos cards da página (na ordem)."""
    resposta = client.get(url, **NAVEGADOR, **extra)
    assert resposta.status_code == 200, (url, resposta.status_code)
    return [a.titulo for a in resposta.context["anuncios"]]


# --- Páginas e cidade ------------------------------------------------------------------------


def test_paginas_por_categoria_e_cidade(client, cenario):
    """/imoveis/ (todas), /imoveis/mt/tangara-da-serra/ (uma cidade) e /veiculos/."""
    assert set(titulos(client, "/imoveis/")) == {
        "Casa 3 quartos com área gourmet",
        "Apartamento 2 quartos mobiliado",
        "Chácara 2 ha com represa",
    }
    assert "Chácara 2 ha com represa" not in titulos(client, "/imoveis/mt/tangara-da-serra/")
    assert set(titulos(client, "/veiculos/")) == {
        "Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020",
        "Honda CG 160 Fan Flex 2023",
    }


@pytest.mark.parametrize("url", ["/imoveis/mt/cidade-que-nao-existe/", "/imoveis/sp/tangara-da-serra/"])
def test_cidade_inexistente_ou_nao_liberada_da_404(client, tangara, url):
    """Só cidades liberadas têm página."""
    assert client.get(url).status_code == 404


def test_so_anuncios_visiveis(client, cenario, imovel, loja):
    """Rascunho, pausado e de loja suspensa não aparecem."""
    imovel(loja("c@exemplo.com", "Loja Gama"), "Casa rascunho que não aparece")
    anuncios.pausar(cenario["apto"])

    lista = titulos(client, "/imoveis/")

    assert "Casa rascunho que não aparece" not in lista and "Apartamento 2 quartos mobiliado" not in lista


def test_seletor_de_cidade_vira_o_caminho(client, cenario):
    """Sem JS, o formulário manda ?cidade=mt/... e a página redireciona para o caminho limpo."""
    resposta = client.get(
        "/imoveis/", {"cidade": "mt/tangara-da-serra", "q": "", "modalidade": "", "tipo": "casa"}
    )

    assert resposta.status_code == 302 and resposta["Location"] == "/imoveis/mt/tangara-da-serra/?tipo=casa"


def test_valores_invalidos_sao_ignorados(client, cenario):
    """quartos=abc ou ordem estranha não quebram: saem da URL."""
    resposta = client.get("/imoveis/?quartos=abc&ordem=xyz&tipo=nave&tipo=casa")

    assert resposta.status_code == 302 and resposta["Location"] == "/imoveis/?tipo=casa"


# --- Filtros de imóvel -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parametros", "esperado"),
    [
        ("modalidade=aluguel", {"Apartamento 2 quartos mobiliado"}),
        ("tipo=casa&tipo=chacara", {"Casa 3 quartos com área gourmet", "Chácara 2 ha com represa"}),
        ("preco_min=100000&preco_max=400000", {"Chácara 2 ha com represa"}),
        ("quartos=3", {"Casa 3 quartos com área gourmet"}),
        ("vagas=2", {"Chácara 2 ha com represa"}),
        ("area_min=10000", {"Chácara 2 ha com represa"}),
        ("area_max=100", {"Apartamento 2 quartos mobiliado"}),
    ],
)
def test_filtros_de_imovel(client, cenario, parametros, esperado):
    """Negócio, tipo (vários), faixa de preço, quartos, vagas e área."""
    assert set(titulos(client, f"/imoveis/?{parametros}")) == esperado


def test_filtro_de_bairro_so_com_cidade(client, cenario):
    """O bairro vale dentro da cidade e o seletor só lista bairros com anúncio."""
    resposta = client.get("/imoveis/mt/tangara-da-serra/?bairro=centro", **NAVEGADOR)

    assert [a.titulo for a in resposta.context["anuncios"]] == ["Apartamento 2 quartos mobiliado"]
    html = resposta.content.decode()
    assert '<option value="jardim-europa"' in html and 'id="campo-bairro"' in html


# --- Filtros de veículo ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parametros", "esperado"),
    [
        ("tipo=moto", {"Honda CG 160 Fan Flex 2023"}),
        ("marca=toyota", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("marca=toyota&modelo=hilux", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("ano_min=2021", {"Honda CG 160 Fan Flex 2023"}),
        ("ano_max=2020", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("km_max=10.000", {"Honda CG 160 Fan Flex 2023"}),
        ("cambio=automatico", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("combustivel=flex", {"Honda CG 160 Fan Flex 2023"}),
        ("preco_max=20000", {"Honda CG 160 Fan Flex 2023"}),
    ],
)
def test_filtros_de_veiculo(client, cenario, parametros, esperado):
    """Tipo, marca, modelo, ano, km, câmbio, combustível e preço."""
    resposta = client.get(f"/veiculos/?{parametros}", **NAVEGADOR, follow=True)

    assert {a.titulo for a in resposta.context["anuncios"]} == esperado


def test_modelos_so_da_marca_escolhida(client, cenario):
    """O select de modelo só tem opções depois da marca, e só modelos com anúncio."""
    sem_marca = client.get("/veiculos/", **NAVEGADOR).content.decode()
    com_marca = client.get("/veiculos/?marca=toyota", **NAVEGADOR).content.decode()

    assert '<option value="hilux"' not in sem_marca
    assert '<option value="hilux"' in com_marca and '<option value="cg"' not in com_marca


# --- Busca por texto -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("categoria", "termo", "esperado"),
    [
        ("imoveis", "apartamento centro", {"Apartamento 2 quartos mobiliado"}),
        ("imoveis", "chacara", {"Chácara 2 ha com represa"}),
        ("imoveis", "CHÁCARA", {"Chácara 2 ha com represa"}),
        ("imoveis", "tangara", {"Casa 3 quartos com área gourmet", "Apartamento 2 quartos mobiliado"}),
        ("imoveis", "apartamnto", {"Apartamento 2 quartos mobiliado"}),
        ("veiculos", "hilux", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("veiculos", "HILUX diesel", {"Toyota Hilux CD SRV 4x4 2.8 TDI Diesel Aut. 2020"}),
        ("veiculos", "honda", {"Honda CG 160 Fan Flex 2023"}),
    ],
)
def test_busca_por_texto(client, cenario, categoria, termo, esperado):
    """Com ou sem acento, maiúscula, várias palavras e erro de digitação."""
    resposta = client.get(f"/{categoria}/", {"q": termo}, **NAVEGADOR)

    assert {a.titulo for a in resposta.context["anuncios"]} == esperado


def test_indice_atualiza_ao_editar(client, cenario):
    """Mudou o título: a busca acha o novo e esquece o antigo."""
    anuncios.atualizar_anuncio(cenario["casa"], {"titulo": "Sobrado reformado com piscina"})

    assert titulos(client, "/imoveis/?q=sobrado") == ["Sobrado reformado com piscina"]
    assert titulos(client, "/imoveis/?q=gourmet") == []


# --- Ordem e paginação -----------------------------------------------------------------------


def test_ordem_por_preco(client, cenario):
    """Menor e maior preço; o padrão é mais recentes."""
    assert titulos(client, "/imoveis/?ordem=menor_preco")[0] == "Apartamento 2 quartos mobiliado"
    assert titulos(client, "/imoveis/?ordem=maior_preco")[0] == "Casa 3 quartos com área gourmet"
    recentes = Anuncio.objects.filter(categoria="imovel").order_by("-publicado_em").first()
    assert titulos(client, "/imoveis/")[0] == recentes.titulo


def test_paginacao_de_24(client, loja, publicado):
    """30 anúncios: 24 na 1ª página, 6 na 2ª; página fora do fim cai na última."""
    from anuncios.tests.conftest import foto_pronta  # noqa: F401  (publicado já cria foto)

    alfa = loja(slug_plano="premium")
    for i in range(30):
        publicado(alfa, f"Casa número {i:02d} com quintal")

    primeira = client.get("/imoveis/", **NAVEGADOR)
    segunda = client.get("/imoveis/?pagina=2", **NAVEGADOR)

    assert len(primeira.context["anuncios"]) == 24 and len(segunda.context["anuncios"]) == 6
    assert 'href="/imoveis/?pagina=2"' in primeira.content.decode()
    assert len(client.get("/imoveis/?pagina=99", **NAVEGADOR).context["anuncios"]) == 6


# --- HTMX, chips e lista vazia ---------------------------------------------------------------


def test_htmx_responde_sem_redirecionar_e_atualiza_a_url(client, cenario):
    """Pedido do HTMX: 200 direto (mesmo com a URL "suja") e cabeçalho HX-Push-Url com a limpa."""
    resposta = client.get(
        "/imoveis/",
        {"cidade": "mt/tangara-da-serra", "tipo": "casa", "q": ""},
        HTTP_HX_REQUEST="true",
        **NAVEGADOR,
    )

    assert resposta.status_code == 200
    assert resposta["HX-Push-Url"] == "/imoveis/mt/tangara-da-serra/?tipo=casa"
    html = resposta.content.decode()
    assert 'id="resultados"' in html and 'id="campo-bairro"' in html
    assert "HX-Request" in resposta["Vary"]


def test_formulario_funciona_sem_javascript(client, cenario):
    """O formulário é GET para a própria busca, com botão de aplicar (HTMX é só um atalho)."""
    html = client.get("/imoveis/", **NAVEGADOR).content.decode()

    assert '<form id="filtros-form"' in html and 'method="get" action="/imoveis/"' in html
    assert 'hx-get="/imoveis/"' in html and 'type="submit"' in html
    assert 'data-bs-toggle="offcanvas" data-bs-target="#filtros"' in html  # painel no celular


def test_chips_com_x_e_limpar_tudo(client, cenario):
    """Cada filtro ativo vira um chip com o link sem ele; "Limpar tudo" volta ao início."""
    resposta = client.get("/imoveis/mt/tangara-da-serra/?tipo=casa&tipo=apartamento&quartos=2", **NAVEGADOR)
    chips = {c.rotulo: c.url_sem for c in resposta.context["chips"]}

    assert chips["Casa"] == "/imoveis/mt/tangara-da-serra/?tipo=apartamento&quartos=2"
    assert chips["2+ quartos"] == "/imoveis/mt/tangara-da-serra/?tipo=casa&tipo=apartamento"
    assert chips["Tangará da Serra"] == "/imoveis/?tipo=casa&tipo=apartamento&quartos=2"
    assert "Limpar tudo" in resposta.content.decode()


def test_lista_vazia_sugere_ampliar(client, cenario):
    """Nada encontrado: mensagem amigável e links para ampliar a busca."""
    html = client.get("/imoveis/mt/tangara-da-serra/?tipo=fazenda", **NAVEGADOR).content.decode()

    assert "Nenhum anúncio encontrado" in html and "Buscar em todas as cidades" in html
    assert 'href="/imoveis/?tipo=fazenda"' in html


# --- SEO -------------------------------------------------------------------------------------


def test_titulo_e_descricao_por_cidade_e_tipo(client, cenario):
    """ "Casas à venda em Tangará da Serra – MT" e description com a quantidade."""
    html = client.get(
        "/imoveis/mt/tangara-da-serra/?modalidade=venda&tipo=casa", **NAVEGADOR
    ).content.decode()

    assert "<title>Casas à venda em Tangará da Serra – MT ·" in html
    assert 'content="Casas à venda em Tangará da Serra – MT: 1 anúncio de imóveis' in html


def test_titulo_de_veiculo_com_marca_e_modelo(cenario):
    """ "Caminhonetes Toyota Hilux à venda em ..."."""
    rotulos = {"marca": {"toyota": "Toyota"}, "modelo": {"hilux": "Hilux"}}
    filtros = {"tipo": ["caminhonete"], "marca": "toyota", "modelo": "hilux"}

    assert services.titulo("veiculos", cenario["tangara"], filtros, rotulos) == (
        "Caminhonetes Toyota Hilux à venda em Tangará da Serra – MT"
    )


def test_canonical_sem_ordem_e_pagina(client, cenario):
    """Ordem e página não mudam o canonical; filtros de conteúdo sim."""
    html = client.get(
        "/imoveis/mt/tangara-da-serra/?tipo=casa&ordem=menor_preco", **NAVEGADOR
    ).content.decode()

    assert '<link rel="canonical" href="http://testserver/imoveis/mt/tangara-da-serra/?tipo=casa">' in html


@pytest.mark.parametrize(
    ("parametros", "indexa"),
    [
        ("", True),
        ("modalidade=venda&tipo=casa", True),
        ("modalidade=venda&tipo=casa&quartos=3", False),
        ("tipo=casa&tipo=apartamento&tipo=terreno", False),
        ("q=casa", False),
        ("tipo=casa&ordem=menor_preco&pagina=2", True),
    ],
)
def test_noindex_com_filtros_demais(client, cenario, parametros, indexa):
    """Combinações simples são indexadas; muitas ou com texto, noindex (mas follow)."""
    resposta = client.get(f"/imoveis/?{parametros}", **NAVEGADOR, follow=True)

    assert ('content="noindex, follow"' not in resposta.content.decode()) is indexa


def test_sitemap_tem_cidades_e_tipos(client, cenario):
    """Páginas de busca com anúncio entram no sitemap (cidade, cidade + negócio + tipo, cidade + tipo)."""
    xml = client.get("/sitemap.xml").content.decode()

    assert "/imoveis/mt/tangara-da-serra/</loc>" in xml
    assert "/imoveis/mt/tangara-da-serra/?modalidade=venda&amp;tipo=casa</loc>" in xml
    assert "/veiculos/mt/tangara-da-serra/?tipo=caminhonete</loc>" in xml
    assert "?tipo=fazenda" not in xml  # sem anúncio, não entra


# --- Home, menu e rodapé ---------------------------------------------------------------------


def test_home_busca_e_atalhos_levam_para_a_busca(client, cenario):
    """Formulários GET da home, atalhos de categoria e menu apontam para /imoveis/ e /veiculos/."""
    html = client.get(reverse("core:inicio"), **NAVEGADOR).content.decode()

    assert 'action="/imoveis/"' in html and 'action="/veiculos/"' in html
    assert (
        'name="modalidade"' in html
        and 'name="marca"' in html
        and '<option value="toyota">Toyota</option>' in html
    )
    assert 'href="/imoveis/?tipo=casa"' in html and 'href="/veiculos/?tipo=caminhonete"' in html
    assert 'title="Em breve"' not in html.split('class="nd-atalhos"', 1)[1].split("</nav>", 1)[0]


def test_paginas_em_breve_de_imoveis_e_veiculos_sairam(client, tangara):
    """/imoveis/ e /veiculos/ são a busca de verdade (sem o aviso "em breve")."""
    for url in ("/imoveis/", "/veiculos/"):
        html = client.get(url, **NAVEGADOR).content.decode()
        assert 'id="filtros-form"' in html and ">Em breve<" not in html
