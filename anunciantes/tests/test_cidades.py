"""Testes de regiões, bairros e solicitações de cidade (cadastro em cidade não atendida)."""

import re

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.gis.geos import Point
from django.core import mail
from django.urls import reverse

from anunciantes.models import Anunciante, SolicitacaoCidade
from anunciantes.services import aprovar, liberar_cidade_da_solicitacao, recusar_solicitacao
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.models import Bairro, Cidade, Regiao

pytestmark = pytest.mark.django_db

LISTA = "admin:anunciantes_solicitacaocidade_changelist"


@pytest.fixture
def sinop(tangara):
    """Cidade de MT ainda não atendida."""
    return Cidade.objects.create(
        codigo_ibge=5107909, nome="Sinop", slug="sinop", uf=tangara.uf, ponto=Point(-55, -11)
    )


@pytest.fixture
def pedido(criar_anunciante, sinop):
    """Loja pendente em Sinop, com e-mail confirmado, e a solicitação da cidade."""
    loja = criar_anunciante(
        "sinop@exemplo.com", "Loja Sinop", status=Anunciante.Status.PENDENTE, cidade=sinop
    )
    return SolicitacaoCidade.objects.create(anunciante=loja, cidade=sinop)


@pytest.fixture
def equipe(client, entrar_no_admin, db):
    """Superusuário logado no admin."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    return daniel


def test_nao_aprova_loja_de_cidade_nao_atendida(pedido, equipe):
    """Primeiro libera a cidade; só depois aprova a loja."""
    with pytest.raises(ValueError, match="ainda não é atendida"):
        aprovar(pedido.anunciante, equipe)


def test_liberar_cidade_atende_todos_os_pedidos_dela(pedido, equipe, criar_anunciante, sinop):
    """Liberar uma vez resolve todos os pedidos pendentes da mesma cidade; depois a loja é aprovada."""
    outra = criar_anunciante(
        "sinop2@exemplo.com", "Outra Sinop", status=Anunciante.Status.PENDENTE, cidade=sinop
    )
    SolicitacaoCidade.objects.create(anunciante=outra, cidade=sinop)

    atendidas = liberar_cidade_da_solicitacao(pedido, equipe)

    assert atendidas == 2
    sinop.refresh_from_db()
    assert sinop.liberada and not sinop.liberada_pela_demo
    assert set(SolicitacaoCidade.objects.values_list("status", flat=True)) == {"liberada"}
    assert SolicitacaoCidade.objects.first().decidido_por == equipe
    aprovar(pedido.anunciante, equipe)  # agora pode


def test_acao_liberar_no_admin(client, pedido, equipe, sinop):
    """A ação "Liberar a cidade" do admin libera e informa o próximo passo."""
    resposta = client.post(
        reverse(LISTA),
        {"action": "liberar_cidades_selecionadas", ACTION_CHECKBOX_NAME: [pedido.pk]},
        follow=True,
    )

    sinop.refresh_from_db()
    assert sinop.liberada
    assert "Agora aprove as lojas em Anunciantes" in resposta.content.decode()


def test_recusar_exige_motivo_e_avisa_por_email(client, pedido, equipe):
    """Recusar: sem motivo não acontece; com motivo, recusa e manda o motivo ao anunciante."""
    tela = client.post(reverse(LISTA), {"action": "recusar_selecionadas", ACTION_CHECKBOX_NAME: [pedido.pk]})
    assert tela.status_code == 200 and "Motivo" in tela.content.decode()

    client.post(
        reverse(LISTA),
        {"action": "recusar_selecionadas", ACTION_CHECKBOX_NAME: [pedido.pk], "aplicar": "1", "motivo": ""},
    )
    pedido.refresh_from_db()
    assert pedido.status == "pendente" and not mail.outbox

    client.post(
        reverse(LISTA),
        {
            "action": "recusar_selecionadas",
            ACTION_CHECKBOX_NAME: [pedido.pk],
            "aplicar": "1",
            "motivo": "Ainda sem equipe na região.",
        },
    )
    pedido.refresh_from_db()
    assert pedido.status == "recusada" and pedido.motivo == "Ainda sem equipe na região."
    email = mail.outbox[-1]
    assert email.to == ["sinop@exemplo.com"] and "Ainda sem equipe na região." in email.body
    assert email.subject.startswith("Ainda não atendemos a sua cidade")


def test_recusar_sem_motivo_no_servico(pedido, equipe):
    """A regra vale também fora do admin."""
    with pytest.raises(ValueError):
        recusar_solicitacao(pedido, equipe, "  ")


def test_solicitacao_nao_e_criada_nem_apagada_no_admin(client, pedido, equipe):
    """Solicitações nascem só do cadastro e ficam como registro da decisão."""
    assert client.get(reverse("admin:anunciantes_solicitacaocidade_add")).status_code == 403
    assert (
        client.get(reverse("admin:anunciantes_solicitacaocidade_delete", args=[pedido.pk])).status_code == 403
    )


def test_aviso_a_equipe_menciona_cidade_nao_atendida(client, criar_anunciante, sinop, equipe):
    """O e-mail "novo cadastro" avisa que a cidade ainda precisa ser liberada."""
    from anunciantes.services import link_confirmacao

    loja = criar_anunciante(
        "nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE, cidade=sinop, sem_confirmacao=True
    )
    client.get(re.sub(r"^https?://[^/]+", "", link_confirmacao(loja.usuario)))  # caminho do link

    assert "AINDA NÃO ATENDIDA" in mail.outbox[-1].body


# --- Regiões e bairros no admin ----------------------------------------------------------


def test_admin_de_regioes_e_bairros(client, equipe, tangara):
    """Listas e formulários abrem; a cidade mostra os bairros dentro dela."""
    regiao = Regiao.objects.create(nome="Região de Tangará", slug="regiao-de-tangara")
    regiao.cidades.add(tangara)
    Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")

    assert "Região de Tangará" in client.get(reverse("admin:core_regiao_changelist")).content.decode()
    assert client.get(reverse("admin:core_regiao_change", args=[regiao.pk])).status_code == 200
    assert "Jardim Europa" in client.get(reverse("admin:core_bairro_changelist")).content.decode()
    pagina_cidade = client.get(reverse("admin:core_cidade_change", args=[tangara.pk])).content.decode()
    assert "Jardim Europa" in pagina_cidade


def test_bairro_tem_endereco_unico_por_cidade(tangara):
    """Dois bairros com o mesmo endereço na mesma cidade não pode."""
    from django.db import IntegrityError

    Bairro.objects.create(cidade=tangara, nome="Centro", slug="centro")
    with pytest.raises(IntegrityError):
        Bairro.objects.create(cidade=tangara, nome="Centro 2", slug="centro")
