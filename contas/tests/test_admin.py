"""Testes do admin de usuários e do login no admin por e-mail."""

import pytest
from django.urls import reverse

from contas.models import Usuario

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
SENHA_NOVA = "Outra-Senha-Forte-456"


@pytest.fixture
def superusuario():
    """Superusuário de teste."""
    return Usuario.objects.create_superuser(email="admin@exemplo.com", password=SENHA, nome="Admin")


def test_login_no_admin_com_email(client, superusuario):
    """O formulário de login do admin aceita o e-mail (em qualquer caixa) e leva ao painel."""
    resposta = client.post(
        reverse("admin:login"),
        {"username": "Admin@Exemplo.com", "password": SENHA, "next": reverse("admin:index")},
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("admin:index")


def test_usuario_fora_da_equipe_nao_entra_no_admin(client):
    """Usuário comum (anunciante) com senha certa não acessa o admin."""
    Usuario.objects.create_user(email="anunciante@exemplo.com", password=SENHA, nome="Anunciante")

    resposta = client.post(
        reverse("admin:login"),
        {"username": "anunciante@exemplo.com", "password": SENHA, "next": reverse("admin:index")},
    )

    assert resposta.status_code == 200  # volta para o formulário com erro
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("rota", ["admin:contas_usuario_changelist", "admin:contas_usuario_add"])
def test_paginas_do_admin_de_usuario_abrem(client, superusuario, rota):
    """Lista e formulário de criação de usuário abrem sem erro."""
    client.force_login(superusuario)

    assert client.get(reverse(rota)).status_code == 200


def test_pagina_de_edicao_abre(client, superusuario):
    """Formulário de edição de usuário abre sem erro."""
    client.force_login(superusuario)

    resposta = client.get(reverse("admin:contas_usuario_change", args=[superusuario.pk]))

    assert resposta.status_code == 200


def test_criar_usuario_pelo_admin(client, superusuario):
    """Criar usuário pelo admin grava o e-mail normalizado e a senha em Argon2."""
    client.force_login(superusuario)

    resposta = client.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "Novo@Exemplo.com",
            "nome": "Novo Usuário",
            "usable_password": "true",
            "password1": SENHA_NOVA,
            "password2": SENHA_NOVA,
        },
    )

    assert resposta.status_code == 302
    novo = Usuario.objects.get(email="novo@exemplo.com")
    assert novo.password.startswith("argon2")
    assert not novo.is_staff


def test_admin_recusa_email_duplicado_com_outra_caixa(client, superusuario):
    """O admin mostra erro amigável (e não erro 500) para e-mail já cadastrado."""
    client.force_login(superusuario)

    resposta = client.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "ADMIN@exemplo.com",
            "nome": "Duplicado",
            "usable_password": "true",
            "password1": SENHA_NOVA,
            "password2": SENHA_NOVA,
        },
    )

    assert resposta.status_code == 200
    assert "Já existe uma conta com este e-mail." in resposta.content.decode()
    assert Usuario.objects.count() == 1
