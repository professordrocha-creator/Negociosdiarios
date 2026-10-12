"""Testes das telas da cobrança: Painel › Faturas (Pix, "Já paguei", comprovante, IDOR, CSP) e o admin
(painel de cobrança, ações confirmar/recusar, comprovante só para quem pode ver faturas)."""

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.urls import reverse

from pagamentos import pix
from pagamentos.models import Fatura
from pagamentos.services import confirmar_pagamento, enviar_comprovante
from pagamentos.tests.conftest import PDF_SIMPLES, envio, imagem

pytestmark = pytest.mark.django_db


def entrar(client, fatura):
    """Loga como o dono da loja da fatura."""
    client.force_login(fatura.assinatura.anunciante.usuario)
    return client


# --- Painel › Faturas --------------------------------------------------------------------------


def test_faturas_exige_login(client):
    """Anônimo vai para o login."""
    resposta = client.get(reverse("pagamentos:faturas"))
    assert resposta.status_code == 302 and reverse("contas:entrar") in resposta["Location"]


def test_fatura_aberta_com_pix_qr_code_e_copiar(client, com_fatura, settings):
    """Valor, vencimento, QR Code e o copia e cola com o valor e o identificador da fatura."""
    fatura = com_fatura()
    html = entrar(client, fatura).get(reverse("pagamentos:faturas")).content.decode()

    esperado = pix.br_code(
        settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE, fatura.valor, fatura.codigo
    )
    assert esperado in html and 'src="data:image/svg+xml' in html
    assert "R$ 49,90" in html and f"{fatura.vencimento:%d/%m/%Y}" in html
    assert 'data-copiar="pix-' in html and "copiar.js" in html
    assert "Já paguei" in html
    assert "<script>" not in html and ' style="' not in html  # CSP: nada inline


def test_sem_pix_configurado_avisa_e_mostra_o_boleto(client, com_fatura, settings):
    """Sem PIX_* no .env: aviso e, se a equipe colou, o link do boleto."""
    settings.PIX_CHAVE = ""
    fatura = com_fatura()
    Fatura.objects.filter(pk=fatura.pk).update(link_boleto="https://banco.exemplo.com/boleto/123")
    html = entrar(client, fatura).get(reverse("pagamentos:faturas")).content.decode()

    assert "Pix ainda não está disponível" in html and "https://banco.exemplo.com/boleto/123" in html
    assert "data:image/svg+xml" not in html


def test_ja_paguei_envia_comprovante(client, com_fatura):
    """Envio válido: aguardando confirmação, mensagem e e-mail para a equipe."""
    fatura = com_fatura()
    mail.outbox.clear()
    resposta = entrar(client, fatura).post(
        reverse("pagamentos:ja_paguei", args=[fatura.codigo]),
        {"comprovante": envio("c.pdf", PDF_SIMPLES, "application/pdf"), "recado": "Pago às 9h"},
        follow=True,
    )

    fatura.refresh_from_db()
    assert fatura.situacao == Fatura.Situacao.AGUARDANDO
    html = resposta.content.decode()
    assert "Comprovante enviado!" in html and "Recebemos seu comprovante" in html
    assert len(mail.outbox) == 1


def test_ja_paguei_com_arquivo_invalido_mostra_o_erro(client, com_fatura):
    """Arquivo que não é imagem nem PDF: 400 com a mensagem no formulário da fatura (aberto)."""
    fatura = com_fatura()
    resposta = entrar(client, fatura).post(
        reverse("pagamentos:ja_paguei", args=[fatura.codigo]),
        {"comprovante": envio("c.png", b"nao e imagem")},
    )

    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert (
        "Envie o comprovante em PDF, JPG, PNG ou WebP." in html
        and '<details class="nd-ja-paguei" open' in html
    )
    fatura.refresh_from_db()
    assert fatura.situacao == Fatura.Situacao.ABERTA


def test_outra_loja_nao_ve_nem_envia(client, com_fatura):
    """IDOR: a fatura de outra loja dá 404 no envio e no comprovante, e não aparece na lista."""
    alheia = enviar_comprovante(com_fatura("a@exemplo.com", "Loja A"), envio("a.png", imagem()))
    minha = com_fatura("b@exemplo.com", "Loja B")
    entrar(client, minha)

    assert alheia.codigo not in client.get(reverse("pagamentos:faturas")).content.decode()
    assert client.get(reverse("pagamentos:comprovante", args=[alheia.codigo])).status_code == 404
    resposta = client.post(
        reverse("pagamentos:ja_paguei", args=[alheia.codigo]), {"comprovante": envio("b.png", imagem())}
    )
    assert resposta.status_code == 404


def test_comprovante_do_dono_com_cabecalhos_seguros(client, com_fatura):
    """O dono abre o próprio comprovante: tipo fixo, sem cache, nosniff e CSP sandbox."""
    fatura = enviar_comprovante(com_fatura(), envio("c.pdf", PDF_SIMPLES, "application/pdf"))
    resposta = entrar(client, fatura).get(reverse("pagamentos:comprovante", args=[fatura.codigo]))

    assert resposta.status_code == 200 and resposta.content == PDF_SIMPLES
    assert resposta["Content-Type"] == "application/pdf"
    assert resposta["Cache-Control"] == "private, no-store"
    assert resposta["X-Content-Type-Options"] == "nosniff"
    assert resposta["Content-Security-Policy"] == "sandbox"


