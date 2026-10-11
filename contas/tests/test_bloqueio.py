"""Testes do bloqueio de tentativas (django-axes): 5 senhas erradas bloqueiam; o desbloqueio funciona."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from contas.models import Usuario
from contas.services import redefinir_acesso

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
EMAIL = "daniel@exemplo.com"


@pytest.fixture
def equipe():
    """Superusuário de teste."""
    return Usuario.objects.create_superuser(email=EMAIL, password=SENHA, nome="Daniel")


def entrar(client, senha: str, email: str = EMAIL, ip: str = "127.0.0.1"):
    """Envia o formulário de login do admin a partir de um IP."""
    return client.post(
        reverse("admin:login"),
        {"username": email, "password": senha, "next": reverse("admin:index")},
        REMOTE_ADDR=ip,
    )


def errar(client, vezes: int, **kwargs):
    """Erra a senha `vezes` vezes e devolve a última resposta."""
    resposta = None
    for _ in range(vezes):
        resposta = entrar(client, senha="senha-errada", **kwargs)
    return resposta


def test_quatro_erros_ainda_deixam_entrar(client, equipe):
    """Abaixo do limite (5), a senha certa entra normalmente."""
    errar(client, 4)

    resposta = entrar(client, senha=SENHA)

    assert resposta.status_code == 302
    assert "_auth_user_id" in client.session


def test_quinto_erro_bloqueia_e_nem_a_senha_certa_entra(client, equipe):
    """Na 5ª senha errada vem a página de bloqueio (429); depois disso nem a senha certa passa."""
    resposta = errar(client, 5)

    assert resposta.status_code == 429
    assert "Acesso bloqueado temporariamente" in resposta.content.decode()

    resposta = entrar(client, senha=SENHA)

    assert resposta.status_code == 429
    assert "_auth_user_id" not in client.session


def test_maiusculas_no_email_nao_dao_tentativas_extras(client, equipe):
    """Maiúsculas no e-mail contam junto: o e-mail é normalizado antes de contar."""
    errar(client, 3, email="DANIEL@Exemplo.com")
    resposta = errar(client, 2, email=EMAIL)

    assert resposta.status_code == 429


def test_bloqueio_nao_afeta_o_mesmo_email_em_outro_ip(client, equipe):
    """Quem erra de outro lugar não tranca o dono da conta (bloqueio é por e-mail + IP)."""
    errar(client, 5, ip="203.0.113.9")

    resposta = entrar(client, senha=SENHA, ip="198.51.100.7")

    assert resposta.status_code == 302


def test_desbloqueio_pelo_comando_do_axes(client, equipe):
    """`axes_reset_username <email>` (docs/RUNBOOK.md) libera o login na hora."""
    errar(client, 5)

    call_command("axes_reset_username", EMAIL)
    resposta = entrar(client, senha=SENHA)

    assert resposta.status_code == 302
    assert "_auth_user_id" in client.session


def test_redefinir_acesso_tambem_desbloqueia(client, equipe):
    """O procedimento de emergência zera o bloqueio."""
    errar(client, 5)

    redefinir_acesso(equipe)
    resposta = entrar(client, senha=SENHA)

    assert resposta.status_code == 302
