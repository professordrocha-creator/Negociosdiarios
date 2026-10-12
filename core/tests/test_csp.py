"""Testes da Content-Security-Policy (django-csp; docs/SEGURANCA.md).

Além do cabeçalho, conferem que NENHUMA página nossa traz script inline, estilo inline (atributo
style ou tag <style>) ou evento onclick=: com a CSP, o navegador bloquearia e a página quebraria.
"""

import re

import pytest
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from anuncios import services
from contas.models import Usuario

pytestmark = pytest.mark.django_db

SCRIPT_INLINE = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*application/(?:ld\+)?json)[^>]*>", re.I)
ESTILO_INLINE = re.compile(r"<style\b|\sstyle=\"", re.I)
EVENTO_INLINE = re.compile(r"\son(?:click|load|change|submit|input|error|mouseover)=", re.I)


def problemas(html: str) -> list[str]:
    """Trechos que a CSP bloquearia."""
    achados = []
    for nome, padrao in (("script", SCRIPT_INLINE), ("estilo", ESTILO_INLINE), ("evento", EVENTO_INLINE)):
        achados += [f"{nome}: {m.group(0)}" for m in padrao.finditer(html)]
    return achados


def test_cabecalho_csp_so_libera_o_site_e_o_openstreetmap(client):
    """Sem 'unsafe-inline', sem CDN; imagens do site, data:, blob: e os tiles do OSM."""
    politica = client.get(reverse("core:inicio"))["Content-Security-Policy"]

    assert "script-src 'self'" in politica and "style-src 'self'" in politica
    assert "unsafe-inline" not in politica and "unsafe-eval" not in politica
    assert "img-src 'self' data: blob: https://tile.openstreetmap.org" in politica
    assert "frame-ancestors 'none'" in politica and "object-src 'none'" in politica


@pytest.mark.parametrize(
    "rota",
    [
        "core:inicio",
        "core:sobre",
        "core:planos",
        "core:anuncie",
        "core:contato",
        "core:privacidade",
        "core:termos",
        "core:cookies",
        "core:imoveis",
        "core:denunciar",
        "anunciantes:lojas",
        "anunciantes:cadastro",
        "contas:entrar",
    ],
)
def test_paginas_publicas_sem_nada_inline(client, rota, tangara):
    """Páginas públicas: nenhum script, estilo ou evento inline."""
    assert problemas(client.get(reverse(rota)).content.decode()) == []


def test_paginas_de_anuncio_loja_e_painel_sem_nada_inline(client, loja, publicado, imovel):
    """Anúncio (com mapa e galeria), loja e todas as telas do painel."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    rascunho = imovel(anunciante, "Apartamento 2 quartos no Centro")
    paginas = [services.url_publica(anuncio), reverse("anunciantes:loja", args=[anunciante.slug])]
    client.force_login(anunciante.usuario)
    paginas += [
        reverse("anunciantes:painel"),
        reverse("anunciantes:painel_loja"),
        reverse("planos:meu_plano"),
        reverse("anuncios:novo"),
        reverse("anuncios:editar", args=[rascunho.codigo]),
        reverse("anuncios:localizacao", args=[rascunho.codigo]),
        reverse("anuncios:fotos", args=[rascunho.codigo]),
        reverse("anuncios:revisao", args=[rascunho.codigo]),
    ]

    for url in paginas:
        resposta = client.get(url)
        assert resposta.status_code == 200, url
        assert problemas(resposta.content.decode()) == [], url


def test_admin_sem_script_inline(client, entrar_no_admin, loja, imovel):
    """Telas do admin que usamos: sem script inline (o admin do Django já é compatível)."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    anuncio = imovel(loja())
    services.enviar_para_publicacao(anuncio)

    for url in (
        reverse("admin:index"),
        reverse("admin:anuncios_anuncioemmoderacao_changelist"),
        reverse("admin:anuncios_anuncioemmoderacao_change", args=[anuncio.pk]),
        reverse("admin:anunciantes_anunciante_changelist"),
        reverse("admin:planos_plano_changelist"),
    ):
        html = client.get(url).content.decode()
        assert [p for p in problemas(html) if p.startswith("script")] == [], url