def test_historico_e_menu(client, com_fatura):
    """Paga vai para o histórico; o menu do painel leva às Faturas."""
    fatura = confirmar_pagamento(com_fatura(), None)
    html = entrar(client, fatura).get(reverse("pagamentos:faturas")).content.decode()

    assert "Histórico" in html and fatura.codigo in html and "Nenhuma fatura em aberto" in html
    assert f'href="{reverse("pagamentos:faturas")}"' in html


def test_ja_paguei_em_fatura_paga_avisa(client, com_fatura):
    """Fatura já paga: não aceita comprovante (aviso, sem erro)."""
    fatura = confirmar_pagamento(com_fatura(), None)
    resposta = entrar(client, fatura).post(
        reverse("pagamentos:ja_paguei", args=[fatura.codigo]),
        {"comprovante": envio("a.png", imagem())},
        follow=True,
    )
    assert "não está esperando pagamento" in resposta.content.decode()


# --- Admin ----------------------------------------------------------------------------------


def test_painel_de_cobranca_so_para_quem_ve_faturas(entrar_no_admin, equipe, com_fatura):
    """Financeiro vê o painel; Moderador não vê faturas (ADMINISTRACAO.md)."""
    com_fatura()
    client = entrar_no_admin(equipe("Financeiro"))
    html = client.get(reverse("admin:pagamentos_fatura_painel")).content.decode()
    assert "Vencendo em 7 dias" in html and "Aguardando confirmação" in html and "R$ 49,90" in html

    client = entrar_no_admin(equipe("Moderador"))
    assert client.get(reverse("admin:pagamentos_fatura_painel")).status_code == 403
    assert client.get(reverse("admin:pagamentos_fatura_changelist")).status_code == 403


def test_admin_confirma_pagamento_com_forma(entrar_no_admin, equipe, com_fatura):
    """Ação "Confirmar pagamento": tela com a forma e, ao aplicar, a fatura fica paga."""
    financeiro = equipe("Financeiro")
    fatura = enviar_comprovante(com_fatura(), envio("a.png", imagem()))
    client = entrar_no_admin(financeiro)
    url = reverse("admin:pagamentos_fatura_changelist")
    dados = {"action": "confirmar_pagamento_acao", ACTION_CHECKBOX_NAME: [fatura.pk]}

    tela = client.post(url, dados)
    assert tela.status_code == 200 and "Forma de pagamento" in tela.content.decode()
    client.post(url, {**dados, "aplicar": "1", "forma": "transferencia", "observacao": "Extrato ok"})

    fatura.refresh_from_db()
    assert (fatura.situacao, fatura.forma, fatura.confirmado_por) == ("paga", "transferencia", financeiro)


def test_admin_recusa_comprovante_com_motivo(entrar_no_admin, equipe, com_fatura):
    """Recusar pede motivo; sem motivo nada muda."""
    fatura = enviar_comprovante(com_fatura(), envio("a.png", imagem()))
    client = entrar_no_admin(equipe("Financeiro"))
    url = reverse("admin:pagamentos_fatura_changelist")
    dados = {"action": "recusar_comprovante_acao", ACTION_CHECKBOX_NAME: [fatura.pk], "aplicar": "1"}

    client.post(url, {**dados, "motivo": ""})
    fatura.refresh_from_db()
    assert fatura.situacao == Fatura.Situacao.AGUARDANDO
    client.post(url, {**dados, "motivo": "Comprovante de outra loja"})
    fatura.refresh_from_db()
    assert (fatura.situacao, fatura.motivo_recusa) == ("aberta", "Comprovante de outra loja")


def test_admin_comprovante_e_ficha(entrar_no_admin, equipe, com_fatura):
    """Ficha com o link do comprovante (URL do admin); só quem vê faturas abre o arquivo."""
    fatura = enviar_comprovante(com_fatura(), envio("a.png", imagem()))
    url = reverse("admin:pagamentos_fatura_comprovante", args=[fatura.pk])
    client = entrar_no_admin(equipe("Financeiro"))

    assert url in client.get(reverse("admin:pagamentos_fatura_change", args=[fatura.pk])).content.decode()
    assert client.get(url).status_code == 200
    assert entrar_no_admin(equipe("Moderador")).get(url).status_code == 403


def test_admin_nao_cria_nem_apaga_fatura(entrar_no_admin, equipe):
    """Faturas nascem da rotina ou do pagamento manual; nunca se apagam."""
    client = entrar_no_admin(equipe("Administrador"))
    assert client.get(reverse("admin:pagamentos_fatura_add")).status_code == 403
    assert "delete_selected" not in client.get(reverse("admin:pagamentos_fatura_changelist")).content.decode()
