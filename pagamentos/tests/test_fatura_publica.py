"""Revisão do link público de pagamento /fatura/<token>/ (Sprint 7B, passo 0) e do clique da publicidade:
token forte, cabeçalhos privados, fora do sitemap, só o necessário, upload com os mesmos limites e limite por
hora, paga mostra só "Fatura paga", e clique sem redirecionamento aberto."""

import io
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from pagamentos.models import Fatura
from pagamentos.services import confirmar_pagamento, gerar_fatura_campanha
from publicidade.models import Banner, Campanha, Patrocinador

pytestmark = pytest.mark.django_db


def png() -> bytes:
    """Imagem pequena de comprovante."""
    saida = io.BytesIO()
    Image.new("RGB", (300, 300), (10, 20, 30)).save(saida, format="PNG")
    return saida.getvalue()


@pytest.fixture
def fatura(settings):
    """Fatura aberta de uma campanha (patrocinador sem login), com Pix configurado."""
    settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE = (
        "12345678000195",
        "Negocios Diarios",
        "Tangara",
    )
    patrocinador = Patrocinador.objects.create(
        nome="Construtora Teste", email="segredo@construtora.exemplo.com"
    )
    hoje = timezone.localdate()
    campanha = Campanha.objects.create(
        patrocinador=patrocinador,
        nome="Campanha Interna Confidencial",
        posicoes=["home_topo"],
        inicio=hoje,
        fim=hoje + timedelta(days=30),
        valor=Decimal("500"),
        situacao="ativa",
    )
    return gerar_fatura_campanha(campanha)


def url(fatura: Fatura, envio: bool = False) -> str:
    """Endereço público da fatura (ou do envio do comprovante)."""
    nome = "pagamentos:fatura_publica_ja_paguei" if envio else "pagamentos:fatura_publica"
    return reverse(nome, args=[fatura.token])


def test_token_longo_aleatorio_e_sem_id_nem_codigo(fatura):
    """32 bytes do secrets (43 caracteres), diferente a cada fatura, sem o id nem o código."""
    outra = Fatura.objects.create(
        campanha=fatura.campanha,
        competencia=fatura.competencia,
        periodo_fim=fatura.periodo_fim,
        descricao="x",
        valor=1,
        vencimento=fatura.vencimento,
        situacao="cancelada",
    )
    assert len(fatura.token) >= 43 and fatura.token != outra.token
    assert str(fatura.pk) not in url(fatura).split("/fatura/")[0] and fatura.codigo not in url(fatura)
    assert fatura.identificador_pix not in fatura.token


def test_formato_antigo_ou_inventado_da_404(client, fatura):
    """UUID antigo, código ND-FT ou id não abrem nada (nem chegam à view)."""
    for falso in ("123e4567-e12b-12d1-a456-426655440000", fatura.codigo, str(fatura.pk), "a" * 43):
        assert client.get(f"/fatura/{falso}/").status_code == 404


def test_cabecalhos_privados_e_fora_do_sitemap(client, fatura):
    """noindex, no-referrer (cabeçalho e meta) e sem cache; o sitemap não lista faturas."""
    resposta = client.get(url(fatura))

    assert resposta["X-Robots-Tag"] == "noindex, nofollow"
    assert resposta["Referrer-Policy"] == "no-referrer"
    assert resposta["Cache-Control"] == "private, no-store"
    assert '<meta name="referrer" content="no-referrer">' in resposta.content.decode()
    assert "/fatura/" not in client.get(reverse("sitemap")).content.decode()


def test_mostra_so_o_necessario(client, fatura):
    """Nome do patrocinador, valor, vencimento e QR; nada de e-mail, nome da campanha ou período."""
    html = client.get(url(fatura)).content.decode()

    assert "Construtora Teste" in html and "R$ 500" in html and "data:image/svg+xml" in html
    assert f"{fatura.vencimento:%d/%m/%Y}" in html
    assert "segredo@construtora" not in html and "Confidencial" not in html
    assert f"{fatura.periodo_fim:%d/%m/%Y}" not in html


def test_comprovante_mesmos_limites_e_armazenamento_privado(client, fatura):
    """Arquivo falso é recusado; o válido vai para a pasta privada (fora da mídia pública)."""
    resposta = client.post(
        url(fatura, envio=True), {"comprovante": SimpleUploadedFile("x.png", b"falso", "image/png")}
    )
    assert resposta.status_code == 400 and "PDF, JPG, PNG ou WebP" in resposta.content.decode()

    client.post(url(fatura, envio=True), {"comprovante": SimpleUploadedFile("c.png", png(), "image/png")})
    fatura.refresh_from_db()
    caminho = Path(fatura.comprovante.path)
    assert fatura.situacao == "aguardando_confirmacao" and caminho.exists()
    assert Path(django_settings.MEDIA_ROOT) not in caminho.parents


def test_limite_de_tentativas_por_hora(client, fatura):
    """Depois de 10 envios na hora, o 11º é barrado (429) sem gravar nada."""
    for _ in range(10):
        client.post(
            url(fatura, envio=True), {"comprovante": SimpleUploadedFile("x.png", b"falso", "image/png")}
        )
    resposta = client.post(
        url(fatura, envio=True), {"comprovante": SimpleUploadedFile("c.png", png(), "image/png")}
    )

    assert resposta.status_code == 429 and "última hora" in resposta.content.decode()
    fatura.refresh_from_db()
    assert fatura.situacao == "aberta" and not fatura.comprovante


def test_paga_mostra_so_fatura_paga(client, fatura):
    """Depois de confirmada: só "Fatura paga", sem valor, sem QR, sem formulário."""
    confirmar_pagamento(fatura, None)
    html = client.get(url(fatura)).content.decode()

    assert "Fatura paga" in html
    assert "data:image/svg+xml" not in html and "R$ 500" not in html and "Já paguei" not in html


def test_clique_nunca_usa_url_da_requisicao(client, fatura):
    """Destino vem do banco pelo id da peça; ?url= ou ?next= são ignorados (sem open redirect)."""
    peca = Banner.objects.create(
        campanha=fatura.campanha, formato="nativo", titulo="T", texto="X", link="https://site.exemplo.com/"
    )
    endereco = reverse("publicidade:clique", args=[peca.pk])

    resposta = client.get(
        endereco,
        {"url": "https://golpe.exemplo.com/", "next": "//golpe.exemplo.com"},
        HTTP_USER_AGENT="Mozilla/5.0",
    )

    assert resposta.status_code == 302 and resposta["Location"] == "https://site.exemplo.com/"
