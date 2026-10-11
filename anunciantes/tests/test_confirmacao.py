"""Testes da confirmação de e-mail (48 h, uso único) e dos e-mails de aprovação e suspensão."""

import re
import time

import pytest
from django.core import mail
from django.urls import reverse

from anunciantes.models import Anunciante
from anunciantes.services import aprovar, link_confirmacao, suspender
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def pendente(criar_anunciante):
    """Loja recém-cadastrada: pendente e com e-mail ainda não confirmado."""
    return criar_anunciante(
        "nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE, sem_confirmacao=True
    )


@pytest.fixture
def equipe(db):
    """Superusuário (recebe o aviso de novo cadastro)."""
    return Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")


def caminho(link: str) -> str:
    """Tira o domínio do link absoluto (SITE_URL) para usar no client."""
    return re.sub(r"^https?://[^/]+", "", link)


# --- Confirmação -------------------------------------------------------------------------


def test_link_confirma_e_avisa_a_equipe(client, pendente, equipe):
    """Clique no link: e-mail confirmado e a equipe recebe "novo cadastro aguardando aprovação"."""
    resposta = client.get(caminho(link_confirmacao(pendente.usuario)))

    assert resposta.status_code == 200 and "E-mail confirmado" in resposta.content.decode()
    pendente.usuario.refresh_from_db()
    assert pendente.usuario.email_confirmado_em is not None
    aviso = mail.outbox[-1]
    assert aviso.subject.startswith("Novo cadastro aguardando aprovação")
    assert aviso.to == ["daniel@exemplo.com"]
    assert (
        "Loja Nova" in aviso.body
        and reverse("admin:anunciantes_anunciante_change", args=[pendente.pk]) in aviso.body
    )


def test_link_e_de_uso_unico(client, pendente, equipe):
    """Usado uma vez, o mesmo link só informa que já foi confirmado (sem novo aviso à equipe)."""
    link = caminho(link_confirmacao(pendente.usuario))
    client.get(link)
    mail.outbox.clear()

    resposta = client.get(link)

    assert "já foi confirmado" in resposta.content.decode()
    assert not mail.outbox


def test_link_vencido_nao_confirma(client, pendente, monkeypatch, settings):
    """Depois de 48 h o link não vale: a tela oferece pedir outro."""
    link = caminho(link_confirmacao(pendente.usuario))
    agora = time.time()
    monkeypatch.setattr(
        "django.core.signing.time.time", lambda: agora + (settings.CONFIRMACAO_EMAIL_HORAS + 1) * 3600
    )

    resposta = client.get(link)

    assert resposta.status_code == 400
    assert "Este link venceu" in resposta.content.decode()
    pendente.usuario.refresh_from_db()
    assert pendente.usuario.email_confirmado_em is None


def test_link_adulterado_nao_confirma(client, pendente):
    """Token alterado: "Link inválido"."""
    link = caminho(link_confirmacao(pendente.usuario))

    resposta = client.get(link.replace(link.rstrip("/").rsplit("/", 1)[1], "abc:def:ghi"))

    assert resposta.status_code == 400 and "Link inválido" in resposta.content.decode()


def test_reenviar_confirmacao(client, pendente):
    """Link novo para quem não confirmou; e-mail desconhecido: mesma tela e nada sai."""
    resposta = client.post(reverse("anunciantes:reenviar_confirmacao"), {"email": "NOVA@exemplo.com"})
    assert "Pedido recebido" in resposta.content.decode()
    assert len(mail.outbox) == 1 and mail.outbox[0].subject.startswith("Confirme seu e-mail")

    mail.outbox.clear()
    resposta = client.post(reverse("anunciantes:reenviar_confirmacao"), {"email": "ninguem@exemplo.com"})
    assert "Pedido recebido" in resposta.content.decode()
    assert not mail.outbox


def test_sem_confirmar_nao_entra_e_nao_aparece_para_aprovacao(client, pendente, equipe, entrar_no_admin):
    """Login avisa que falta confirmar; no admin, não está em "aguardando aprovação" e não é aprovado."""
    resposta = client.post(reverse("contas:entrar"), {"username": "nova@exemplo.com", "password": SENHA})
    assert "Falta confirmar o seu e-mail" in resposta.content.decode()

    entrar_no_admin(equipe)
    lista = reverse("admin:anunciantes_anunciante_changelist")
    assert "Loja Nova" not in client.get(lista, {"aprovacao": "aguardando"}).content.decode()
    assert "Loja Nova" in client.get(lista, {"aprovacao": "sem_confirmacao"}).content.decode()

    with pytest.raises(ValueError, match="não foi confirmado"):
        aprovar(pendente, equipe)


def test_depois_de_confirmar_aparece_para_aprovacao(client, pendente, equipe, entrar_no_admin):
    """Confirmado o e-mail, a loja entra no filtro "Aguardando aprovação"."""
    client.get(caminho(link_confirmacao(pendente.usuario)))
    entrar_no_admin(equipe)

    html = client.get(
        reverse("admin:anunciantes_anunciante_changelist"), {"aprovacao": "aguardando"}
    ).content.decode()

    assert "Loja Nova" in html


# --- E-mails de aprovação e suspensão ----------------------------------------------------


def test_aprovacao_envia_email_com_link_para_entrar(criar_anunciante, equipe, settings):
    """ "Sua loja foi aprovada", com o link absoluto de /entrar/."""
    loja = criar_anunciante("loja@exemplo.com", "Loja Boa", status=Anunciante.Status.PENDENTE)

    aprovar(loja, equipe, "Ok")

    email = mail.outbox[-1]
    assert email.subject.startswith("Sua loja foi aprovada") and email.to == ["loja@exemplo.com"]
    assert settings.SITE_URL + reverse("contas:entrar") in email.body


def test_aprovar_pelo_admin_dispara_o_email(client, equipe, entrar_no_admin, criar_anunciante):
    """A ação do admin aprova e o e-mail sai."""
    from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME

    loja = criar_anunciante("loja@exemplo.com", "Loja Boa", status=Anunciante.Status.PENDENTE)
    entrar_no_admin(equipe)

    client.post(
        reverse("admin:anunciantes_anunciante_changelist"),
        {"action": "aprovar_selecionados", ACTION_CHECKBOX_NAME: [loja.pk], "aplicar": "1", "motivo": ""},
    )

    assert any(m.subject.startswith("Sua loja foi aprovada") for m in mail.outbox)


def test_suspensao_envia_email_com_o_motivo(criar_anunciante, equipe):
    """ "Sua loja foi suspensa", com o motivo escrito pela equipe."""
    loja = criar_anunciante("loja@exemplo.com", "Loja X")

    suspender(loja, equipe, "Fotos de outro anunciante.")

    email = mail.outbox[-1]
    assert email.subject.startswith("Sua loja foi suspensa")
    assert "Fotos de outro anunciante." in email.body
