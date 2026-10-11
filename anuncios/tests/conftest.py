"""Fixtures dos testes de anúncios: loja com plano, anúncio completo e fotos de teste com EXIF."""

import io
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from anuncios import services
from anuncios.models import Foto
from core import imagens
from planos.models import Periodicidade, Plano
from planos.services import criar_assinatura

CAMERA = "CameraTeste"


def jpeg(largura: int = 1200, altura: int = 900, orientacao: int | None = None, gps: bool = False) -> bytes:
    """JPEG de teste; opcionalmente com rotação do celular (EXIF 0x0112) e GPS (o que deve sumir)."""
    imagem = Image.new("RGB", (largura, altura), (30, 120, 90))
    exif = Image.Exif()
    exif[0x010F] = CAMERA  # fabricante da câmera
    if orientacao:
        exif[0x0112] = orientacao
    if gps:
        dados_gps = exif.get_ifd(0x8825)
        dados_gps[1] = "S"
        dados_gps[2] = (14.0, 37.0, 30.0)
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", exif=exif)
    return saida.getvalue()


def envio(nome: str = "foto.jpg", **kwargs) -> SimpleUploadedFile:
    """Arquivo enviado por formulário."""
    return SimpleUploadedFile(nome, jpeg(**kwargs), content_type="image/jpeg")


@pytest.fixture
def loja(criar_anunciante, tangara):
    """Fábrica: anunciante ativo com assinatura ativa (padrão: Básico, 10 anúncios)."""

    def _criar(
        email: str = "loja@exemplo.com", nome: str = "Loja Alfa", slug_plano: str = "basico", limite=None
    ):
        anunciante = criar_anunciante(email, nome)
        plano = Plano.objects.get(slug=slug_plano)
        if limite is not None:
            plano.limite_anuncios = limite
            plano.save()
        criar_assinatura(anunciante, plano, Periodicidade.MENSAL)
        return anunciante

    return _criar


def foto_pronta(anuncio, ordem: int = 0) -> Foto:
    """Foto já processada (sem passar pelo Celery), para o anúncio ficar completo."""
    foto = Foto(anuncio=anuncio, ordem=ordem)
    limpa = Image.new("RGB", (800, 600), (200, 180, 40))
    foto.imagem.save("imagem.webp", imagens.webp(limpa, 1600, "imagem"), save=False)
    foto.miniatura.save(
        "miniatura.webp", ContentFile(imagens.webp(limpa, 400, "miniatura").read()), save=False
    )
    foto.save()
    return foto


@pytest.fixture
def imovel(tangara):
    """Fábrica: anúncio de imóvel em rascunho; `completo=True` já tem descrição, ponto e foto."""

    def _criar(anunciante, titulo: str = "Casa 3 quartos com área gourmet", completo: bool = True, **ficha):
        dados = {
            "titulo": titulo,
            "descricao": "Casa ampla, perto do centro." if completo else "",
            "preco": Decimal("420000"),
        }
        ficha = {"tipo": "casa", "modalidade": "venda", "quartos": 3, "area_total": Decimal("180"), **ficha}
        anuncio = services.criar_anuncio_imovel(anunciante, dados, ficha)
        if completo:
            anuncio.imovel.ponto = Point(-57.49, -14.62, srid=4326)
            anuncio.imovel.save()
            foto_pronta(anuncio)
        return anuncio

    return _criar


@pytest.fixture
def publicado(imovel, settings):
    """Fábrica: anúncio já publicado (moderação desligada só para montar o cenário)."""
    from core.services import configuracao

    def _criar(anunciante, titulo: str = "Casa 3 quartos com área gourmet"):
        config = configuracao()
        regra, config.moderacao = config.moderacao, "nenhum"
        config.save()
        anuncio = imovel(anunciante, titulo)
        services.enviar_para_publicacao(anuncio)
        config.moderacao = regra
        config.save()
        anuncio.refresh_from_db()
        return anuncio

    return _criar
