"""Testes do layout base, da home provisória, da página Sobre e do favicon."""

import pytest
from django.urls import reverse

from core.models import Cidade, Estado
from core.services import cidades_atendidas

pytestmark = pytest.mark.django_db


def criar_cidade(estado: Estado, codigo: int, nome: str, slug: str, liberada: bool) -> Cidade:
    """Cria uma cidade de teste com um ponto qualquer."""
    return Cidade.objects.create(
        codigo_ibge=codigo, nome=nome, slug=slug, uf=estado, liberada=liberada, ponto="POINT(-57 -14)"
    )


@pytest.fixture
def mt():
    """Mato Grosso liberado, com uma cidade liberada e outra não."""
    estado = Estado.objects.create(uf="MT", nome="Mato Grosso", liberado=True)
    criar_cidade(estado, 5107958, "Tangará da Serra", "tangara-da-serra", liberada=True)
    criar_cidade(estado, 5103403, "Cuiabá", "cuiaba", liberada=False)
    return estado


def secao_cidades(html: str) -> str:
    """Recorta só a seção "Cidades atendidas" do HTML da home."""
    return html.split('id="cidades"', 1)[1].split("</section>", 1)[0]


@pytest.mark.parametrize("rota", ["core:inicio", "core:sobre"])
def test_paginas_respondem_200_com_layout_base(client, rota):
    """Home e Sobre abrem e usam o layout base com os três parciais."""
    resposta = client.get(reverse(rota))

    assert resposta.status_code == 200
    usados = {t.name for t in resposta.templates}
    assert {"base.html", "_topo.html", "_rodape.html", "_ajuda.html"} <= usados


def test_home_mostra_cidade_liberada_e_esconde_nao_liberada(client, mt):
    """Na seção de cidades aparece só a liberada."""
    html = client.get(reverse("core:inicio")).content.decode()

    cidades = secao_cidades(html)
    assert "Tangará da Serra" in cidades
    assert "Cuiabá" not in cidades
    assert "Cuiabá" not in html  # nem no seletor da busca


def test_home_esconde_cidade_liberada_de_estado_bloqueado(client, mt):
    """Cidade liberada de estado não liberado não aparece (as duas chaves precisam estar ligadas)."""
    rondonia = Estado.objects.create(uf="RO", nome="Rondônia", liberado=False)
    criar_cidade(rondonia, 1100205, "Porto Velho", "porto-velho", liberada=True)

    html = client.get(reverse("core:inicio")).content.decode()

    assert "Porto Velho" not in html


def test_home_funciona_com_zero_cidades_liberadas(client):
    """Banco vazio (ou nada liberado): a página abre e mostra o aviso de "em breve"."""
    resposta = client.get(reverse("core:inicio"))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Estamos preparando a chegada às primeiras cidades" in secao_cidades(html)
    assert "Encontre seu próximo imóvel ou veículo</h1>" in html  # sem "em UF"


def test_home_com_um_estado_mostra_uf_no_titulo_e_esconde_nome_do_estado(client, mt):
    """Um estado liberado: título diz "em MT" e a lista não repete o nome do estado."""
    html = client.get(reverse("core:inicio")).content.decode()

    assert "Encontre seu próximo imóvel ou veículo em MT" in html
    assert "Mato Grosso</h3>" not in secao_cidades(html)


def test_home_com_dois_estados_agrupa_por_estado(client, mt):
    """Dois estados liberados: cidades agrupadas sob o nome de cada estado."""
    goias = Estado.objects.create(uf="GO", nome="Goiás", liberado=True)
    criar_cidade(goias, 5208707, "Goiânia", "goiania", liberada=True)

    cidades = secao_cidades(client.get(reverse("core:inicio")).content.decode())

    assert "Goiás</h3>" in cidades
    assert "Mato Grosso</h3>" in cidades
    assert cidades.index("Goiás</h3>") < cidades.index("Goiânia") < cidades.index("Mato Grosso</h3>")


def test_home_mostra_destaques_e_recem_anunciados_em_breve(client):
    """As duas seções de anúncios existem, com o aviso "Em breve"."""
    html = client.get(reverse("core:inicio")).content.decode()

    assert "Destaques" in html
    assert "Recém-anunciados" in html
    assert html.count("Em breve") >= 2


def test_layout_usa_identidade_do_context_processor(client, settings):
    """Nome e linha da região vêm do context processor "site" (não fixos no HTML)."""
    settings.SITE_NOME = "Nome de Teste"
    settings.SITE_LINHA_REGIAO = "Linha de teste"
    settings.SITE_EMPRESA = "Empresa de Teste"
    settings.SITE_CIDADE_SEDE = "Cidade de Teste, XX"

    html = client.get(reverse("core:sobre")).content.decode()

    assert "Nome de Teste" in html
    assert "Linha de teste" in html
    assert "Empresa de Teste" in html
    assert "Cidade de Teste, XX" in html
    assert "D'Rocha" not in html and "D&#x27;Rocha" not in html


def test_layout_tem_favicon_e_arquivos_estaticos(client):
    """Cabeçalho carrega CSS, JS, fontes e favicon da pasta static/, sem nada de terceiros."""
    html = client.get(reverse("core:inicio")).content.decode()

    for arquivo in [
        "css/bootstrap.min.css",
        "css/nd.css",
        "js/bootstrap.bundle.min.js",
        "img/simbolo.svg",
        "fonts/figtree-latin.woff2",
        "fonts/bricolage-grotesque-latin.woff2",
    ]:
        assert f"/static/{arquivo}" in html
    assert "googleapis" not in html  # fontes locais: o IP do visitante não vai ao Google (LGPD)


def test_favicon_ico_redireciona_para_static(client):
    """/favicon.ico (pedido automático dos navegadores) aponta para o arquivo estático."""
    resposta = client.get("/favicon.ico")

    assert resposta.status_code == 301
    assert resposta["Location"] == "/static/img/favicon.ico"


def test_cidades_atendidas_agrupa_e_ordena(mt):
    """O serviço devolve só estados com cidades liberadas, em ordem alfabética."""
    goias = Estado.objects.create(uf="GO", nome="Goiás", liberado=True)
    Estado.objects.create(uf="SP", nome="São Paulo", liberado=True)  # liberado, mas sem cidade liberada
    criar_cidade(goias, 5208707, "Goiânia", "goiania", liberada=True)
    criar_cidade(goias, 5201405, "Aparecida de Goiânia", "aparecida-de-goiania", liberada=True)

    grupos = cidades_atendidas()

    assert [g.estado.uf for g in grupos] == ["GO", "MT"]
    assert [c.nome for c in grupos[0].cidades] == ["Aparecida de Goiânia", "Goiânia"]
    assert [c.nome for c in grupos[1].cidades] == ["Tangará da Serra"]
