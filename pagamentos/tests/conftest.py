"""Fixtures da cobrança: loja com assinatura, fatura aberta, equipe por grupo e arquivos de comprovante."""

import io
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from pagamentos.services import gerar_fatura
from planos.models import Assinatura
from planos.services import assinatura_de

PDF_SIMPLES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture(autouse=True)
def pix_configurado(settings):
    """Chave Pix de teste (os testes do "sem Pix" apagam)."""
    settings.PIX_CHAVE = "12345678000195"
    settings.PIX_NOME = "Negócios Diários Ltda"
    settings.PIX_CIDADE = "Tangará da Serra"


@pytest.fixture
def com_fatura(loja):
    """Fábrica: loja com assinatura (Básico mensal) e a fatura do ciclo, vencendo em `dias` (sem e-mail)."""

    def _criar(email: str = "loja@exemplo.com", nome: str = "Loja Alfa", dias: int = 5):
        anunciante = loja(email, nome)
        Assinatura.objects.filter(anunciante=anunciante).update(
            vencimento=timezone.localdate() + timedelta(days=dias)
        )
        return gerar_fatura(assinatura_de(anunciante), avisar=False)

    return _criar


@pytest.fixture
def equipe(db):
    """Fábrica: membro da equipe num grupo (Financeiro, Moderador...)."""

    def _criar(grupo: str, email: str = ""):
        usuario = Usuario.objects.create_user(
            email=email or f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return usuario

    return _criar


def imagem(formato: str = "PNG", exif: bool = False, lado: int = 300) -> bytes:
    """Imagem de teste; com `exif`, leva GPS e o fabricante da câmera."""
    saida = io.BytesIO()
    img = Image.new("RGB", (lado, lado), (30, 120, 90))
    if exif:
        dados = Image.Exif()
        dados[0x8825] = {2: (15.0, 30.0, 0.0)}
        dados[0x010F] = "Camera Teste"
        img.save(saida, format=formato, exif=dados)
    else:
        img.save(saida, format=formato)
    return saida.getvalue()


def envio(nome: str, conteudo: bytes, tipo: str = "image/png") -> SimpleUploadedFile:
    """Arquivo como chega do formulário."""
    return SimpleUploadedFile(nome, conteudo, tipo)
