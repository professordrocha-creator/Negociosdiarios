"""Validação e processamento de imagens: identidade do site (símbolos, favicon) e fotos das lojas.

Regras do projeto (CLAUDE.md, docs/SEGURANCA.md): validar o tipo REAL do arquivo (não a
extensão), limitar o tamanho, reprocessar e remover EXIF. SVG é texto e pode carregar
código: só passa sem script, eventos, links "javascript:", foreignObject e DOCTYPE.
"""

import io
import re
from pathlib import PurePath

from defusedxml import ElementTree
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

# Trechos que tornam um SVG perigoso (scripts, eventos, links externos, entidades XML).
_SVG_PROIBIDO = re.compile(
    r"<\s*script|<\s*foreignObject|<!DOCTYPE|<!ENTITY|\son\w+\s*=|javascript:|data:text/html|"
    r"(?:xlink:)?href\s*=\s*[\"']\s*(?:https?:|//)",
    re.IGNORECASE,
)

FORMATOS_RASTER = {"PNG": "png", "JPEG": "jpg"}


def _tamanho_ok(arquivo, limite_kb: int) -> None:
    """Recusa arquivo maior que o limite (KB vem da Configuracao, editável no admin)."""
    if arquivo.size > limite_kb * 1024:
        raise ValidationError(
            f"Arquivo de {arquivo.size // 1024} KB: o máximo é {limite_kb} KB. Reduza e envie de novo."
        )


def validar_svg(arquivo) -> None:
    """SVG de verdade (XML com raiz <svg>) e sem nada que execute código ou busque fora do site."""
    arquivo.seek(0)
    conteudo = arquivo.read()
    arquivo.seek(0)
    texto = conteudo.decode("utf-8", errors="replace")
    if _SVG_PROIBIDO.search(texto):
        raise ValidationError(
            "SVG com script, evento, link externo ou DOCTYPE não é aceito. Exporte um SVG simples."
        )
    try:
        raiz = ElementTree.fromstring(conteudo)  # defusedxml: sem entidades nem DTD
    except Exception as erro:
        raise ValidationError("Arquivo SVG inválido (não é um XML legível).") from erro
    if not raiz.tag.lower().endswith("svg"):
        raise ValidationError("O arquivo não é um SVG (falta a marca <svg>).")


def tipo_raster(arquivo) -> str:
    """Formato real (PNG ou JPEG) conferido pelo Pillow; recusa o resto."""
    arquivo.seek(0)
    try:
        with Image.open(arquivo) as imagem:
            formato = imagem.format
            imagem.verify()
    except (UnidentifiedImageError, OSError) as erro:
        raise ValidationError("Imagem inválida ou corrompida. Envie um PNG ou JPG.") from erro
    finally:
        arquivo.seek(0)
    if formato not in FORMATOS_RASTER:
        raise ValidationError(f"Formato {formato} não aceito. Envie PNG ou JPG.")
    return formato


def validar_simbolo(arquivo, limite_kb: int) -> None:
    """Símbolo do site: SVG seguro ou PNG, até `limite_kb`."""
    _tamanho_ok(arquivo, limite_kb)
    if PurePath(arquivo.name).suffix.lower() == ".svg":
        validar_svg(arquivo)
    elif tipo_raster(arquivo) != "PNG":
        raise ValidationError("O símbolo deve ser SVG ou PNG (com fundo transparente).")


def validar_compartilhamento(arquivo, limite_kb: int) -> None:
    """Imagem de compartilhamento: PNG ou JPG, até `limite_kb`."""
    _tamanho_ok(arquivo, limite_kb)
    tipo_raster(arquivo)


def reprocessar_raster(arquivo) -> ContentFile:
    """Regrava PNG/JPG a partir dos pixels: some o EXIF (GPS, câmera) e qualquer dado escondido."""
    arquivo.seek(0)
    with Image.open(arquivo) as imagem:
        formato = imagem.format
        # Só os pixels passam para a imagem nova: EXIF, ICC e textos embutidos ficam para trás.
        limpa = Image.frombytes(imagem.mode, imagem.size, imagem.tobytes())
        if imagem.mode == "P" and imagem.getpalette():
            limpa.putpalette(imagem.getpalette())
    saida = io.BytesIO()
    limpa.save(saida, format=formato, optimize=True)
    return ContentFile(saida.getvalue(), name=f"imagem.{FORMATOS_RASTER[formato]}")


