"""Testes do acesso ao admin: login com e-mail e senha, código por e-mail para navegador novo
(só em produção) e navegador confiável por 30 dias."""

import re
from datetime import timedelta
from smtplib import SMTPException

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_email.models import EmailDevice

from contas.models import Usuario
from contas.services import (
    COOKIE_NAVEGADOR_CONFIAVEL,
    enviar_codigo_email,
    redefinir_acesso,
    verificar_codigo,
)

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
EMAIL = "daniel@exemplo.com"


@pytest.fixture
def equipe():
    """Superusuário (como o Daniel)."""
    return Usuario.objects.create_superuser(email=EMAIL, password=SENHA, nome="Daniel")


@pytest.fixture
def producao(settings):
    """Produção com o código por e-mail ligado (o que vale depois da etapa 6)."""
    settings.DEBUG = False
    settings.ADMIN_CODIGO_EMAIL = True
    return settings


def entrar(client, email: str = EMAIL, senha: str = SENHA):
    """Envia o formulário de login do admin (só e-mail e senha)."""
    return client.post(
        reverse("admin:login"), {"username": email, "password": senha, "next": reverse("admin:index")}
    )


def codigo_do_ultimo_email() -> str:
    """Tira o código de 6 dígitos do último e-mail enviado."""
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


def confirmar(client, codigo: str, proximo: str | None = None):
    """Envia o código na tela "Confirme que é você"."""
    return client.post(
        reverse("admin:verificar"), {"codigo": codigo, "next": proximo or reverse("admin:index")}
    )


def painel_abre(client) -> bool:
    """Diz se o painel do admin abre para esta sessão."""
    return client.get(reverse("admin:index")).status_code == 200


# --- Liga/desliga ------------------------------------------------------------------------


def test_em_dev_tambem_pede_codigo_quando_ligado(client, equipe, settings):
    """Desde a etapa 6 o código vale em dev também (o e-mail cai no Mailpit)."""
    settings.DEBUG = True
    settings.ADMIN_CODIGO_EMAIL = True

    resposta = entrar(client)

    assert resposta["Location"].startswith(reverse("admin:verificar"))
    assert len(mail.outbox) == 1


def test_com_codigo_desligado_entra_so_com_senha(client, equipe, settings):
    """ADMIN_CODIGO_EMAIL=False (opção para dev): só e-mail e senha, nenhum e-mail enviado."""
    settings.DEBUG = True
    settings.ADMIN_CODIGO_EMAIL = False

    resposta = entrar(client)

    assert resposta["Location"] == reverse("admin:index")
    assert painel_abre(client)
    assert not mail.outbox


def test_codigo_do_login_passa_pela_fila_do_celery(client, equipe, producao):
    """Com o backend de produção (fila do Celery), o código chega do mesmo jeito."""
    producao.EMAIL_BACKEND = "core.email.CeleryEmailBackend"
    producao.EMAIL_BACKEND_REAL = "django.core.mail.backends.locmem.EmailBackend"

    entrar(client)

    assert len(mail.outbox) == 1
    assert re.search(r"\b\d{6}\b", mail.outbox[0].body)


def test_fila_fora_do_ar_avisa_na_tela(client, equipe, producao, monkeypatch):
    """Redis fora do ar: o código não sai, mas a tela avisa e o login não dá erro 500."""

    def fila_fora(*args, **kwargs):
        raise ConnectionError("redis fora do ar")

    producao.EMAIL_BACKEND = "core.email.CeleryEmailBackend"
    monkeypatch.setattr("core.tasks.enviar_email.delay", fila_fora)

    resposta = client.post(
        reverse("admin:login"),
        {"username": EMAIL, "password": SENHA, "next": reverse("admin:index")},
        follow=True,
    )

    assert resposta.status_code == 200
    assert "Não conseguimos enviar o e-mail agora" in resposta.content.decode()


def test_tela_de_login_tem_so_email_e_senha(client):
    """Nada de seletor de dispositivo nem campo de código no login."""
    html = client.get(reverse("admin:login")).content.decode()

    assert 'name="username"' in html and 'name="password"' in html
    assert "otp_device" not in html and "otp_token" not in html


