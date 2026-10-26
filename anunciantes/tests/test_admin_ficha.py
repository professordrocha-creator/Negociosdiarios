"""Testes da ficha do Anunciante no admin (lote 3A): a equipe envia ou troca logo e capa (mesma validação e o
mesmo processamento do painel da loja), vê o plano e a situação da assinatura (com o link) e a situação da
confiança, com as ações Retirar/Devolver confiança."""

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from anunciantes.tests.test_pagina_loja import envio, imagem
from contas.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_logado(client, entrar_no_admin, db):
    """Superusuário logado e verificado no admin."""
    entrar_no_admin(Usuario.objects.create_superuser(email="d@exemplo.com", password=SENHA, nome="D"))
    return client


def dados_da_ficha(anunciante: Anunciante, **extra) -> dict:
    """POST da ficha com os valores atuais (os campos editáveis do admin)."""
    return {
        "usuario": anunciante.usuario_id,
        "tipo": anunciante.tipo,
        "nome_publico": anunciante.nome_publico,
        "slug": anunciante.slug,
        "sigla": anunciante.sigla,
        "cor": anunciante.cor,
        "cidade": anunciante.cidade_id,
        "documento_tipo": anunciante.documento_tipo,
        "documento_numero": anunciante.documento_numero,
        "sobre": anunciante.sobre,
        "endereco_publico": anunciante.endereco_publico,
        "horario": anunciante.horario,
        "instagram": anunciante.instagram,
        "site": anunciante.site,
        "whatsapp": "(65) 99999-0001",
        "email_publico": anunciante.email_publico,
        **extra,
    }


def test_ficha_mostra_envio_plano_e_confianca(admin_logado, loja):
    """Campos "Trocar o logo/capa", plano e assinatura (só leitura, com link) e a situação da confiança."""
    anunciante = loja()
    pagina = admin_logado.get(
        reverse("admin:anunciantes_anunciante_change", args=[anunciante.pk])
    ).content.decode()

    assert 'name="logo_envio"' in pagina and 'name="capa_envio"' in pagina
    assert "Básico" in pagina and "abrir a assinatura" in pagina and "/planos/assinatura/" in pagina
    assert "Com confiança: os anúncios novos publicam direto." in pagina


def test_equipe_envia_logo_pela_ficha(admin_logado, loja):
    """Logo enviado pela ficha: validado e processado como no painel (WebP 400 e 96 px, original apagado)."""
    anunciante = loja()
    url = reverse("admin:anunciantes_anunciante_change", args=[anunciante.pk])

    resposta = admin_logado.post(
        url, dados_da_ficha(anunciante, logo_envio=envio("logo.png", imagem(600, 600)))
    )

    assert resposta.status_code == 302, resposta.content.decode()[:3000]
    anunciante.refresh_from_db()
    assert anunciante.logo.name.endswith(".webp") and anunciante.logo_mini and not anunciante.logo_original


def test_ficha_recusa_logo_pequeno_como_o_painel(admin_logado, loja):
    """Abaixo do lado mínimo da Configuração: erro no campo e nada muda."""
    anunciante = loja()
    url = reverse("admin:anunciantes_anunciante_change", args=[anunciante.pk])

    resposta = admin_logado.post(
        url, dados_da_ficha(anunciante, logo_envio=envio("logo.png", imagem(50, 50)))
    )

    assert resposta.status_code == 200
    anunciante.refresh_from_db()
    assert not anunciante.logo and not anunciante.logo_original


def test_acoes_retirar_e_devolver_confianca(admin_logado, loja):
    """Retirar pede motivo e grava a data; Devolver limpa."""
    anunciante = loja()
    lista = reverse("admin:anunciantes_anunciante_changelist")

    admin_logado.post(
        lista,
        {
            "action": "retirar_confianca_selecionados",
            ACTION_CHECKBOX_NAME: [anunciante.pk],
            "aplicar": "1",
            "motivo": "Muitas reclamações.",
        },
    )
    anunciante.refresh_from_db()
    assert anunciante.confianca_retirada_em and anunciante.motivo_confianca == "Muitas reclamações."

    admin_logado.post(
        lista,
        {"action": "devolver_confianca_selecionados", ACTION_CHECKBOX_NAME: [anunciante.pk], "aplicar": "1"},
    )
    anunciante.refresh_from_db()
    assert anunciante.confianca_retirada_em is None
