"""Testes do admin de usuários e do login no admin por e-mail."""

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from config.settings import normalizar_admin_url
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
def test_paginas_do_admin_de_usuario_abrem(client, entrar_no_admin, superusuario, rota):
    """Lista e formulário de criação de usuário abrem sem erro."""
    entrar_no_admin(superusuario)

    assert client.get(reverse(rota)).status_code == 200


def test_pagina_de_edicao_abre(client, entrar_no_admin, superusuario):
    """Formulário de edição de usuário abre sem erro."""
    entrar_no_admin(superusuario)

    resposta = client.get(reverse("admin:contas_usuario_change", args=[superusuario.pk]))

    assert resposta.status_code == 200


def test_criar_usuario_pelo_admin(client, entrar_no_admin, superusuario):
    """Criar usuário pelo admin grava o e-mail normalizado e a senha em Argon2."""
    entrar_no_admin(superusuario)

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


def test_admin_recusa_email_duplicado_com_outra_caixa(client, entrar_no_admin, superusuario):
    """O admin mostra erro amigável (e não erro 500) para e-mail já cadastrado."""
    entrar_no_admin(superusuario)

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


# --- Endereço secreto do admin ------------------------------------------------


def test_admin_padrao_da_404(client):
    """/admin/ não existe: o admin mora em ADMIN_URL (do .env)."""
    assert client.get("/admin/").status_code == 404
    assert client.get("/admin/login/").status_code == 404


def test_admin_fica_no_endereco_do_env():
    """As rotas do admin usam o caminho configurado em ADMIN_URL."""
    assert reverse("admin:index") == f"/{settings.ADMIN_URL}"
    assert settings.ADMIN_URL != "admin/"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("painel-abc123", "painel-abc123/"), ("/painel-abc123/", "painel-abc123/"), ("a/b-c_d", "a/b-c_d/")],
)
def test_normalizar_admin_url_aceita_caminhos_validos(valor, esperado):
    """Barras nas pontas são opcionais; o resultado termina sempre com uma barra."""
    assert normalizar_admin_url(valor) == esperado


@pytest.mark.parametrize("valor", ["", "/", "admin", "/Admin/", "painel abc", "painel<int:x>", "painel.php"])
def test_normalizar_admin_url_recusa_valores_ruins(valor):
    """Vazio, "admin" e caracteres que não são de caminho simples derrubam a subida do Django."""
    with pytest.raises(ImproperlyConfigured):
        normalizar_admin_url(valor)


# --- Grupo Administrador não vira superusuário ----------------------------------


@pytest.fixture
def membro_administrador():
    """Usuário da equipe no grupo Administrador (sem ser superusuário)."""
    usuario = Usuario.objects.create_user(email="ajudante@exemplo.com", password=SENHA, nome="Ajudante")
    usuario.is_staff = True
    usuario.save()
    usuario.groups.add(Group.objects.get(name="Administrador"))
    return usuario


def test_administrador_nao_se_promove_a_superusuario(client, entrar_no_admin, membro_administrador):
    """Mesmo podendo editar usuários, quem não é superusuário não liga is_superuser (campo só leitura)."""
    entrar_no_admin(membro_administrador)
    url = reverse("admin:contas_usuario_change", args=[membro_administrador.pk])

    resposta = client.post(
        url,
        {
            "email": membro_administrador.email,
            "nome": "Ajudante",
            "is_active": "on",
            "is_staff": "on",
            "is_superuser": "on",
            "groups": [Group.objects.get(name="Administrador").pk],
        },
    )

    assert resposta.status_code == 302
    membro_administrador.refresh_from_db()
    assert not membro_administrador.is_superuser


def test_administrador_nao_edita_conta_de_superusuario(
    client, entrar_no_admin, membro_administrador, superusuario
):
    """A conta do superusuário (inclusive a troca de senha) fica fora do alcance do grupo Administrador."""
    entrar_no_admin(membro_administrador)
    dados = {"email": "invasor@exemplo.com", "nome": "Invasor", "is_active": "on", "is_staff": "on"}

    # Pode ver (view_usuario), mas salvar e trocar a senha são recusados.
    assert (
        client.post(reverse("admin:contas_usuario_change", args=[superusuario.pk]), dados).status_code == 403
    )
    assert client.get(reverse("admin:auth_user_password_change", args=[superusuario.pk])).status_code == 403
    superusuario.refresh_from_db()
    assert superusuario.email == "admin@exemplo.com"