# --- Navegador novo em produção: código por e-mail -------------------------------------


def test_navegador_novo_recebe_codigo_e_nao_ve_o_painel_antes(client, equipe, producao):
    """Senha certa num navegador novo: vai para a tela do código, com um e-mail de 6 dígitos."""
    resposta = entrar(client)

    assert resposta["Location"].startswith(reverse("admin:verificar"))
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [EMAIL]
    assert re.search(r"\b\d{6}\b", mail.outbox[0].body)
    assert not painel_abre(client)


def test_tela_do_codigo_mostra_email_mascarado(client, equipe, producao):
    """A tela diz para onde foi o código sem mostrar o e-mail inteiro."""
    entrar(client)

    html = client.get(reverse("admin:verificar")).content.decode()

    assert "d*****@exemplo.com" in html
    assert EMAIL not in html


def test_codigo_certo_libera_e_marca_navegador_por_30_dias(client, equipe, producao):
    """Código certo: painel abre e o navegador ganha o cookie seguro de 30 dias."""
    entrar(client)

    resposta = confirmar(client, codigo_do_ultimo_email())

    assert resposta["Location"] == reverse("admin:index")
    assert painel_abre(client)
    cookie = client.cookies[COOKIE_NAVEGADOR_CONFIAVEL]
    assert cookie["max-age"] == 30 * 24 * 60 * 60
    assert cookie["httponly"] and cookie["secure"]
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == f"/{producao.ADMIN_URL}"


def test_codigo_errado_nao_libera(client, equipe, producao):
    """Código que não foi enviado: continua na tela, com mensagem, sem acesso."""
    entrar(client)
    certo = codigo_do_ultimo_email()

    resposta = confirmar(client, "000000" if certo != "000000" else "111111")

    assert resposta.status_code == 200
    assert "Código errado, vencido ou já usado" in resposta.content.decode()
    assert not painel_abre(client)


def test_codigo_vale_uma_vez(equipe):
    """O mesmo código não serve duas vezes."""
    enviar_codigo_email(equipe)
    codigo = codigo_do_ultimo_email()

    assert verificar_codigo(equipe, codigo)
    assert not verificar_codigo(equipe, codigo)


def test_codigo_vence_em_10_minutos(equipe):
    """O código vale ADMIN_CODIGO_MINUTOS (10) minutos; vencido, é recusado."""
    enviar_codigo_email(equipe)
    dispositivo = EmailDevice.objects.get(user=equipe)
    restante = dispositivo.valid_until - timezone.now()
    assert timedelta(minutes=9) < restante <= timedelta(minutes=10)

    dispositivo.valid_until = timezone.now() - timedelta(seconds=1)
    dispositivo.save()

    assert not verificar_codigo(equipe, codigo_do_ultimo_email())


def test_reenviar_respeita_espera_de_1_minuto(client, equipe, producao):
    """Pedir outro código logo em seguida não manda outro e-mail; a tela pede para aguardar."""
    entrar(client)

    resposta = client.post(reverse("admin:verificar"), {"reenviar": "1"}, follow=True)

    assert len(mail.outbox) == 1
    assert "Aguarde 1 minuto" in resposta.content.decode()


def test_falha_no_envio_avisa_e_nao_quebra(client, equipe, producao, monkeypatch):
    """Servidor de e-mail fora do ar: a tela avisa e o login não dá erro 500."""

    def falhar(*args, **kwargs):
        raise SMTPException("fora do ar")

    monkeypatch.setattr(EmailDevice, "send_mail", falhar)

    resposta = client.post(
        reverse("admin:login"),
        {"username": EMAIL, "password": SENHA, "next": reverse("admin:index")},
        follow=True,
    )

    assert resposta.status_code == 200
    assert "Não conseguimos enviar o e-mail agora" in resposta.content.decode()
    assert not painel_abre(client)


def test_sessao_so_com_senha_nao_ve_o_painel(client, equipe, producao):
    """Logado só pela senha (sem a verificação), o painel não abre."""
    client.force_login(equipe)

    resposta = client.get(reverse("admin:index"))

    assert resposta.status_code == 302


