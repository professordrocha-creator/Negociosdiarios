"""Regressão LGPD: as rotinas que apagam dados do guia (`limpar_guia_vencido` e `apagar_guia_demo`) não podem
deixar nenhuma linha de histórico (django-simple-history) com contato da pessoa. O próprio delete grava uma
última linha no histórico; antes ela sobrava porque o histórico era apagado ANTES dos registros."""

from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone

from core.models import Cidade
from guia import services
from guia.models import AceitePublicacao, ContatoConvite, PedidoDoPerfil, PerfilGuia, TermoGuia
from guia.tests.test_regras import _texto_de_todas_as_tabelas_do_guia

pytestmark = pytest.mark.django_db

CONTATO_PEDIDO = "titular.regressao@exemplo.com"
NOME_ACEITE = "Pessoa Regressao Silva"


def test_limpeza_depois_do_prazo_nao_deixa_historico(perfil_publicado):
    """Perfil com aceite (histórico), pedido de remoção (histórico) e remoção; passado o prazo de prova, a
    rotina apaga tudo e nenhuma linha de histórico (nem o contato ou o nome do aceite) sobra."""
    perfil = perfil_publicado()
    aceite = services.aceite_vigente(perfil)
    AceitePublicacao.objects.filter(pk=aceite.pk).update(nome_digitado=NOME_ACEITE)
    services.revogar_aceite(AceitePublicacao.objects.get(pk=aceite.pk), None, "pedido")  # mais histórico
    pedido = services.registrar_pedido(perfil, "remover", "Quero sair", CONTATO_PEDIDO)
    services.remover_perfil(perfil, None, "Pedido do titular.", pedido=pedido)
    assert PedidoDoPerfil.history.filter(id=pedido.pk).exists()  # o cenário tem histórico de verdade
    seis_anos = timezone.now() - timedelta(days=6 * 365)
    PerfilGuia.objects.filter(pk=perfil.pk).update(removido_em=seis_anos)
    PedidoDoPerfil.objects.update(decidido_em=seis_anos)

    assert services.limpar_guia_vencido() == 1

    assert not PedidoDoPerfil.history.filter(id=pedido.pk).exists()
    assert not AceitePublicacao.history.filter(id=aceite.pk).exists()
    assert not PerfilGuia.history.filter(id=perfil.pk).exists()
    tudo = _texto_de_todas_as_tabelas_do_guia()
    assert CONTATO_PEDIDO not in tudo and NOME_ACEITE not in tudo


def test_pedido_decidido_antigo_de_perfil_que_continua_nao_deixa_historico(perfil_publicado):
    """Pedido já decidido há mais que o prazo, de um perfil que segue publicado: sai sem sobrar histórico."""
    perfil = perfil_publicado()
    pedido = services.registrar_pedido(perfil, "alterar", "Novo horário", CONTATO_PEDIDO)
    services.responder_pedido(pedido, None, PedidoDoPerfil.Status.ATENDIDO, "Feito.")
    PedidoDoPerfil.objects.filter(pk=pedido.pk).update(decidido_em=timezone.now() - timedelta(days=6 * 365))

    services.limpar_guia_vencido()

    assert not PedidoDoPerfil.objects.exists() and not PedidoDoPerfil.history.filter(id=pedido.pk).exists()
    assert CONTATO_PEDIDO not in _texto_de_todas_as_tabelas_do_guia()


@pytest.fixture
def cidades_demo(tangara):
    """As 3 cidades dos perfis demo, liberadas."""
    for codigo, nome, slug in (
        (5101704, "Barra do Bugres", "barra-do-bugres"),
        (5102637, "Campo Novo do Parecis", "campo-novo-do-parecis"),
    ):
        Cidade.objects.create(
            codigo_ibge=codigo, nome=nome, slug=slug, uf=tangara.uf, liberada=True, ponto=Point(-57.2, -14.3)
        )


def test_apagar_demo_nao_deixa_historico(cidades_demo, termo):
    """Demo completa (perfis, aceites, pedidos, uma remoção, convites, interessados, termo demo) e o apagar:
    nenhuma linha de histórico de pedido, aceite, perfil, contato ou termo demo sobra."""
    services.criar_guia_demo()
    assert PedidoDoPerfil.history.exists() and AceitePublicacao.history.exists()

    services.apagar_guia_demo()

    assert not PedidoDoPerfil.history.exists()
    assert not AceitePublicacao.history.exists()
    assert not PerfilGuia.history.exists()
    assert not ContatoConvite.history.exists()
    assert not TermoGuia.history.filter(demo=True).exists()
    assert "@demo.invalid" not in _texto_de_todas_as_tabelas_do_guia()
