"""Testes do "esqueci minha senha": link de uso único, só clientes, sessões encerradas, limite por IP."""

import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario

pytestmark = pytest.mark.django_db

SENHA_NOVA = "Outra-Senha-Forte-2026"


def pedir_link(client, email: str, ip: str = "127.0.0.1"):
    """Envia o formulário "esqueci minha senha"."""
    return client.post(reverse("contas:esqueci"), {"email": email}, REMOTE_ADDR=ip)


def link_do_email() -> str:
    """Caminho do link de redefinição no último e-mail."""
    return re.search(r"https?://[^/\s]+(/entrar/redefinir/\S+)", mail.outbox[-1].body).group(1)


def redefinir(client, link: str, senha: str = SENHA_NOVA):
    """Abre o link (o Django troca o token pela sessão) e envia a nova senha."""
    pagina = client.get(link, follow=True)
    return client.post(pagina.redirect_chain[-1][0], {"new_password1": senha, "new_password2": senha})


@pytest.fixture
def cliente(criar_anunciante):
    """Anunciante ativo."""
    return criar_anunciante("loja@exemplo.com", "Loja Ativa")


def test_link_por_email_troca_a_senha(client, cliente):
    """Pede o link, abre, cria a senha nova: a nova entra e a antiga não."""
    resposta = pedir_link(client, "Loja@Exemplo.com")
    assert resposta["Location"] == reverse("contas:esqueci_enviado")
    assert len(mail.outbox) == 1 and mail.outbox[0].subject.startswith("Crie uma nova senha")

    resposta = redefinir(client, link_do_email())

    assert resposta["Location"] == reverse("contas:redefinir_concluido")
    cliente.usuario.refresh_from_db()
    assert cliente.usuario.check_password(SENHA_NOVA) and not cliente.usuario.check_password(SENHA)


def test_link_e_de_uso_unico(client, cliente):
    """Depois de usado, o mesmo link mostra "inválido ou já usado"."""
    pedir_link(client, "loja@exemplo.com")
    link = link_do_email()
    redefinir(client, link)

    pagina = Client().get(link, follow=True)

    assert "Link inválido ou já usado" in pagina.content.decode()


def test_trocar_a_senha_encerra_as_outras_sessoes(client, cliente):
    """Um celular logado antes da troca perde a sessão."""
    celular = Client()
    celular.force_login(cliente.usuario)
    assert celular.get(reverse("anunciantes:painel")).status_code == 200

    pedir_link(client, "loja@exemplo.com")
    redefinir(client, link_do_email())

    assert celular.get(reverse("anunciantes:painel")).status_code == 302  # volta para /entrar/


def test_troca_de_senha_libera_o_bloqueio_do_axes(client, cliente):
    """Quem foi bloqueado por errar a senha volta a entrar depois de criar uma nova."""
    for _ in range(5):
        client.post(reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": "errada"})
    assert (
        client.post(reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": SENHA}).status_code
        == 429
    )

    pedir_link(client, "loja@exemplo.com")
    redefinir(client, link_do_email())

    resposta = client.post(reverse("contas:entrar"), {"username": "loja@exemplo.com", "password": SENHA_NOVA})
    assert resposta["Location"] == reverse("anunciantes:painel")


@pytest.mark.parametrize("email", ["ninguem@exemplo.com", "daniel@exemplo.com"])
def test_email_desconhecido_ou_da_equipe_nao_recebe_link(client, cliente, email):
    """Mesma resposta para todos (não revela quem tem conta); equipe não recebe link público."""
    Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")

    resposta = pedir_link(client, email)

    assert resposta["Location"] == reverse("contas:esqueci_enviado")
    assert not mail.outbox


def test_limite_por_ip_no_esqueci(client, cliente, settings):
    """Muitos pedidos do mesmo IP: 429."""
    settings.LIMITE_PEDIDOS_EMAIL_POR_HORA = 2
    pedir_link(client, "ninguem@exemplo.com")
    pedir_link(client, "ninguem@exemplo.com")

    assert pedir_link(client, "loja@exemplo.com").status_code == 429
    assert not mail.outbox


def test_entrar_tem_link_para_esqueci_e_cadastro(client, db):
    """A tela de login leva ao "esqueci minha senha" e ao cadastro."""
    html = client.get(reverse("contas:entrar")).content.decode()

    assert reverse("contas:esqueci") in html and reverse("anunciantes:cadastro") in html
