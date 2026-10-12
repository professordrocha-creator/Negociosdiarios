"""Testes do mapa da busca (Sprint 5): JSON só com o necessário e com os mesmos filtros da lista, ponto
público (o ponto real de anúncio "aproximado" nunca sai no JSON nem é revelado pelo filtro de área),
"só o bairro" fora do mapa, limite de pontos, "Buscar nesta área", cartões dos marcadores, mapa das
lojas de veículos (só com permissão) e a página da busca sem script nem estilo inline (CSP)."""

import json
import math
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from anuncios import services as anuncios
from anuncios.localizacao import METROS_POR_GRAU
from anuncios.models import Anuncio
from busca import services
from busca.forms import FiltrosImovel

pytestmark = pytest.mark.django_db

NAVEGADOR = {"HTTP_USER_AGENT": "Mozilla/5.0"}
# Ponto real com casas "assinatura": se aparecerem no JSON, o ponto real vazou.
REAL = Point(-57.491234, -14.621234, srid=4326)


def metros(a: Point, b: Point) -> float:
    """Distância aproximada em metros (suficiente para dezenas/centenas de metros)."""
    norte = (a.y - b.y) * METROS_POR_GRAU
    leste = (a.x - b.x) * METROS_POR_GRAU * math.cos(math.radians(a.y))
    return math.hypot(norte, leste)


def com_localizacao(anuncio: Anuncio, exibir: str, ponto: Point | None = REAL) -> Anuncio:
    """Muda o ponto e o modo de exibição do imóvel (o save recalcula o ponto público)."""
    imovel = anuncio.imovel
    imovel.ponto, imovel.exibir_localizacao = ponto, exibir
    imovel.save()
    anuncio.refresh_from_db()
    return anuncio


def json_do_mapa(client, categoria: str = "imoveis", **parametros) -> dict:
    """Pede o JSON do mapa (todas as cidades) com os parâmetros da busca."""
    resposta = client.get(reverse(f"busca:{categoria}_mapa"), parametros)
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/json"
    return resposta.json()


def retangulo(ponto: Point, folga: float) -> str:
    """ "oeste,sul,leste,norte" em volta do ponto, com `folga` graus para cada lado."""
    return f"{ponto.x - folga},{ponto.y - folga},{ponto.x + folga},{ponto.y + folga}"


@pytest.fixture
def alfa(loja):
    """Imobiliária ativa com plano."""
    return loja()


# --- Ponto público (gravado no save) --------------------------------------------------------


def test_ponto_publico_conforme_a_exibicao(alfa, publicado):
    """Exata = o ponto; aproximada = deslocado 60–150 m (4 casas), sempre o mesmo; só o bairro = nada."""
    anuncio = publicado(alfa)
    com_localizacao(anuncio, "exata")
    assert anuncio.imovel.ponto_publico.coords == pytest.approx(REAL.coords)

    com_localizacao(anuncio, "aproximada")
    publico = anuncio.imovel.ponto_publico
    assert 40 <= metros(publico, REAL) <= 160
    assert round(publico.x, 4) == publico.x and round(publico.y, 4) == publico.y
    com_localizacao(anuncio, "aproximada")  # salvar de novo não "anda" o ponto (sem média por repetição)
    assert anuncio.imovel.ponto_publico.coords == publico.coords

    com_localizacao(anuncio, "so_bairro")
    assert anuncio.imovel.ponto_publico is None
    com_localizacao(anuncio, "exata", ponto=None)
    assert anuncio.imovel.ponto_publico is None


def test_historico_nao_guarda_ponto_publico(alfa, publicado):
    """O ponto público é derivado: fica fora do histórico (não polui nem duplica o ponto)."""
    anuncio = com_localizacao(publicado(alfa), "aproximada")
    historico = anuncio.imovel.history.first()
    assert not hasattr(historico, "ponto_publico")


# --- JSON do mapa ---------------------------------------------------------------------------


