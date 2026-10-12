"""Anúncios de demonstração no banco (Sprint 3, parte B), a partir do demo.json (a fonte continua lá).

Chamado pelo `core.services.criar_dados_demo`. Cada imóvel do demo.json vira um anúncio publicado
da loja demo, com 3 a 5 fotos de exemplo desenhadas pelo Pillow (passam pelo mesmo processamento
das fotos reais: WebP, compartilhamento JPEG, sem EXIF), ponto no mapa conforme `exibir_localizacao`
e estatísticas fictícias dos últimos 30 dias. Veículos entram na Sprint 4. Idempotente.
"""

from __future__ import annotations

import io
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from anunciantes.models import Anunciante
from anuncios import services
from anuncios.models import Anuncio, DetalheImovel, Foto
from core.models import Bairro, Cidade
from core.services import configuracao

TIPOS = {rotulo: valor for valor, rotulo in DetalheImovel.Tipo.choices}
LARGURA, ALTURA = 1600, 1200

# Paletas por foto: (céu de cima, céu de baixo, chão, parede, telhado/detalhe)
PALETAS = [
    ((92, 160, 214), (198, 226, 240), (96, 150, 72), (238, 226, 200), (170, 70, 50)),
    ((240, 170, 110), (252, 220, 170), (120, 140, 70), (230, 214, 190), (120, 60, 40)),
    ((70, 120, 190), (170, 210, 235), (80, 130, 60), (215, 225, 230), (60, 80, 110)),
    ((110, 170, 200), (220, 236, 240), (150, 120, 80), (245, 235, 215), (14, 74, 87)),
    ((150, 190, 225), (230, 240, 248), (90, 140, 80), (225, 205, 175), (190, 140, 40)),
]


def _ceu_e_chao(desenho: ImageDraw.ImageDraw, paleta, horizonte: int) -> None:
    """Degradê do céu e o chão."""
    topo, baixo, chao = paleta[0], paleta[1], paleta[2]
    for y in range(horizonte):
        f = y / horizonte
        cor = tuple(round(topo[i] + (baixo[i] - topo[i]) * f) for i in range(3))
        desenho.line([(0, y), (LARGURA, y)], fill=cor)
    desenho.rectangle([0, horizonte, LARGURA, ALTURA], fill=chao)