def test_tela_do_codigo_sem_login_volta_ao_login(client, producao):
    """Ninguém chega à tela do código sem antes acertar a senha."""
    resposta = client.get(reverse("admin:verificar"))

    assert resposta["Location"] == reverse("admin:login")


def test_next_de_outro_site_e_ignorado(client, equipe, producao):
    """Depois do código, nunca redireciona para fora do site (open redirect)."""
    entrar(client)

    resposta = confirmar(client, codigo_do_ultimo_email(), proximo="https://site-malicioso.example/")

    assert resposta["Location"] == reverse("admin:index")


# --- Navegador confiável ---------------------------------------------------------------


@pytest.fixture
def navegador_confiavel(client, equipe, producao):
    """Navegador que já passou pelo código uma vez (e saiu)."""
    entrar(client)
    confirmar(client, codigo_do_ultimo_email())
    client.post(reverse("admin:logout"))
    mail.outbox.clear()
    return client


def test_navegador_confiavel_entra_so_com_senha(navegador_confiavel):
    """No mesmo navegador, dentro de 30 dias, não pede código de novo."""
    resposta = entrar(navegador_confiavel)

    assert resposta["Location"] == reverse("admin:index")
    assert painel_abre(navegador_confiavel)
    assert not mail.outbox


def test_outro_navegador_pede_codigo(navegador_confiavel):
    """Outro computador (sem o cookie) pede código, mesmo com a senha certa."""
    outro = Client()

    resposta = entrar(outro)

    assert resposta["Location"].startswith(reverse("admin:verificar"))
    assert len(mail.outbox) == 1


def test_trocar_a_senha_invalida_navegadores_confiaveis(navegador_confiavel, equipe):
    """Senha nova = todos os navegadores precisam do código de novo (ex.: notebook roubado)."""
    equipe.set_password("Outra-Senha-Forte-456")
    equipe.save()

    resposta = entrar(navegador_confiavel, senha="Outra-Senha-Forte-456")

    assert resposta["Location"].startswith(reverse("admin:verificar"))


def test_cookie_de_outro_usuario_nao_vale(navegador_confiavel):
    """O cookie é ligado ao usuário: não serve para outra conta da equipe."""
    Usuario.objects.create_superuser(email="ajudante@exemplo.com", password=SENHA, nome="Ajudante")

    resposta = entrar(navegador_confiavel, email="ajudante@exemplo.com")

    assert resposta["Location"].startswith(reverse("admin:verificar"))


def test_cookie_adulterado_nao_vale(client, equipe, producao):
    """Cookie inventado ou alterado não passa na assinatura."""
    client.cookies[COOKIE_NAVEGADOR_CONFIAVEL] = "inventado:123"

    resposta = entrar(client)

    assert resposta["Location"].startswith(reverse("admin:verificar"))


# --- Emergência pelo servidor ----------------------------------------------------------


def test_codigo_de_emergencia_entra_uma_vez(client, equipe, producao):
    """O código do `redefinir_acesso` serve na tela do código, uma única vez."""
    codigo = redefinir_acesso(equipe)
    entrar(client)

    confirmar(client, codigo)
    assert painel_abre(client)

    assert not verificar_codigo(equipe, codigo)


def test_comando_redefinir_acesso_mostra_o_codigo(equipe, capsys):
    """O comando imprime o código de emergência."""
    call_command("redefinir_acesso", "Daniel@Exemplo.com")

    saida = capsys.readouterr().out
    assert "Login desbloqueado." in saida
    assert re.search(r"Código de emergência \(uso único\): [a-z2-7]{8}", saida)


@pytest.mark.parametrize("email", ["ninguem@exemplo.com", "cliente@exemplo.com"])
def test_comando_redefinir_acesso_recusa_quem_nao_e_da_equipe(email):
    """E-mail inexistente ou usuário fora da equipe: erro claro."""
    Usuario.objects.create_user(email="cliente@exemplo.com", password=SENHA, nome="Cliente")

    with pytest.raises(CommandError):
        call_command("redefinir_acesso", email)