def test_json_tem_so_o_necessario(client, alfa, publicado):
    """Por ponto: id, título curto, preço curto, lat e lng. E os totais."""
    anuncio = com_localizacao(publicado(alfa, "Casa " + "muito grande " * 6), "exata")
    dados = json_do_mapa(client)
    assert dados["tipo"] == "anuncios"
    assert dados["total"] == 1 and dados["sem_localizacao"] == 0 and dados["cortado"] is False
    (ponto,) = dados["pontos"]
    assert set(ponto) == {"id", "titulo", "preco", "lat", "lng"}
    assert ponto["id"] == anuncio.codigo
    assert len(ponto["titulo"]) == 60
    assert ponto["preco"] == "420 mil"
    assert (ponto["lat"], ponto["lng"]) == pytest.approx((REAL.y, REAL.x))


def test_ponto_real_de_anuncio_aproximado_nunca_sai_no_json(client, alfa, publicado):
    """O JSON leva o ponto deslocado: nem as coordenadas reais nem as casas decimais delas aparecem."""
    anuncio = com_localizacao(publicado(alfa), "aproximada")
    resposta = client.get(reverse("busca:imoveis_mapa"))
    texto = resposta.content.decode()
    assert "491234" not in texto and "621234" not in texto
    (ponto,) = resposta.json()["pontos"]
    publico = anuncio.imovel.ponto_publico
    assert (ponto["lat"], ponto["lng"]) == (publico.y, publico.x)
    assert metros(Point(ponto["lng"], ponto["lat"]), REAL) >= 40


def test_so_bairro_fica_fora_do_mapa_e_e_contado(client, alfa, publicado):
    """ "Só o bairro" (e sem ponto) não vira marcador: entra em `sem_localizacao`."""
    com_localizacao(publicado(alfa, "Casa no mapa"), "exata")
    com_localizacao(publicado(alfa, "Casa só bairro"), "so_bairro")
    com_localizacao(publicado(alfa, "Casa sem ponto"), "aproximada", ponto=None)
    dados = json_do_mapa(client)
    assert [p["titulo"] for p in dados["pontos"]] == ["Casa no mapa"]
    assert dados["total"] == 1 and dados["sem_localizacao"] == 2


def test_json_usa_os_mesmos_filtros_da_lista(client, alfa, publicado):
    """Filtro de preço, modalidade e texto valem para o mapa como para a lista."""
    casa = com_localizacao(publicado(alfa, "Casa com piscina"), "exata")
    apto = com_localizacao(publicado(alfa, "Apartamento central"), "exata")
    anuncios.atualizar_anuncio(apto, {"preco": Decimal("1600")}, {"modalidade": "aluguel"})
    assert [p["id"] for p in json_do_mapa(client, modalidade="venda")["pontos"]] == [casa.codigo]
    aluguel = json_do_mapa(client, modalidade="aluguel")["pontos"]
    assert [p["id"] for p in aluguel] == [apto.codigo]
    assert aluguel[0]["preco"] == "1,6 mil/mês"
    assert [p["id"] for p in json_do_mapa(client, q="piscina")["pontos"]] == [casa.codigo]


def test_json_so_mostra_anuncio_visivel(client, alfa, publicado):
    """Pausado não entra no mapa."""
    anuncio = com_localizacao(publicado(alfa), "exata")
    Anuncio.objects.filter(pk=anuncio.pk).update(situacao=Anuncio.Situacao.PAUSADO)
    assert json_do_mapa(client)["pontos"] == []


def test_limite_de_pontos(client, alfa, publicado, settings):
    """Acima do limite: só os mais novos, com `cortado` e o total verdadeiro."""
    settings.MAPA_LIMITE_PONTOS = 2
    for n in range(3):
        com_localizacao(publicado(alfa, f"Casa {n}"), "exata", ponto=Point(-57.49 + n / 100, -14.62))
    dados = json_do_mapa(client)
    assert len(dados["pontos"]) == 2 and dados["total"] == 3 and dados["cortado"] is True


def test_json_do_mapa_por_cidade_e_cidade_invalida(client, alfa, publicado):
    """Mesmo caminho da lista (com a UF); cidade não atendida dá 404."""
    com_localizacao(publicado(alfa), "exata")
    url = reverse("busca:imoveis_cidade_mapa", args=["mt", "tangara-da-serra"])
    assert len(client.get(url).json()["pontos"]) == 1
    assert client.get(reverse("busca:imoveis_cidade_mapa", args=["mt", "nao-existe"])).status_code == 404


# --- "Buscar nesta área" --------------------------------------------------------------------


