"""Testes do admin de anunciantes: filtro por status e ações Aprovar/Suspender com motivo."""

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.urls import reverse

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario

pytestmark = pytest.mark.django_db

LISTA = "admin:anunciantes_anunciante_changelist"


@pytest.fixture
def admin_logado(client, entrar_no_admin, db):
    """Superusuário logado e verificado no admin."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    return daniel


def acao(client, nome: str, anunciantes, motivo: str | None = None):
    """Dispara a ação do admin; com `motivo`, já confirma a tela intermediária."""
    dados = {"action": nome, ACTION_CHECKBOX_NAME: [a.pk for a in anunciantes]}
    if motivo is not None:
        dados.update(aplicar="1", motivo=motivo)
    return client.post(reverse(LISTA), dados)


def test_lista_filtra_por_status(client, admin_logado, criar_anunciante):
    """Filtro por situação na lista do admin."""
    criar_anunciante("a@exemplo.com", "Loja Pendente", status=Anunciante.Status.PENDENTE)
    criar_anunciante("b@exemplo.com", "Loja Ativa")

    html = client.get(reverse(LISTA), {"status__exact": "pendente"}).content.decode()

    assert "Loja Pendente" in html and "Loja Ativa" not in html


def test_aprovar_pede_motivo_e_ativa(client, admin_logado, criar_anunciante):
    """Aprovar: primeiro a tela do motivo; ao confirmar, ativa e registra quem e por quê."""
    loja = criar_anunciante("a@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)

    tela = acao(client, "aprovar_selecionados", [loja])
    assert tela.status_code == 200 and "Motivo" in tela.content.decode()
    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.PENDENTE  # nada muda antes de confirmar

    acao(client, "aprovar_selecionados", [loja], motivo="CNPJ conferido na Receita.")

    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.ATIVO
    assert loja.motivo_status == "CNPJ conferido na Receita."
    ultimo = loja.history.order_by("-history_id").first()
    assert ultimo.history_user == admin_logado
    assert ultimo.history_change_reason == "CNPJ conferido na Receita."


def test_aprovar_sem_motivo_usa_texto_padrao(client, admin_logado, criar_anunciante):
    """Na aprovação o motivo é opcional."""
    loja = criar_anunciante("a@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)

    acao(client, "aprovar_selecionados", [loja], motivo="")

    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.ATIVO and loja.motivo_status == "Documento conferido."


def test_suspender_exige_motivo(client, admin_logado, criar_anunciante):
    """Sem motivo, a suspensão não acontece e a tela mostra o erro."""
    loja = criar_anunciante("a@exemplo.com", "Loja Ativa")

    resposta = acao(client, "suspender_selecionados", [loja], motivo="  ")

    assert resposta.status_code == 200
    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.ATIVO


def test_suspender_com_motivo(client, admin_logado, criar_anunciante):
    """Com motivo: suspende, guarda o motivo e o histórico."""
    loja = criar_anunciante("a@exemplo.com", "Loja Ativa")

    acao(client, "suspender_selecionados", [loja], motivo="Anúncio enganoso denunciado.")

    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.SUSPENSO
    assert loja.motivo_status == "Anúncio enganoso denunciado."
    assert (
        loja.history.order_by("-history_id").first().history_change_reason == "Anúncio enganoso denunciado."
    )


def test_suspenso_perde_o_painel_na_hora(client, admin_logado, criar_anunciante):
    """Depois de suspenso, o cliente não entra mais no painel."""
    loja = criar_anunciante("a@exemplo.com", "Loja Ativa")
    acao(client, "suspender_selecionados", [loja], motivo="Teste.")

    client.force_login(loja.usuario)

    assert client.get(reverse("anunciantes:painel")).status_code == 403


def test_situacao_nao_e_editada_no_formulario(client, admin_logado, criar_anunciante):
    """Status e motivo só mudam pelas ações (assim o histórico sempre tem o motivo)."""
    loja = criar_anunciante("a@exemplo.com", "Loja Ativa")

    html = client.get(reverse("admin:anunciantes_anunciante_change", args=[loja.pk])).content.decode()

    assert 'name="status"' not in html
    assert 'name="motivo_status"' not in html


def test_moderador_pode_aprovar(client, entrar_no_admin, criar_anunciante):
    """O grupo Moderador aprova anunciantes (docs/ADMINISTRACAO.md)."""
    moderador = Usuario.objects.create_user(
        email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True
    )
    moderador.groups.add(Group.objects.get(name="Moderador"))
    entrar_no_admin(moderador)
    loja = criar_anunciante("a@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)

    acao(client, "aprovar_selecionados", [loja], motivo="Ok.")

    loja.refresh_from_db()
    assert loja.status == Anunciante.Status.ATIVO
