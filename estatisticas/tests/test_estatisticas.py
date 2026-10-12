"""Testes das estatísticas: 1 por visitante por dia, sem IP guardado, sem robôs e sem o dono."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from anuncios import services
from estatisticas import services as estatisticas
from estatisticas.models import EstatisticaDiaria

pytestmark = pytest.mark.django_db

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0) Chrome/128"


def visita(client, anuncio, agente=NAVEGADOR, ip="203.0.113.9"):
    """Abre a página do anúncio como um visitante."""
    return client.get(services.url_publica(anuncio), HTTP_USER_AGENT=agente, REMOTE_ADDR=ip)


def total(anuncio, campo="visualizacoes") -> int:
    """Total gravado no banco."""
    return sum(EstatisticaDiaria.objects.filter(anuncio=anuncio).values_list(campo, flat=True))


def test_mesmo_visitante_conta_uma_vez_por_dia(client, loja, publicado):
    """Recarregar a página não infla o número; outro visitante conta."""
    anuncio = publicado(loja())

    visita(client, anuncio)
    visita(client, anuncio)
    visita(client, anuncio, ip="198.51.100.4")

    assert total(anuncio) == 2


@pytest.mark.parametrize(
    "agente",
    [
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "WhatsApp/2.23.20.0 A",
        "facebookexternalhit/1.1",
        "curl/8.4.0",
        "python-requests/2.32",
        "",
    ],
)
def test_robos_e_previas_de_link_nao_contam(client, loja, publicado, agente):
    """Buscadores, a prévia do WhatsApp/Facebook, scripts e requisição sem navegador não contam."""
    anuncio = publicado(loja())

    visita(client, anuncio, agente=agente)

    assert total(anuncio) == 0


def test_dono_nao_conta(client, loja, publicado):
    """O próprio anunciante olhando o anúncio não conta."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    client.force_login(anunciante.usuario)

    visita(client, anuncio)

    assert total(anuncio) == 0


def test_nenhum_ip_e_guardado(client, loja, publicado):
    """No banco só ficam números; no cache, só um hash com sal do dia (sem o IP)."""
    anuncio = publicado(loja())
    ip = "203.0.113.77"

    visita(client, anuncio, ip=ip)

    linha = EstatisticaDiaria.objects.get(anuncio=anuncio)
    assert {f.name for f in EstatisticaDiaria._meta.fields} == {
        "id",
        "demo",
        "anuncio",
        "dia",
        "visualizacoes",
        "cliques_whatsapp",
    }
    assert linha.visualizacoes == 1
    chaves = [k for k in cache._cache if "estat:visualizacoes" in str(k)]  # LocMemCache dos testes
    assert chaves and all(ip not in str(k) for k in chaves)


def test_hash_muda_de_um_dia_para_o_outro():
    """O sal é do dia: a mesma pessoa vira outro hash no dia seguinte (não dá para seguir alguém)."""
    request = RequestFactory().get("/", HTTP_USER_AGENT=NAVEGADOR, REMOTE_ADDR="203.0.113.9")
    hoje = timezone.localdate()

    assert estatisticas.assinatura_do_visitante(request, hoje) != estatisticas.assinatura_do_visitante(
        request, hoje + timedelta(days=1)
    )
    assert "203.0.113.9" not in estatisticas.assinatura_do_visitante(request, hoje)


def test_totais_da_loja_somam_30_dias(loja, publicado):
    """O painel soma os últimos 30 dias (hoje incluído); o 31º dia fica de fora."""
    anuncio = publicado(loja())
    hoje = timezone.localdate()
    EstatisticaDiaria.objects.create(anuncio=anuncio, dia=hoje, visualizacoes=10, cliques_whatsapp=2)
    EstatisticaDiaria.objects.create(anuncio=anuncio, dia=hoje - timedelta(days=29), visualizacoes=5)
    EstatisticaDiaria.objects.create(anuncio=anuncio, dia=hoje - timedelta(days=30), visualizacoes=100)

    assert estatisticas.totais_da_loja(anuncio.anunciante_id) == {"visualizacoes": 15, "cliques_whatsapp": 2}
    assert estatisticas.totais_por_anuncio([anuncio.pk])[anuncio.pk]["visualizacoes"] == 115


def test_evento_desconhecido_e_erro():
    """Só visualização e clique no WhatsApp."""
    with pytest.raises(ValueError):
        estatisticas.registrar(RequestFactory().get("/"), None, "curtidas")