def test_area_filtra_pelo_ponto_publico_nunca_pelo_real(client, alfa, publicado):
    """Um retângulo pequeno em volta do ponto REAL não acha o anúncio aproximado (senão bastaria ir
    diminuindo o retângulo para descobrir onde fica o imóvel); em volta do ponto público, acha."""
    anuncio = com_localizacao(publicado(alfa), "aproximada")
    publico = anuncio.imovel.ponto_publico
    em_volta_do_real = retangulo(REAL, 0.0002)  # ~22 m
    em_volta_do_publico = retangulo(publico, 0.0002)

    assert json_do_mapa(client, area=em_volta_do_real)["pontos"] == []
    assert len(json_do_mapa(client, area=em_volta_do_publico)["pontos"]) == 1
    lista = client.get(reverse("busca:imoveis"), {"area": em_volta_do_real}, follow=True, **NAVEGADOR)
    assert anuncio.titulo not in lista.content.decode()
    lista = client.get(reverse("busca:imoveis"), {"area": em_volta_do_publico}, follow=True, **NAVEGADOR)
    assert anuncio.titulo in lista.content.decode()


def test_area_mantem_os_outros_filtros_e_vira_chip(client, alfa, publicado):
    """Área + outro filtro na URL limpa; chip "Área do mapa" para tirar; página com área não é indexada."""
    com_localizacao(publicado(alfa), "exata")
    area = retangulo(REAL, 0.01)
    resposta = client.get(reverse("busca:imoveis"), {"area": area, "quartos": "3"}, **NAVEGADOR)
    assert resposta.status_code == 302
    destino = resposta["Location"]
    assert "area=" in destino and "quartos=3" in destino
    pagina = client.get(destino, **NAVEGADOR).content.decode()
    assert "Área do mapa" in pagina
    assert 'name="robots" content="noindex' in pagina
    assert "Casa 3 quartos" in pagina


@pytest.mark.parametrize(
    "valor",
    ["abc", "1,2,3", "-57,-14,-58,-13", "-57,-13,-56,-14", "-200,-14,-56,-13", "nan,nan,nan,nan"],
)
def test_area_invalida_e_ignorada(valor, alfa):
    """Texto, ordem trocada ou fora do mundo: o campo é descartado (a busca segue sem ele)."""
    form = FiltrosImovel({"area": valor}, opcoes={"bairro": []})
    assert "area" not in form.filtros()


def test_area_valida_e_normalizada():
    """5 casas decimais (~1 m): URL estável e sem precisão inútil."""
    form = FiltrosImovel({"area": "-57.5,-14.7,-57.4000001,-14.6"}, opcoes={"bairro": []})
    assert form.filtros()["area"] == "-57.50000,-14.70000,-57.40000,-14.60000"


@pytest.mark.parametrize(
    ("valor", "aluguel", "esperado"),
    [
        (Decimal("950"), False, "R$ 950"),
        (Decimal("1600"), True, "1,6 mil/mês"),
        (Decimal("420000"), False, "420 mil"),
        (Decimal("189900"), False, "189,9 mil"),
        (Decimal("1200000"), False, "1,2 mi"),
        (Decimal("2000000"), False, "2 mi"),
    ],
)
def test_preco_curto(valor, aluguel, esperado):
    """Rótulo do marcador: curto para caber no mapa."""
    assert services.preco_curto(valor, aluguel) == esperado


# --- Cartões dos marcadores -----------------------------------------------------------------


def test_cartao_do_anuncio(client, alfa, publicado):
    """Foto, preço, título e link; anúncio que saiu do ar dá 404."""
    anuncio = publicado(alfa)
    resposta = client.get(reverse("busca:cartao_anuncio", args=[anuncio.codigo]))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert anuncio.titulo in html and "R$ 420.000" in html and "<img" in html
    assert anuncios.url_publica(anuncio) in html
    Anuncio.objects.filter(pk=anuncio.pk).update(situacao=Anuncio.Situacao.PAUSADO)
    assert client.get(reverse("busca:cartao_anuncio", args=[anuncio.codigo])).status_code == 404