def simbolo_em_png(arquivo, lado: int = 512) -> Image.Image:
    """Símbolo (SVG ou PNG) como imagem quadrada RGBA de `lado` px, para gerar os favicons."""
    arquivo.seek(0)
    if PurePath(arquivo.name).suffix.lower() == ".svg":
        import cairosvg  # importa só aqui: depende da libcairo2 do sistema

        png = cairosvg.svg2png(bytestring=arquivo.read(), output_width=lado, output_height=lado)
        imagem = Image.open(io.BytesIO(png))
    else:
        imagem = Image.open(arquivo)
        imagem.load()
    arquivo.seek(0)
    imagem = imagem.convert("RGBA")
    if imagem.size != (lado, lado):  # centraliza num quadrado transparente sem distorcer
        imagem.thumbnail((lado, lado))
        quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        quadro.paste(imagem, ((lado - imagem.width) // 2, (lado - imagem.height) // 2), imagem)
        imagem = quadro
    return imagem


def favicons(simbolo) -> dict[str, ContentFile]:
    """Gera favicon.ico (16/32/48), PNG 32, apple-touch 180 e ícone 512 a partir do símbolo."""
    base = simbolo_em_png(simbolo, 512)
    arquivos = {}
    for lado in (32, 180, 512):
        saida = io.BytesIO()
        base.resize((lado, lado), Image.LANCZOS).save(saida, format="PNG", optimize=True)
        arquivos[f"favicon_{lado}"] = ContentFile(saida.getvalue(), name=f"favicon-{lado}.png")
    saida = io.BytesIO()
    base.save(saida, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    arquivos["favicon_ico"] = ContentFile(saida.getvalue(), name="favicon.ico")
    return arquivos


# --- Fotos enviadas por anunciantes (logo e capa da loja; fotos de anúncio na Sprint 3) ----

FORMATOS_FOTO = {"JPEG", "PNG", "WEBP"}


def validar_foto(arquivo, limite_kb: int, min_largura: int, min_altura: int) -> None:
    """JPG, PNG ou WebP de verdade (Pillow), até `limite_kb` e com as dimensões mínimas.

    As dimensões consideram a rotação gravada pelo celular (EXIF), como a imagem aparece.
    Mensagens dizem o que fazer (docs/TELAS.md).
    """
    _tamanho_ok(arquivo, limite_kb)
    arquivo.seek(0)
    try:
        with Image.open(arquivo) as imagem:
            formato = imagem.format
            imagem.verify()
        arquivo.seek(0)
        with Image.open(arquivo) as imagem:
            largura, altura = ImageOps.exif_transpose(imagem).size
    except (UnidentifiedImageError, OSError) as erro:
        raise ValidationError("Imagem inválida ou corrompida. Envie JPG, PNG ou WebP.") from erro
    finally:
        arquivo.seek(0)
    if formato not in FORMATOS_FOTO:
        raise ValidationError(f"Formato {formato} não aceito. Envie JPG, PNG ou WebP.")
    if largura < min_largura or altura < min_altura:
        raise ValidationError(
            f"Imagem de {largura}×{altura} px: o mínimo é {min_largura}×{min_altura} px. "
            "Envie uma imagem maior."
        )


def abrir_limpa(arquivo) -> Image.Image:
    """Abre a foto já na posição certa (rotação do EXIF) e sem nenhum metadado (GPS, câmera)."""
    arquivo.seek(0)
    with Image.open(arquivo) as original:
        girada = ImageOps.exif_transpose(original)
        modo = "RGBA" if girada.mode in ("RGBA", "LA", "P") else "RGB"
        convertida = girada.convert(modo)
        return Image.frombytes(modo, convertida.size, convertida.tobytes())


def recortar_proporcao(imagem: Image.Image, proporcao: float) -> Image.Image:
    """Recorta pelo centro na proporção largura/altura pedida (1 = quadrado, 4 = capa 4:1)."""
    largura, altura = imagem.size
    if largura / altura > proporcao:  # larga demais: corta as laterais
        nova = round(altura * proporcao)
        esquerda = (largura - nova) // 2
        return imagem.crop((esquerda, 0, esquerda + nova, altura))
    nova = round(largura / proporcao)  # alta demais: corta em cima e embaixo
    topo = (altura - nova) // 2
    return imagem.crop((0, topo, largura, topo + nova))


def webp(imagem: Image.Image, largura: int, nome: str) -> ContentFile:
    """WebP com a largura pedida (mantendo a proporção), sem nunca ampliar imagem pequena."""
    if imagem.width > largura:
        altura = round(imagem.height * largura / imagem.width)
        imagem = imagem.resize((largura, altura), Image.LANCZOS)
    saida = io.BytesIO()
    imagem.save(saida, format="WEBP", quality=82, method=4)
    return ContentFile(saida.getvalue(), name=f"{nome}.webp")
