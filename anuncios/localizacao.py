"""Localização pública do imóvel (docs/LGPD.md §4): a única regra de "onde o público vê o imóvel".

Usada pela página do anúncio (círculo), pelo `DetalheImovel.ponto_publico` (gravado já deslocado) e,
por ele, pelo mapa da busca e pelo filtro "Buscar nesta área". Assim o ponto real de um anúncio com
localização aproximada nunca sai do servidor, nem por um JSON, nem por perguntas de "está neste
retângulo?" (o filtro olha o ponto deslocado, não o real).

- exata: o ponto marcado;
- aproximada: o ponto deslocado de 60 a 150 m numa direção fixa por anúncio (HMAC do código com a
  SECRET_KEY: recarregar não revela o ponto pela média), arredondado a 4 casas (~11 m);
- só o bairro (ou sem ponto): nenhum.
"""

from __future__ import annotations

import math

from django.contrib.gis.geos import Point
from django.utils.crypto import salted_hmac

RAIO_APROXIMADO_M = 300
DESLOCAMENTO_MAXIMO_M = 150
METROS_POR_GRAU = 111_320
EXATA, APROXIMADA = "exata", "aproximada"
# Raio aceito entre o ponto marcado (imóvel ou loja) e o centro da cidade (graus; ~0,6° ≈ 65 km):
# pega clique errado no mapa.
DISTANCIA_MAXIMA_GRAUS = 0.6


def longe_da_cidade(lat: float, lng: float, cidade) -> bool:
    """O ponto marcado está longe demais da sede da cidade? (cidade sem ponto: não dá para saber.)"""
    if cidade is None or not cidade.ponto:
        return False
    return (
        abs(lat - cidade.ponto.y) > DISTANCIA_MAXIMA_GRAUS
        or abs(lng - cidade.ponto.x) > DISTANCIA_MAXIMA_GRAUS
    )


def deslocamento(codigo: str) -> tuple[float, float]:
    """(norte, leste) em metros: fixo por anúncio, entre 40% e 100% de 150 m."""
    resumo = salted_hmac("anuncios.localizacao_aproximada", codigo).digest()
    angulo = int.from_bytes(resumo[:4], "big") / 2**32 * 2 * math.pi
    distancia = (0.4 + 0.6 * int.from_bytes(resumo[4:8], "big") / 2**32) * DESLOCAMENTO_MAXIMO_M
    return distancia * math.cos(angulo), distancia * math.sin(angulo)


def ponto_publico(codigo: str | None, ponto: Point | None, exibir: str) -> Point | None:
    """O ponto que o público pode ver (ou None)."""
    if ponto is None or not codigo:
        return None
    lat, lng = ponto.y, ponto.x
    if exibir == EXATA:
        return Point(round(lng, 6), round(lat, 6), srid=4326)
    if exibir == APROXIMADA:
        norte, leste = deslocamento(codigo)
        lat_c = lat + norte / METROS_POR_GRAU
        lng_c = lng + leste / (METROS_POR_GRAU * math.cos(math.radians(lat)))
        return Point(round(lng_c, 4), round(lat_c, 4), srid=4326)
    return None
