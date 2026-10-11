"""Testes do modelo Usuario: criação, e-mail normalizado e senha em Argon2."""

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.db import IntegrityError

from contas.models import Usuario
from contas.services import normalizar_email

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
SENHA_ERRADA = "errada"


def test_modelo_de_usuario_do_projeto_e_o_do_app_contas():
    """O Django usa o nosso Usuario (AUTH_USER_MODEL), não o User padrão."""
    assert get_user_model() is Usuario


def test_normalizar_email_tira_espacos_e_maiusculas():
    """'  Maria@Exemplo.COM ' vira 'maria@exemplo.com'."""
    assert normalizar_email("  Maria@Exemplo.COM ") == "maria@exemplo.com"


def test_create_user_sem_username_e_com_email_normalizado():
    """Usuário comum nasce ativo, fora da equipe e com e-mail em minúsculas."""
    usuario = Usuario.objects.create_user(email="Maria@Exemplo.com", password=SENHA, nome="Maria")

    assert usuario.email == "maria@exemplo.com"
    assert usuario.is_active
    assert not usuario.is_staff
    assert not usuario.is_superuser
    assert not hasattr(usuario, "username")


def test_create_user_exige_email():
    """Sem e-mail não há conta."""
    with pytest.raises(ValueError, match="e-mail"):
        Usuario.objects.create_user(email="", password=SENHA, nome="Sem Email")


def test_senha_guardada_com_argon2():
    """A senha nunca é guardada em texto; o hash usa Argon2."""
    usuario = Usuario.objects.create_user(email="a@exemplo.com", password=SENHA, nome="A")

    assert usuario.password.startswith("argon2")
    assert SENHA not in usuario.password
    assert usuario.check_password(SENHA)


def test_create_user_sem_senha_gera_senha_inutilizavel():
    """Conta sem senha não entra por senha (útil para convites e contas criadas pelo admin)."""
    usuario = Usuario.objects.create_user(email="b@exemplo.com", nome="B")

    assert not usuario.has_usable_password()


def test_email_duplicado_com_outra_caixa_e_recusado():
    """'joao@x.com' e 'JOAO@x.com' são a mesma conta: a segunda é recusada pelo banco."""
    Usuario.objects.create_user(email="joao@exemplo.com", password=SENHA, nome="João")

    with pytest.raises(IntegrityError):
        Usuario.objects.create_user(email="JOAO@Exemplo.com", password=SENHA, nome="Outro")


def test_save_direto_tambem_normaliza_email():
    """Mesmo salvando sem o manager (ex.: shell, importação), o e-mail fica normalizado."""
    usuario = Usuario(email=" Pedro@Exemplo.com", nome="Pedro")
    usuario.save()

    usuario.refresh_from_db()
    assert usuario.email == "pedro@exemplo.com"


def test_create_superuser_tem_acesso_total():
    """Superusuário nasce com is_staff e is_superuser."""
    admin = Usuario.objects.create_superuser(email="admin@exemplo.com", password=SENHA, nome="Admin")

    assert admin.is_staff
    assert admin.is_superuser


def test_create_superuser_recusa_flags_inconsistentes():
    """Não dá para criar 'superusuário' fora da equipe."""
    with pytest.raises(ValueError):
        Usuario.objects.create_superuser(email="x@exemplo.com", password=SENHA, nome="X", is_staff=False)


def test_login_por_email_ignora_maiusculas(rf):
    """authenticate() aceita o e-mail com qualquer caixa (o axes exige a requisição)."""
    Usuario.objects.create_user(email="ana@exemplo.com", password=SENHA, nome="Ana Paula")

    assert authenticate(rf.post("/"), username="ANA@Exemplo.com", password=SENHA) is not None
    assert authenticate(rf.post("/"), username="ana@exemplo.com", password=SENHA_ERRADA) is None


def test_usuario_inativo_nao_entra(rf):
    """Conta bloqueada (is_active=False) não autentica, mesmo com a senha certa."""
    Usuario.objects.create_user(email="bloq@exemplo.com", password=SENHA, nome="Bloqueado", is_active=False)

    assert authenticate(rf.post("/"), username="bloq@exemplo.com", password=SENHA) is None


def test_nomes_curto_e_completo():
    """get_short_name devolve o primeiro nome; __str__ devolve o e-mail."""
    usuario = Usuario(email="ana@exemplo.com", nome="Ana Paula Souza")

    assert usuario.get_full_name() == "Ana Paula Souza"
    assert usuario.get_short_name() == "Ana"
    assert str(usuario) == "ana@exemplo.com"


def test_comando_createsuperuser_usa_email_e_nome(monkeypatch):
    """`manage.py createsuperuser` funciona com e-mail e nome (sem username)."""
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", SENHA)

    call_command("createsuperuser", interactive=False, email="Dono@Exemplo.com", nome="Dono", verbosity=0)

    dono = Usuario.objects.get(email="dono@exemplo.com")
    assert dono.is_superuser
    assert dono.check_password(SENHA)
