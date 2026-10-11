"""Testes do Celery (tarefa de exemplo, agenda) e do e-mail pela fila."""

from smtplib import SMTPException

import pytest
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.core.management import call_command

from core.services import email_para_fila
from core.tasks import batimento, enviar_email


@pytest.fixture
def email_pela_fila(settings):
    """Backend de produção (fila do Celery); o envio "real" cai em mail.outbox."""
    settings.EMAIL_BACKEND = "core.email.CeleryEmailBackend"
    settings.EMAIL_BACKEND_REAL = "django.core.mail.backends.locmem.EmailBackend"


# --- Tarefa de exemplo e agenda ---------------------------------------------------------


def test_tarefa_de_exemplo_roda_e_devolve_a_hora():
    """A tarefa `batimento` roda pelo Celery e devolve a hora local (Cuiabá)."""
    hora = batimento.delay().get(timeout=5)

    assert hora.endswith("-04:00")


def test_agenda_do_beat_tem_a_tarefa_de_exemplo():
    """O beat agenda o batimento a cada 5 minutos."""
    agenda = settings.CELERY_BEAT_SCHEDULE["batimento"]

    assert agenda["task"] == "core.tasks.batimento"
    assert agenda["schedule"] == 5 * 60


def test_comando_testar_celery(capsys):
    """O comando dispara a tarefa e mostra que o worker respondeu."""
    call_command("testar_celery")

    assert "Celery funcionando" in capsys.readouterr().out


# --- E-mail sempre pela fila ---------------------------------------------------------------


def test_send_mail_coloca_na_fila_e_nao_envia_na_pagina(email_pela_fila, monkeypatch):
    """A página só enfileira: quem envia é a tarefa `enviar_email`, no worker."""
    na_fila = []
    monkeypatch.setattr("core.tasks.enviar_email.delay", lambda dados: na_fila.append(dados))

    enviados = send_mail("Assunto", "Corpo", "site@exemplo.com", ["ana@exemplo.com"])

    assert enviados == 1
    assert not mail.outbox  # nada saiu durante a "requisição"
    assert na_fila[0]["to"] == ["ana@exemplo.com"]


def test_email_completo_chega_igual_depois_da_fila(email_pela_fila):
    """Assunto, corpo, HTML, cópia, cópia oculta, responder-para e cabeçalhos sobrevivem à fila."""
    mensagem = EmailMultiAlternatives(
        "Assunto",
        "Texto",
        "site@exemplo.com",
        ["ana@exemplo.com"],
        cc=["bia@exemplo.com"],
        bcc=["oculto@exemplo.com"],
        reply_to=["contato@exemplo.com"],
        headers={"X-Teste": "1"},
    )
    mensagem.attach_alternative("<p>Texto</p>", "text/html")

    mensagem.send()

    enviado = mail.outbox[0]
    assert (enviado.subject, enviado.body, enviado.from_email) == ("Assunto", "Texto", "site@exemplo.com")
    assert (enviado.to, enviado.cc, enviado.bcc) == (
        ["ana@exemplo.com"],
        ["bia@exemplo.com"],
        ["oculto@exemplo.com"],
    )
    assert enviado.reply_to == ["contato@exemplo.com"]
    assert enviado.extra_headers == {"X-Teste": "1"}
    assert list(enviado.alternatives[0]) == ["<p>Texto</p>", "text/html"]


def test_remetente_padrao_vem_do_settings(email_pela_fila):
    """Sem remetente, usa DEFAULT_FROM_EMAIL (configurável pelo .env)."""
    send_mail("Assunto", "Corpo", None, ["ana@exemplo.com"])

    assert mail.outbox[0].from_email == settings.DEFAULT_FROM_EMAIL


def test_anexo_ainda_nao_e_aceito_na_fila():
    """Anexo daria erro silencioso na fila; melhor recusar claramente."""
    mensagem = EmailMessage("Assunto", "Corpo", "site@exemplo.com", ["ana@exemplo.com"])
    mensagem.attach("a.txt", "conteúdo", "text/plain")

    with pytest.raises(ValueError, match="anexo"):
        email_para_fila(mensagem)


def test_fila_fora_do_ar_sobe_erro_ou_silencia(email_pela_fila, monkeypatch):
    """Redis fora: o erro sobe para quem chamou avisar; com fail_silently, só devolve 0."""

    def fila_fora(*args, **kwargs):
        raise ConnectionError("redis fora do ar")

    monkeypatch.setattr("core.tasks.enviar_email.delay", fila_fora)

    with pytest.raises(ConnectionError):
        send_mail("Assunto", "Corpo", None, ["ana@exemplo.com"])
    assert send_mail("Assunto", "Corpo", None, ["ana@exemplo.com"], fail_silently=True) == 0


def test_envio_tenta_de_novo_se_o_servidor_de_email_falhar():
    """Falha de SMTP ou de rede: tenta de novo 5 vezes (30 s, 1, 2, 4 e 8 min), ~15 min no total."""
    assert SMTPException in enviar_email.autoretry_for
    assert OSError in enviar_email.autoretry_for
    assert enviar_email.max_retries == 5
    assert enviar_email.retry_backoff == 30
