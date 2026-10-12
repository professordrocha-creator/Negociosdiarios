"""Desempenho da busca com 2.000 anúncios gerados só durante o teste (nada fica no repositório).

Não é um benchmark: garante que a página não degrada (número de consultas fixo, sem N+1) e responde
num tempo folgado mesmo no CI, e que os índices dos filtros existem no banco.
"""

import os
import random
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.postgres.search import SearchVector
from django.db import connection
from django.db.models import Value
from django.db.models.functions import Lower
from django.utils import timezone

from anuncios.indice import CONFIG
from anuncios.models import Anuncio, DetalheImovel, DetalheVeiculo

pytestmark = pytest.mark.django_db

TOTAL = 2000
# Segundos por página. Folgado: o CI é mais lento, e em paralelo (pytest-xdist) a máquina fica disputada;
# o que pega N+1 com rigor é o número de consultas, que não depende da carga.
TEMPO_MAXIMO = 6.0 if os.environ.get("PYTEST_XDIST_WORKER") else 2.0
CONSULTAS_MAXIMAS = 25
TIPOS = ["casa", "apartamento", "terreno", "chacara", "kitnet"]


@pytest.fixture
def muitos_anuncios(loja, catalogo_teste, tangara):
    """1.500 imóveis e 500 veículos publicados, em lote (rápido), já com o índice de busca."""
    sorteio = random.Random(42)  # noqa: S311 (dados de teste repetíveis)
    anunciante = loja(slug_plano="premium")
    agora = timezone.now()
    anuncios = []
    for i in range(TOTAL):
        veiculo = i >= 1500
        anuncios.append(
            Anuncio(
                anunciante=anunciante,
                categoria="veiculo" if veiculo else "imovel",
                codigo=f"ND-{'VE' if veiculo else 'IM'}-{90000 + i}",
                titulo=f"{'Hilux' if veiculo else sorteio.choice(TIPOS).capitalize()} número {i} centro",
                slug=f"anuncio-{i}",
                descricao="Anúncio gerado para o teste de desempenho.",
                preco=Decimal(sorteio.randint(20_000, 900_000)),
                cidade=tangara,
                situacao="publicado",
                publicado_em=agora - timedelta(minutes=i),
                expira_em=agora + timedelta(days=60),
            )
        )
    criados = Anuncio.objects.bulk_create(anuncios, batch_size=500)
    DetalheImovel.objects.bulk_create(
        [
            DetalheImovel(
                anuncio=a,
                tipo=a.titulo.split()[0].lower(),
                modalidade=sorteio.choice(["venda", "aluguel"]),
                quartos=sorteio.randint(0, 4),
                vagas=sorteio.randint(0, 3),
                area_total=Decimal(sorteio.randint(40, 2000)),
            )
            for a in criados[:1500]
        ],
        batch_size=500,
    )
    DetalheVeiculo.objects.bulk_create(
        [
            DetalheVeiculo(
                anuncio=a,
                versao=catalogo_teste["hilux_srv"],
                ano_fabricacao=2020,
                ano_modelo=2021,
                quilometragem=sorteio.randint(0, 200_000),
                combustivel="diesel",
                cambio="automatico",
                cor="prata",
            )
            for a in criados[1500:]
        ],
        batch_size=500,
    )
    # Índice em lote (o sinal post_save não roda no bulk_create).
    Anuncio.objects.update(
        busca=SearchVector("titulo", config=CONFIG, weight="A")
        + SearchVector(Value("Tangará da Serra"), config=CONFIG, weight="B"),
        texto_busca=Lower("titulo"),
    )
    return criados


@pytest.mark.parametrize(
    "url",
    [
        "/imoveis/",
        "/imoveis/mt/tangara-da-serra/?modalidade=venda&tipo=casa&quartos=2",
        "/imoveis/?preco_min=100000&preco_max=500000&ordem=menor_preco",
        "/imoveis/?q=apartamento+centro",
        "/imoveis/?pagina=40",
        "/veiculos/?marca=toyota&modelo=hilux&km_max=100000",
        "/veiculos/?q=hilux",
    ],
)
def test_busca_rapida_com_2000_anuncios(client, muitos_anuncios, django_assert_max_num_queries, url):
    """Cada página responde no tempo e com um número fixo de consultas (sem uma por anúncio)."""
    client.get(url, HTTP_USER_AGENT="Mozilla/5.0")  # aquece (cache da configuração, catálogo)

    inicio = time.perf_counter()
    with django_assert_max_num_queries(CONSULTAS_MAXIMAS):
        resposta = client.get(url, HTTP_USER_AGENT="Mozilla/5.0")
    duracao = time.perf_counter() - inicio

    assert resposta.status_code == 200
    assert resposta.context["pagina"].paginator.count > 0
    assert duracao < TEMPO_MAXIMO, f"{url} levou {duracao:.2f}s"


def test_indices_dos_filtros_existem():
    """Os índices da busca estão no banco (situação/categoria/cidade/data, preço, texto, trigram...)."""
    with connection.cursor() as cursor:
        indices = set(connection.introspection.get_constraints(cursor, "anuncios_anuncio"))
        indices |= set(connection.introspection.get_constraints(cursor, "anuncios_detalheimovel"))
        indices |= set(connection.introspection.get_constraints(cursor, "anuncios_detalheveiculo"))

    assert {
        "anuncio_vitrine",
        "anuncio_preco",
        "anuncio_busca_gin",
        "anuncio_texto_trgm",
        "imovel_tipo_modalidade",
        "imovel_quartos",
        "veiculo_ano",
        "veiculo_km",
    } <= indices