def _arvore(desenho: ImageDraw.ImageDraw, x: int, y: int, tamanho: int) -> None:
    """Árvore simples (tronco e copa)."""
    desenho.rectangle([x - tamanho // 10, y - tamanho // 2, x + tamanho // 10, y], fill=(110, 80, 50))
    desenho.ellipse(
        [x - tamanho // 2, y - tamanho * 3 // 2, x + tamanho // 2, y - tamanho // 3], fill=(60, 120, 60)
    )


def _casa(desenho: ImageDraw.ImageDraw, paleta, x: int, y: int, largura: int) -> None:
    """Fachada: parede, telhado, porta e janelas."""
    altura = largura * 6 // 10
    parede, telhado = paleta[3], paleta[4]
    desenho.rectangle([x, y - altura, x + largura, y], fill=parede, outline=(90, 90, 90), width=4)
    desenho.polygon(
        [(x - 40, y - altura), (x + largura // 2, y - altura - largura // 3), (x + largura + 40, y - altura)],
        fill=telhado,
    )
    desenho.rectangle(
        [x + largura * 42 // 100, y - altura * 55 // 100, x + largura * 58 // 100, y], fill=(110, 75, 50)
    )
    for jx in (x + largura // 10, x + largura * 70 // 100):
        desenho.rectangle(
            [jx, y - altura * 75 // 100, jx + largura // 5, y - altura * 40 // 100],
            fill=(170, 210, 230),
            outline=(80, 80, 80),
            width=4,
        )


def _interior(desenho: ImageDraw.ImageDraw, paleta, comodo: str) -> None:
    """Cômodo: parede, piso, janela e um móvel conforme o cômodo."""
    desenho.rectangle([0, 0, LARGURA, ALTURA * 64 // 100], fill=paleta[3])
    desenho.rectangle([0, ALTURA * 64 // 100, LARGURA, ALTURA], fill=(185, 150, 110))
    for x in range(0, LARGURA, 200):
        desenho.line([(x, ALTURA * 64 // 100), (x - 300, ALTURA)], fill=(165, 130, 95), width=3)
    desenho.rectangle([1000, 180, 1400, 520], fill=paleta[1], outline=(255, 255, 255), width=18)
    if comodo == "sala":
        desenho.rounded_rectangle([200, 560, 860, 860], radius=40, fill=paleta[4])
        desenho.rounded_rectangle([240, 470, 820, 640], radius=40, fill=paleta[4])
    elif comodo == "quarto":
        desenho.rectangle([260, 600, 1000, 900], fill=(240, 240, 245))
        desenho.rectangle([260, 480, 320, 900], fill=paleta[4])
        desenho.rounded_rectangle([340, 560, 560, 650], radius=30, fill=(255, 255, 255))
    else:  # cozinha
        desenho.rectangle([120, 560, 1500, 800], fill=(245, 245, 245), outline=(120, 120, 120), width=4)
        desenho.rectangle([120, 520, 1500, 570], fill=(80, 80, 85))
        for x in range(160, 1500, 260):
            desenho.rectangle([x, 600, x + 200, 780], outline=(150, 150, 150), width=4)


def foto_de_exemplo(tipo: str, indice: int, rotulo: str) -> bytes:
    """Desenha uma foto fictícia (JPEG 1600×1200) do tipo de imóvel; marca "FOTO ILUSTRATIVA"."""
    paleta = PALETAS[indice % len(PALETAS)]
    imagem = Image.new("RGB", (LARGURA, ALTURA))
    desenho = ImageDraw.Draw(imagem)
    if tipo in ("casa", "apartamento", "kitnet") and indice > 0:
        _interior(desenho, paleta, ("sala", "quarto", "cozinha", "sala")[(indice - 1) % 4])
    else:
        horizonte = ALTURA * 55 // 100
        _ceu_e_chao(desenho, paleta, horizonte)
        desenho.ellipse([1300, 120, 1440, 260], fill=(255, 230, 120))
        if tipo == "terreno":
            for x in range(80, LARGURA, 120):
                desenho.rectangle([x, horizonte + 160, x + 14, horizonte + 320], fill=(150, 110, 70))
            desenho.line(
                [(60, horizonte + 200), (LARGURA - 60, horizonte + 200)], fill=(150, 110, 70), width=8
            )
            _arvore(desenho, 1350, horizonte + 120, 260)
        elif tipo in ("chacara", "sitio", "fazenda"):
            desenho.ellipse([150, horizonte + 220, 900, horizonte + 460], fill=(90, 150, 200))
            for x in range(1000, 1550, 140):
                _arvore(desenho, x, horizonte + 260 + (x % 3) * 20, 200)
            if indice % 2 == 0:
                _casa(desenho, paleta, 600, horizonte + 120, 380)
        else:
            _casa(desenho, paleta, 380 + (indice % 3) * 60, horizonte + 260, 760)
            _arvore(desenho, 200, horizonte + 260, 240)
    fonte = ImageFont.load_default(size=44)
    desenho.rectangle([0, ALTURA - 90, LARGURA, ALTURA], fill=(14, 74, 87))
    desenho.text((40, ALTURA - 70), f"FOTO ILUSTRATIVA · DEMO · {rotulo}", fill=(255, 244, 204), font=fonte)
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=88)
    return saida.getvalue()


def _estatisticas_ficticias(anuncio: Anuncio) -> None:
    """Visualizações e cliques dos últimos 30 dias (fixos por anúncio, para o painel ter números)."""
    from estatisticas.models import EstatisticaDiaria

    sorteio = random.Random(anuncio.codigo)  # noqa: S311 (números fictícios repetíveis, não segurança)
    hoje = timezone.localdate()
    for dias_atras in range(30):
        dia = hoje - timedelta(days=dias_atras)
        if anuncio.publicado_em and dia < timezone.localdate(anuncio.publicado_em) - timedelta(days=27):
            continue
        visualizacoes = sorteio.randint(3, 40)
        EstatisticaDiaria.objects.update_or_create(
            anuncio=anuncio,
            dia=dia,
            defaults={
                "visualizacoes": visualizacoes,
                "cliques_whatsapp": sorteio.randint(0, max(1, visualizacoes // 8)),
                "demo": True,
            },
        )


def criar_anuncios_demo(anuncios: list[dict]) -> int:
    """Cria (ou atualiza) os imóveis do demo.json no banco. Devolve quantos anúncios demo existem.

    Só lojas demo ATIVAS em cidades liberadas. Fotos são geradas só na primeira vez.
    """
    agora = timezone.now()
    prazo = timedelta(days=configuracao().expiracao_dias)
    total = 0
    for dado in anuncios:
        if dado["categoria"] != "imovel":
            continue  # veículos: Sprint 4
        loja = Anunciante.objects.filter(slug=dado["loja"], demo=True, status=Anunciante.Status.ATIVO).first()
        cidade = Cidade.objects.filter(codigo_ibge=dado["cidade_ibge"]).first()
        if loja is None or cidade is None:
            continue
        bairro = Bairro.objects.filter(cidade=cidade, nome=dado["bairro"]).first() if dado["bairro"] else None
        publicado_em = agora - timedelta(hours=dado["publicado_ha_horas"])
        campos = {
            "descricao": dado.get("descricao", ""),
            "preco": Decimal(dado["preco"]),
            "cidade": cidade,
            "bairro": bairro,
            "situacao": Anuncio.Situacao.PUBLICADO,
            "publicado_em": publicado_em,
            "expira_em": publicado_em + prazo,
            "destaque_ate": agora + timedelta(days=30) if dado["destaque"] else None,
            "demo": True,
        }
        anuncio = Anuncio.objects.filter(anunciante=loja, titulo=dado["titulo"]).first()
        if anuncio is None:
            anuncio = Anuncio(
                anunciante=loja, categoria=Anuncio.Categoria.IMOVEL, titulo=dado["titulo"], **campos
            )
        else:
            for campo, valor in campos.items():
                setattr(anuncio, campo, valor)
        anuncio.slug = slugify(anuncio.titulo)[:140]
        anuncio._change_reason = "Dados de demonstração."
        anuncio.save()

        detalhes = dado["detalhes"]
        ponto = dado.get("ponto")
        DetalheImovel.objects.update_or_create(
            anuncio=anuncio,
            defaults={
                "tipo": TIPOS[dado["tipo"]],
                "modalidade": dado["finalidade"],
                "quartos": detalhes.get("quartos", 0),
                "banheiros": detalhes.get("banheiros", 0),
                "vagas": detalhes.get("vagas", 0),
                "area_total": Decimal(detalhes["area_m2"]),
                "area_construida": Decimal(dado["area_construida"]) if dado.get("area_construida") else None,
                "iptu": Decimal(dado["iptu"]) if dado.get("iptu") else None,
                "endereco": "Endereço fictício (demonstração)",
                "ponto": Point(ponto[1], ponto[0], srid=4326) if ponto else None,
                "exibir_localizacao": dado.get("exibir_localizacao", "aproximada"),
            },
        )
        if not anuncio.fotos.exists():
            tipo = TIPOS[dado["tipo"]]
            for indice in range(dado.get("num_fotos", 3)):
                foto = Foto(anuncio=anuncio, ordem=indice)
                foto.original.save(
                    "demo.jpg", ContentFile(foto_de_exemplo(tipo, indice, dado["tipo"].upper())), save=False
                )
                foto.save()
                services.processar_foto(foto)  # na hora (o comando roda sem esperar o Celery)
        _estatisticas_ficticias(anuncio)
        total += 1
    return total
