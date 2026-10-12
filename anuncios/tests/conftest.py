"""Ajudantes dos testes de anúncios: fotos de teste (com EXIF/GPS e rotação) e foto já processada.

As fixtures `loja`, `imovel` e `publicado` ficam no conftest.py da raiz (usadas também pelos
testes de estatísticas e da CSP).
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from anuncios.models import Foto
from core import imagens

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


def foto_pronta(anuncio, ordem: int = 0) -> Foto:
    """Foto já processada (sem passar pelo Celery), para o anúncio ficar completo."""
    foto = Foto(anuncio=anuncio, ordem=ordem)
    limpa = Image.new("RGB", (800, 600), (200, 180, 40))
    foto.imagem.save("imagem.webp", imagens.webp(limpa, 1600, "imagem"), save=False)
    foto.miniatura.save("miniatura.webp", imagens.webp(limpa, 400, "miniatura"), save=False)
    foto.compartilhamento.save("compartilhamento.jpg", imagens.jpeg_compartilhamento(limpa, "c"), save=False)
    foto.save()
    return foto