def test_cartao_da_loja_so_com_permissao(client, alfa):
    """Loja sem "mostrar endereço e mapa" (ou sem ponto) não tem cartão."""
    url = reverse("busca:cartao_loja", args=[alfa.slug])
    assert client.get(url).status_code == 404
    alfa.ponto = Point(-57.5, -14.6, srid=4326)
    alfa.save()
    assert client.get(url).status_code == 404
    alfa.mostrar_no_mapa, alfa.endereco_publico = True, "Av. Brasil, 10"
    alfa.save()
    html = client.get(url).content.decode()
    assert alfa.nome_publico in html and "Av. Brasil, 10" in html


# --- Veículos: mapa das lojas ---------------------------------------------------------------


@pytest.fixture
def garagem(loja, veiculo):
    """Revenda com dois veículos publicados."""
    beta = loja("b@exemplo.com", "Garagem Beta")
    for versao in ("hilux_srv", "corolla_xei"):
        anuncio = veiculo(beta, versao)
        if anuncios.enviar_para_publicacao(anuncio) == Anuncio.Situacao.EM_MODERACAO:
            anuncios.aprovar(anuncio, None)
    return beta


def test_veiculos_so_lojas_que_permitiram(client, garagem):
    """Sem permissão (ou sem ponto) a loja não aparece e os veículos dela contam como "sem localização"."""
    dados = json_do_mapa(client, "veiculos")
    assert dados["tipo"] == "lojas" and dados["pontos"] == [] and dados["sem_localizacao"] == 2

    garagem.ponto = Point(-57.5, -14.6, srid=4326)
    garagem.save()
    assert json_do_mapa(client, "veiculos")["pontos"] == []

    garagem.mostrar_no_mapa = True
    garagem.save()
    dados = json_do_mapa(client, "veiculos")
    assert dados["pontos"] == [
        {"id": garagem.slug, "titulo": "Garagem Beta", "preco": "2 veículos", "lat": -14.6, "lng": -57.5}
    ]
    assert dados["sem_localizacao"] == 0
    filtrado = json_do_mapa(client, "veiculos", tipo="carro")
    assert filtrado["pontos"][0]["preco"] == "1 veículo"


def test_veiculos_area_pelo_ponto_da_loja(client, garagem):
    """ "Buscar nesta área" nos veículos: pelo ponto da loja (que permitiu o mapa)."""
    garagem.ponto, garagem.mostrar_no_mapa = Point(-57.5, -14.6, srid=4326), True
    garagem.save()
    perto = retangulo(garagem.ponto, 0.01)
    longe = retangulo(Point(-56, -15), 0.01)
    assert len(json_do_mapa(client, "veiculos", area=perto)["pontos"]) == 1
    assert json_do_mapa(client, "veiculos", area=longe)["pontos"] == []


# --- Página da busca com o mapa ---------------------------------------------------------------


@pytest.mark.parametrize("categoria", ["imoveis", "veiculos"])
def test_pagina_tem_mapa_e_respeita_a_csp(client, categoria, tangara):
    """Lista | Mapa, o mapa com a URL do JSON e scripts só por arquivo (sem inline nem style="")."""
    html = client.get(reverse(f"busca:{categoria}"), **NAVEGADOR).content.decode()
    assert 'id="mapa-busca"' in html and "Buscar nesta área" in html
    assert f'data-mapa-url="{reverse(f"busca:{categoria}_mapa")}"' in html
    assert "leaflet.markercluster.js" in html and "mapa-busca.js" in html
    assert "<script>" not in html and ' style="' not in html


def test_url_do_mapa_sem_ordem_nem_pagina(tangara):
    """O JSON do mapa não depende de ordem nem de página (todos os pontos da busca)."""
    url = services.url_do_mapa("imoveis", tangara, {"ordem": "menor_preco", "pagina": 2, "quartos": "3"})
    assert url == reverse("busca:imoveis_cidade_mapa", args=["mt", "tangara-da-serra"]) + "?quartos=3"


def test_json_do_mapa_tem_cache_curto_e_nao_e_indexado(client, tangara):
    """Cache público de 1 minuto (o mapa pede de novo a cada filtro) e fora dos buscadores."""
    resposta = client.get(reverse("busca:imoveis_mapa"))
    assert resposta["Cache-Control"] == "public, max-age=60"
    assert resposta["X-Robots-Tag"] == "noindex"
    assert json.loads(resposta.content)["pontos"] == []
