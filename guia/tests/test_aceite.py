"""Testes do convite e do aceite (docs/GUIA.md §8 e §10; GUIA_LGPD_E_TERMO.md §2): link de uso único com
validade, página noindex e no-referrer com CSRF e limite por hora, registro do aceite e publicação, aceite em
papel (foto privada), revogação e o botão do WhatsApp no admin."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from guia import services
from guia.models import AceitePublicacao, ConviteAceite, PerfilGuia

pytestmark = pytest.mark.django_db

NAVEGADOR = {
    "HTTP_USER_AGENT": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36",
    "REMOTE_ADDR": "200.150.10.77",
}


def url(token: str) -> str:
    """Endereço da página de aceite."""
    return reverse("guia:aceite", args=[token])


def autorizar(client, token: str, **extra):
    """Envia o formulário de aceite."""
    dados = {"nome": "Maria Responsável", "autorizo": "on", "site_empresa": "", **extra}
    return client.post(url(token), dados, **NAVEGADOR)


def foto_jpeg(nome: str = "termo.jpg") -> SimpleUploadedFile:
    """Foto pequena de verdade (Pillow), como a do celular."""
    saida = io.BytesIO()
    Image.new("RGB", (800, 1000), (240, 240, 240)).save(saida, format="JPEG")
    return SimpleUploadedFile(nome, saida.getvalue(), content_type="image/jpeg")


def test_pagina_mostra_previa_e_termo_e_e_privada(client, perfil_pronto, termo):
    """Prévia, versão e data do termo; noindex, no-referrer e sem cache. O CNPJ não aparece."""
    perfil = perfil_pronto()
    _, token = services.gerar_convite(perfil)

    resposta = client.get(url(token), **NAVEGADOR)
    pagina = resposta.content.decode()

    assert resposta.status_code == 200
    assert perfil.nome_publico in pagina and "Eletricista" in pagina and "(65) 99999-0101" in pagina
    assert (
        f"Versão {termo.versao}" in pagina and "18/10/2026" not in pagina
    )  # vigência do fixture: 01/01/2026
    assert "01/01/2026" in pagina
    assert resposta["X-Robots-Tag"] == "noindex, nofollow"
    assert resposta["Referrer-Policy"] == "no-referrer"
    assert "no-store" in resposta["Cache-Control"]
    assert '<meta name="robots" content="noindex, nofollow">' in pagina
    assert "90000001000129" not in pagina and "maria@exemplo.com" not in pagina


def test_aceite_registra_e_publica(client, perfil_pronto, termo):
    """Confirmado: grava nome, versão, IP truncado e navegador resumido, usa o convite e publica na hora."""
    perfil = perfil_pronto()
    convite, token = services.gerar_convite(perfil)
    perfil.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.AGUARDANDO_ACEITE

    resposta = autorizar(client, token)

    assert resposta.status_code == 200 and "Autorização registrada" in resposta.content.decode()
    aceite = AceitePublicacao.objects.get()
    assert aceite.nome_digitado == "Maria Responsável" and aceite.termo == termo
    assert aceite.ip_truncado == "200.150.10.0"
    assert aceite.agente_resumido == "Chrome · Android"
    assert aceite.canal == ConviteAceite.Canal.WHATSAPP and aceite.convite == convite
    convite.refresh_from_db()
    perfil.refresh_from_db()
    assert convite.usado_em is not None
    assert perfil.status == PerfilGuia.Status.PUBLICADO and perfil.publicado_em
    assert mail.outbox and mail.outbox[0].to == ["maria@exemplo.com"]


def test_token_reutilizado_falha_sem_revelar_dados(client, perfil_pronto, termo):
    """Depois de usado: GET e POST dão "link já utilizado", sem o nome, e não gravam outro aceite."""
    perfil = perfil_pronto()
    _, token = services.gerar_convite(perfil)
    autorizar(client, token)

    pagina = client.get(url(token), **NAVEGADOR)
    segundo = autorizar(client, token, nome="Outra Pessoa")

    for resposta in (pagina, segundo):
        assert resposta.status_code == 410
        texto = resposta.content.decode()
        assert "já foi utilizado ou expirou" in texto and perfil.nome_publico not in texto
    assert AceitePublicacao.objects.count() == 1
    with pytest.raises(ValueError):
        services.aceitar_convite(token, "Outra Pessoa")


def test_token_expirado_falha(client, perfil_pronto, termo):
    """Vencido: mesma tela, nada gravado, perfil continua aguardando."""
    perfil = perfil_pronto()
    convite, token = services.gerar_convite(perfil)
    ConviteAceite.objects.filter(pk=convite.pk).update(expira_em=timezone.now() - timedelta(minutes=1))

    resposta = autorizar(client, token)

    assert resposta.status_code == 410 and perfil.nome_publico not in resposta.content.decode()
    assert not AceitePublicacao.objects.exists()
    perfil.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.AGUARDANDO_ACEITE


def test_token_inexistente_tem_a_mesma_resposta(client, db):
    """Token qualquer: mesma resposta (não dá para saber se existiu)."""
    resposta = client.get(url("x" * 43), **NAVEGADOR)
    assert resposta.status_code == 410 and "já foi utilizado ou expirou" in resposta.content.decode()


def test_novo_convite_vence_o_anterior_e_expira_no_prazo(perfil_pronto, termo):
    """Gerar outro link vence o anterior; validade = dias da configuração; token de 32 bytes, nunca o id."""
    perfil = perfil_pronto()
    primeiro, token1 = services.gerar_convite(perfil)
    segundo, token2 = services.gerar_convite(perfil)

    assert services.convite_valido(token1) is None
    assert services.convite_valido(token2) == segundo
    assert len(token2) >= 43 and str(perfil.pk) != token2
    dias = services.configuracao_guia().dias_validade_convite
    assert abs((segundo.expira_em - segundo.criado_em) - timedelta(days=dias)) < timedelta(seconds=5)


def test_convite_exige_cadastro_completo(perfil_pronto):
    """Sem contato não há convite (o aceite publicaria na hora)."""
    perfil = perfil_pronto(whatsapp="")
    with pytest.raises(services.PublicacaoRecusada):
        services.gerar_convite(perfil)
    assert not ConviteAceite.objects.exists()


def test_csrf_obrigatorio(perfil_pronto, termo):
    """Sem o token CSRF o POST é recusado."""
    _, token = services.gerar_convite(perfil_pronto())
    resposta = Client(enforce_csrf_checks=True).post(url(token), {"nome": "Maria Silva", "autorizo": "on"})
    assert resposta.status_code == 403
    assert not AceitePublicacao.objects.exists()


def test_limite_de_tentativas_por_hora(client, perfil_pronto, termo):
    """Passou do limite da configuração: 429, nada gravado."""
    config = services.configuracao_guia()
    config.tentativas_aceite_por_hora = 2
    config.save()
    _, token = services.gerar_convite(perfil_pronto())

    codigos = [autorizar(client, token, autorizo="").status_code for _ in range(3)]

    assert codigos == [400, 400, 429]
    assert not AceitePublicacao.objects.exists()


def test_robo_no_campo_armadilha_nao_grava(client, perfil_pronto, termo):
    """Campo-armadilha preenchido: tela de sucesso, mas nada gravado e o link continua valendo."""
    _, token = services.gerar_convite(perfil_pronto())
    resposta = autorizar(client, token, site_empresa="http://spam")
    assert resposta.status_code == 200 and not AceitePublicacao.objects.exists()
    assert services.convite_valido(token) is not None


def test_nome_precisa_ser_completo(client, perfil_pronto, termo):
    """Uma palavra só não serve."""
    _, token = services.gerar_convite(perfil_pronto())
    resposta = autorizar(client, token, nome="Maria")
    assert resposta.status_code == 400 and "nome completo" in resposta.content.decode()


# --- Admin: WhatsApp, papel, revogação -----------------------------------------------------------------


def test_botao_whatsapp_gera_convite_e_mensagem(admin_guia, perfil_pronto, termo):
    """O POST cria o convite e mostra a mensagem do GUIA_LGPD_E_TERMO.md §4 com o link e o wa.me."""
    perfil = perfil_pronto()

    resposta = admin_guia.post(reverse("admin:guia_perfil_convite", args=[perfil.pk]))
    pagina = resposta.content.decode()

    convite = ConviteAceite.objects.get()
    assert resposta.status_code == 200
    assert f"/guia/aceite/{convite.token}/" in pagina
    assert "https://wa.me/5565999990101?text=" in pagina
    assert "guia gratuito de serviços" in pagina and perfil.nome_publico in pagina


def test_aceite_presencial_publica_e_guarda_foto_privada(admin_guia, perfil_pronto, termo):
    """Foto do termo vai para o storage privado (fora da media/), regravada sem EXIF; perfil publicado."""
    perfil = perfil_pronto()

    resposta = admin_guia.post(
        reverse("admin:guia_perfil_presencial", args=[perfil.pk]),
        {"nome": "Maria Responsável", "foto": foto_jpeg(), "confirmo": "on"},
    )

    assert resposta.status_code == 302
    aceite = AceitePublicacao.objects.get()
    perfil.refresh_from_db()
    assert aceite.canal == ConviteAceite.Canal.PRESENCIAL and perfil.status == PerfilGuia.Status.PUBLICADO
    caminho = Path(aceite.foto_termo.path)
    assert caminho.exists() and Path(settings.MEDIA_ROOT) not in caminho.parents
    with pytest.raises(ValueError):
        aceite.foto_termo.url  # noqa: B018 (sem endereço público)
    foto = admin_guia.get(reverse("admin:guia_aceite_foto", args=[aceite.pk]))
    assert foto.status_code == 200 and "no-store" in foto["Cache-Control"]


def test_foto_do_termo_so_com_permissao(perfil_pronto, termo, membro, entrar_no_admin):
    """Financeiro não vê a foto do termo (nem o guia)."""
    perfil = perfil_pronto()
    aceite = services.registrar_aceite_presencial(perfil, foto_jpeg(), "Maria Responsável", None)
    cliente = entrar_no_admin(membro("Financeiro"))

    assert cliente.get(reverse("admin:guia_aceite_foto", args=[aceite.pk])).status_code == 403


def test_revogar_aceite_despublica_na_hora(admin_guia, perfil_pronto, termo):
    """Revogado: sai do ar, o registro fica (com data e motivo) e não volta sem novo aceite."""
    perfil = perfil_pronto()
    _, token = services.gerar_convite(perfil)
    aceite = services.aceitar_convite(token, "Maria Responsável")

    resposta = admin_guia.post(
        reverse("admin:guia_aceite_revogar", args=[aceite.pk]), {"motivo": "Pediu por WhatsApp."}
    )

    assert resposta.status_code == 302
    perfil.refresh_from_db()
    aceite.refresh_from_db()
    assert perfil.status == PerfilGuia.Status.PAUSADO
    assert aceite.revogado_em is not None and aceite.motivo_revogacao == "Pediu por WhatsApp."
    with pytest.raises(services.PublicacaoRecusada):
        services.publicar(perfil)
