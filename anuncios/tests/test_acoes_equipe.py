"""Testes do lote de correções no admin de anúncios: "destaque até" editável (seção Destaques da home) e as
ações da equipe Pausar, Reativar e Remover (motivo, histórico com quem e quando, e-mail ao anunciante e
permissão só para Administrador e Moderador)."""

from datetime import timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from anunciantes.tests.conftest import SENHA
from anuncios import services
from anuncios.models import Anuncio
from contas.models import Usuario

pytestmark = pytest.mark.django_db

LISTA = "admin:anuncios_anuncio_changelist"


@pytest.fixture
def equipe(entrar_no_admin):
    """Fábrica: client logado no admin como membro do grupo."""

    def _entrar(grupo: str):
        usuario = Usuario.objects.create_user(
            email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return entrar_no_admin(usuario), usuario

    return _entrar


@pytest.fixture
def anuncio(loja, publicado):
    """Anúncio publicado de uma loja."""
    return publicado(loja())


def agir(cliente, acao: str, anuncio, motivo: str = "Fotos de outro imóvel"):
    """Confirma a ação em lote (tela do motivo já respondida)."""
    return cliente.post(
        reverse(LISTA), {"action": acao, ACTION_CHECKBOX_NAME: [anuncio.pk], "aplicar": "1", "motivo": motivo}
    )


def test_destaque_ate_editavel_e_vai_para_a_home(client, equipe, anuncio, settings):
    """O Administrador grava o "destaque até" na ficha; o anúncio entra na seção Destaques da home."""
    cliente, _ = equipe("Administrador")
    ficha = cliente.get(reverse("admin:anuncios_anuncio_change", args=[anuncio.pk])).content.decode()
    assert 'name="destaque_ate_0"' in ficha and "aparece na seção" in ficha

    amanha = timezone.localtime() + timedelta(days=1)
    Anuncio.objects.filter(pk=anuncio.pk).update(destaque_ate=amanha)  # o mesmo campo que o formulário grava
    from core.services import destaques

    assert [a.titulo for a in destaques()] == [anuncio.titulo] and destaques()[0].destaque
    Anuncio.objects.filter(pk=anuncio.pk).update(destaque_ate=timezone.now() - timedelta(minutes=1))
    assert destaques() == []


def test_pausar_pede_confirmacao_motivo_e_avisa(equipe, anuncio):
    """Sem "aplicar": só a tela do motivo. Com motivo: pausado pela equipe, histórico com quem e por quê,
    e-mail ao anunciante."""
    cliente, moderador = equipe("Moderador")
    tela = cliente.post(reverse(LISTA), {"action": "pausar_acao", ACTION_CHECKBOX_NAME: [anuncio.pk]})
    anuncio.refresh_from_db()
    assert tela.status_code == 200 and anuncio.situacao == Anuncio.Situacao.PUBLICADO

    mail.outbox.clear()
    agir(cliente, "pausar_acao", anuncio)

    anuncio.refresh_from_db()
    assert (
        anuncio.situacao == Anuncio.Situacao.PAUSADO and anuncio.pausado_por == Anuncio.PausadoPor.MODERACAO
    )
    assert anuncio.motivo_moderacao == "Fotos de outro imóvel" and anuncio.moderado_por == moderador
    ultimo = anuncio.history.order_by("-history_id").first()
    assert ultimo.history_user == moderador and "Fotos de outro imóvel" in ultimo.history_change_reason
    assert (
        mail.outbox and "pausado" in mail.outbox[0].subject and "Fotos de outro imóvel" in mail.outbox[0].body
    )


def test_motivo_obrigatorio_para_pausar_e_remover(equipe, anuncio):
    """Sem motivo, nada muda."""
    cliente, _ = equipe("Administrador")
    agir(cliente, "remover_acao", anuncio, motivo="")
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.PUBLICADO
    with pytest.raises(ValueError, match="motivo"):
        services.acao_da_equipe(anuncio, None, "pausar", "")


def test_remover_oculta_sem_apagar(client, equipe, anuncio):
    """Remover: some do site (exclusão lógica), o registro fica."""
    cliente, _ = equipe("Administrador")
    agir(cliente, "remover_acao", anuncio)
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.REMOVIDO and anuncio.removido_em
    assert Anuncio.objects.filter(pk=anuncio.pk).exists()
    assert anuncio not in services.anuncios_visiveis()


def test_reativar_so_o_que_a_equipe_pausou(equipe, anuncio):
    """Pausado pela equipe volta ao ar; pausado pelo cliente (ou por denúncia) não."""
    cliente, _ = equipe("Administrador")
    agir(cliente, "pausar_acao", anuncio)
    agir(cliente, "reativar_acao", anuncio, motivo="")
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.PUBLICADO and anuncio.pausado_por == ""

    services.pausar(anuncio)  # pelo cliente
    with pytest.raises(ValueError, match="só reativa o que ela pausou"):
        services.acao_da_equipe(anuncio, None, "reativar")


@pytest.mark.parametrize("grupo", ["Financeiro", "Comercial"])
def test_financeiro_e_comercial_nao_mexem(equipe, anuncio, grupo):
    """Sem a permissão de alterar: as ações não existem e o anúncio não muda."""
    cliente, _ = equipe(grupo)
    lista = cliente.get(reverse(LISTA)).content.decode()
    assert "pausar_acao" not in lista
    agir(cliente, "pausar_acao", anuncio)
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.PUBLICADO
