"""Regras da publicidade (docs/PUBLICIDADE.md, Sprint 7A).

- Escolha da peça: campanha ativa e no período, posição pedida, formato da posição, peça pronta e ativa;
  cidade: campanha sem cidades vale no site todo, com cidades só nelas. Rodízio: sorteio a cada página.
- Métricas: impressões e cliques somados por dia (UPDATE com F()), SEM IP, SEM cookie, sem robôs.
- Imagens: mesmo tratamento das fotos (tipo real, limite de peso, Celery → WebP no tamanho da
  Configuracao, sem EXIF, original apagado).
- Rotina diária: campanha que passou do fim é encerrada; a equipe recebe aviso X dias antes do fim.
- Loja do site só compra publicidade se for assinante (não vender visibilidade a concorrente de quem paga).
"""

from __future__ import annotations

import csv
import io
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet, Sum
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from core import imagens
from core.services import configuracao
from publicidade.models import FORMATO_DA_POSICAO, Banner, Campanha, Formato, MetricaDiaria, Patrocinador

if TYPE_CHECKING:
    from django.http import HttpRequest

    from core.models import Cidade, Configuracao

logger = logging.getLogger(__name__)

IMPRESSOES, CLIQUES = "impressoes", "cliques"
TOLERANCIA_PROPORCAO = (
    0.10  # imagem até 10% fora da proporção é recortada pelo centro; mais que isso, recusada
)


# --- Tamanhos (Configuracao) ------------------------------------------------------------------------


@dataclass(frozen=True)
class Tamanho:
    """Largura × altura de uma imagem de peça."""

    largura: int
    altura: int

    def __str__(self) -> str:
        """Ex.: '970×90'."""
        return f"{self.largura}×{self.altura}"


def tamanhos(config: Configuracao | None = None) -> dict[str, Tamanho]:
    """Tamanhos das imagens por campo da peça, vindos do admin."""
    config = config or configuracao()
    return {
        "banner": Tamanho(config.banner_largura_px, config.banner_altura_px),
        "banner_celular": Tamanho(config.banner_celular_largura_px, config.banner_celular_altura_px),
        "card": Tamanho(config.card_patrocinador_px, config.card_patrocinador_px),
    }


def tamanho_da_imagem(formato: str, celular: bool = False) -> Tamanho:
    """Tamanho final da imagem de um formato (o banner tem a do computador e a do celular)."""
    t = tamanhos()
    if formato == Formato.CARD:
        return t["card"]
    return t["banner_celular"] if celular else t["banner"]


def validar_imagem(arquivo, tamanho: Tamanho) -> None:
    """Tipo real (JPG/PNG/WebP), peso da Configuracao, no mínimo o tamanho final e perto da proporção."""
    largura, altura = imagens.validar_foto(
        arquivo, configuracao().limite_banner_kb, tamanho.largura, tamanho.altura
    )
    esperada = tamanho.largura / tamanho.altura
    if abs(largura / altura - esperada) / esperada > TOLERANCIA_PROPORCAO:
        raise ValidationError(
            f"Imagem de {largura}×{altura} px fora da proporção: use {tamanho} px "
            "(ou maior, na mesma proporção)."
        )


def imagem_no_tamanho(arquivo, tamanho: Tamanho, nome: str) -> ContentFile:
    """WebP no tamanho exato: rotação aplicada, sem EXIF, recorte central na proporção, reduzido."""
    with arquivo.open("rb") as aberto:
        limpa = imagens.abrir_limpa(aberto)
    recortada = imagens.recortar_proporcao(limpa, tamanho.largura / tamanho.altura)
    final = recortada.resize((tamanho.largura, tamanho.altura), Image.Resampling.LANCZOS)
    return imagens.webp(final, tamanho.largura, nome)


def processar_banner(banner: Banner) -> bool:
    """Gera os WebP da peça a partir dos envios e apaga os originais (Celery). False se não abriu."""
    feito = False
    pares = [("imagem_original", "imagem", False), ("imagem_celular_original", "imagem_celular", True)]
    for origem, destino, celular in pares:
        original = getattr(banner, origem)
        if not original:
            continue
        try:
            conteudo = imagem_no_tamanho(original, tamanho_da_imagem(banner.formato, celular), destino)
        except Exception:
            logger.exception("Imagem de publicidade não pôde ser processada (peça id=%s).", banner.pk)
            original.delete(save=False)
            continue
        antiga = getattr(banner, destino)
        if antiga:
            antiga.delete(save=False)
        getattr(banner, destino).save(f"{destino}.webp", conteudo, save=False)
        original.delete(save=False)
        feito = True
    banner.save()
    return feito


# --- Escolha da peça (rodízio) e métricas -------------------------------------------------------------


def no_ar(hoje: date | None = None) -> QuerySet[Banner]:
    """Peças que podem aparecer hoje: ativas, prontas, de campanha ativa no período (demo: MOSTRAR_DEMO)."""
    hoje = hoje or timezone.localdate()
    pecas = Banner.objects.filter(
        ativo=True,
        campanha__situacao=Campanha.Situacao.ATIVA,
        campanha__inicio__lte=hoje,
        campanha__fim__gte=hoje,
    ).filter(Q(formato=Formato.NATIVO) | ~Q(imagem=""))
    pecas = pecas.exclude(formato=Formato.BANNER, imagem_celular="")
    return pecas if settings.MOSTRAR_DEMO else pecas.filter(demo=False)


def escolher(
    posicao: str, cidade: Cidade | None = None, quantos: int = 1, hoje: date | None = None
) -> list[Banner]:
    """Rodízio: sorteia até `quantos` peças diferentes para a posição (uma por campanha).

    Sem cidade na página (home): só campanhas sem cidade. Com cidade: as sem cidade e as daquela cidade.
    """
    pecas = no_ar(hoje).filter(formato=FORMATO_DA_POSICAO[posicao], campanha__posicoes__contains=[posicao])
    if cidade is None:
        pecas = pecas.filter(campanha__cidades__isnull=True)
    else:
        pecas = pecas.filter(Q(campanha__cidades__isnull=True) | Q(campanha__cidades=cidade))
    por_campanha: dict[int, list[Banner]] = {}
    for peca in pecas.select_related("campanha").distinct():
        por_campanha.setdefault(peca.campanha_id, []).append(peca)
    sorteadas = random.sample(list(por_campanha.values()), k=min(quantos, len(por_campanha)))
    return [random.choice(opcoes) for opcoes in sorteadas]  # noqa: S311 (rodízio, não é segurança)


def _somar(banner_id: int, dia: date, campo: str) -> None:
    """+1 no total do dia, sem corrida (UPDATE com F(); cria a linha na primeira vez do dia)."""
    linhas = MetricaDiaria.objects.filter(banner_id=banner_id, dia=dia)
    if linhas.update(**{campo: F(campo) + 1}):
        return
    try:
        with transaction.atomic():
            MetricaDiaria.objects.create(banner_id=banner_id, dia=dia, **{campo: 1})
    except IntegrityError:  # outro acesso criou a linha no mesmo instante
        linhas.update(**{campo: F(campo) + 1})


def deve_contar(request: HttpRequest | None) -> bool:
    """Conta só visitante de verdade: sem robôs e sem as trocas parciais do HTMX (peça não redesenhada)."""
    from estatisticas.services import e_robo

    if request is None or e_robo(request):
        return False
    return request.headers.get("HX-Request") != "true"


def registrar(banner: Banner, campo: str, request: HttpRequest | None) -> bool:
    """Soma impressão ou clique do dia. Nada do visitante é lido além do User-Agent (para pular robôs)."""
    if not deve_contar(request):
        return False
    _somar(banner.pk, timezone.localdate(), campo)
    return True


def link_seguro(banner: Banner) -> str | None:
    """O link da peça, só se for http/https (validado no cadastro; conferido de novo no clique)."""
    link = (banner.link or "").strip()
    return link if link.lower().startswith(("https://", "http://")) else None


# --- Regras de venda ---------------------------------------------------------------------------------


def conferir_patrocinador(campanha: Campanha) -> None:
    """Loja do site só compra publicidade se for assinante (regra 4). Vale ao ativar a campanha."""
    loja = campanha.patrocinador.anunciante
    if campanha.situacao != Campanha.Situacao.ATIVA or loja is None:
        return
    from planos.models import Assinatura
    from planos.services import assinatura_de

    assinatura = assinatura_de(loja)
    if assinatura is None or assinatura.situacao != Assinatura.Situacao.ATIVA:
        raise ValidationError(
            f"{loja} é uma loja do site sem assinatura ativa: loja só compra publicidade se for assinante."
        )


# --- Rotina diária -----------------------------------------------------------------------------------


def destinatarios_comercial() -> list[str]:
    """Quem recebe os avisos de publicidade: superusuários e os grupos Comercial e Administrador."""
    Usuario = get_user_model()
    emails = list(
        Usuario.objects.filter(is_active=True, is_staff=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=["Comercial", "Administrador"]))
        .values_list("email", flat=True)
        .distinct()
    )
    return emails or [configuracao().email_contato]


def encerrar_vencidas(hoje: date | None = None) -> int:
    """Campanha ativa que passou do fim vira "encerrada" (sai do ar já pela data; aqui fica registrado)."""
    hoje = hoje or timezone.localdate()
    total = 0
    for campanha in Campanha.objects.filter(situacao=Campanha.Situacao.ATIVA, fim__lt=hoje):
        campanha.situacao = Campanha.Situacao.ENCERRADA
        campanha._change_reason = f"Encerrada sozinha: terminou em {campanha.fim:%d/%m/%Y}."
        campanha.save(update_fields=["situacao", "atualizado_em"])
        total += 1
    return total


def avisar_fim_proximo(hoje: date | None = None) -> int:
    """E-mail à equipe para cada campanha ativa a até X dias do fim (uma vez; recupera dia perdido)."""
    hoje = hoje or timezone.localdate()
    dias = configuracao().campanha_aviso_dias
    campanhas = list(
        Campanha.objects.filter(
            situacao=Campanha.Situacao.ATIVA,
            aviso_fim_enviado=False,
            fim__gte=hoje,
            fim__lte=hoje + timedelta(days=dias),
        ).select_related("patrocinador")
    )
    if not campanhas:
        return 0
    linhas = [
        f"- {c.nome} ({c.patrocinador.nome}): termina em {c.fim:%d/%m/%Y}. Contato: {c.patrocinador.email}"
        for c in campanhas
    ]
    link = settings.SITE_URL + reverse("admin:publicidade_campanha_painel")
    send_mail(
        f"{len(campanhas)} campanha(s) de publicidade terminando · {configuracao().nome}",
        "Campanhas que saem do ar em breve (ofereça a renovação):\n\n"
        + "\n".join(linhas)
        + f"\n\nPainel: {link}\n",
        None,
        destinatarios_comercial(),
    )
    Campanha.objects.filter(pk__in=[c.pk for c in campanhas]).update(aviso_fim_enviado=True)
    return len(campanhas)


def rotina_de_publicidade(hoje: date | None = None) -> dict[str, int]:
    """A rotina diária: encerra as vencidas e avisa as que terminam em breve."""
    resultado = {"encerradas": encerrar_vencidas(hoje), "avisos": avisar_fim_proximo(hoje)}
    logger.info("Rotina de publicidade: %s", resultado)  # só números
    return resultado


# --- Painel do admin e CSV -----------------------------------------------------------------------------


@dataclass
class LinhaPainel:
    """Uma campanha no painel: situação, período e números do intervalo pedido."""

    campanha: Campanha
    impressoes: int
    cliques: int
    no_ar: bool
    a_vencer: bool

    @property
    def taxa_de_cliques(self) -> str:
        """CTR em %, com 2 casas (cliques ÷ impressões)."""
        if not self.impressoes:
            return "—"
        return f"{100 * self.cliques / self.impressoes:.2f}%".replace(".", ",")


def painel(de: date, ate: date, hoje: date | None = None) -> dict:
    """Campanhas (menos rascunho e cancelada) com impressões e cliques de `de` a `ate`, e os resumos."""
    hoje = hoje or timezone.localdate()
    aviso = configuracao().campanha_aviso_dias
    totais = {
        linha["banner__campanha"]: linha
        for linha in MetricaDiaria.objects.filter(dia__gte=de, dia__lte=ate)
        .values("banner__campanha")
        .annotate(impressoes=Sum("impressoes"), cliques=Sum("cliques"))
    }
    campanhas = (
        Campanha.objects.exclude(situacao__in=[Campanha.Situacao.RASCUNHO, Campanha.Situacao.CANCELADA])
        .select_related("patrocinador")
        .order_by("fim", "nome")
    )
    linhas = [
        LinhaPainel(
            campanha=c,
            impressoes=totais.get(c.pk, {}).get("impressoes") or 0,
            cliques=totais.get(c.pk, {}).get("cliques") or 0,
            no_ar=c.no_ar(hoje),
            a_vencer=c.no_ar(hoje) and c.fim <= hoje + timedelta(days=aviso),
        )
        for c in campanhas
    ]
    return {
        "linhas": linhas,
        "ativas": sum(linha.no_ar for linha in linhas),
        "a_vencer": sum(linha.a_vencer for linha in linhas),
        "impressoes": sum(linha.impressoes for linha in linhas),
        "cliques": sum(linha.cliques for linha in linhas),
        "aviso_dias": aviso,
    }


def _celula_segura(valor) -> str:
    """Planilha não executa fórmula vinda de texto digitado (=, +, -, @ no começo viram texto)."""
    texto = str(valor)
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def painel_csv(de: date, ate: date) -> str:
    """CSV (separador ;, para o Excel em português) com os números do painel."""
    dados = painel(de, ate)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(
        [
            "campanha",
            "patrocinador",
            "posições",
            "início",
            "fim",
            "situação",
            "valor",
            "impressões",
            "cliques",
            "CTR",
        ]
    )
    for linha in dados["linhas"]:
        c = linha.campanha
        escritor.writerow(
            [
                _celula_segura(c.nome),
                _celula_segura(c.patrocinador.nome),
                ", ".join(c.posicoes),
                f"{c.inicio:%d/%m/%Y}",
                f"{c.fim:%d/%m/%Y}",
                c.get_situacao_display(),
                f"{c.valor}".replace(".", ","),
                linha.impressoes,
                linha.cliques,
                linha.taxa_de_cliques,
            ]
        )
    return saida.getvalue()


# --- Dados de demonstração -------------------------------------------------------------------------------


def _imagem_demo(tamanho, texto: str, cor: tuple[int, int, int]) -> ContentFile:
    """Peça fictícia desenhada pelo Pillow, já no tamanho final e em WebP."""
    imagem = Image.new("RGB", (tamanho.largura, tamanho.altura), cor)
    desenho = ImageDraw.Draw(imagem)
    desenho.text((12, max(tamanho.altura // 2 - 6, 4)), texto, fill=(255, 255, 255))
    return imagens.webp(imagem, tamanho.largura, "demo")


DEMO = [
    {
        "patrocinador": "Construtora Horizonte (demonstração)",
        "email": "contato@horizonte.demo.invalid",
        "campanha": "Lançamento Residencial Ipê",
        "posicoes": ["home_topo", "anuncio_topo"],
        "inicio": -20,
        "fim": 40,
        "valor": "599.00",
        "formato": Formato.BANNER,
        "cor": (14, 74, 87),
        "texto": "Residencial Ipê - apartamentos na planta (DEMO)",
    },
    {
        "patrocinador": "Casa & Obra Materiais (demonstração)",
        "email": "contato@casaeobra.demo.invalid",
        "campanha": "Feirão de pisos",
        "posicoes": ["busca_topo", "busca_nativo"],
        "inicio": -25,
        "fim": 5,
        "valor": "399.00",
        "formato": Formato.BANNER,
        "cor": (166, 77, 30),
        "texto": "Feirão de pisos e revestimentos (DEMO)",
        "nativo": (
            "Piso porcelanato com 30% de desconto",
            "Entrega em Tangará e região. Parcelamos em até 10x.",
        ),
    },
    {
        "patrocinador": "AutoPeças Serra (demonstração)",
        "email": "contato@autopecas.demo.invalid",
        "campanha": "Revisão completa",
        "posicoes": ["rodape_card"],
        "inicio": -10,
        "fim": 60,
        "valor": "199.00",
        "formato": Formato.CARD,
        "cor": (40, 90, 40),
        "texto": "AutoPecas Serra (DEMO)",
        "frase": "Revisão completa com desconto para quem achou o carro aqui.",
    },
]


def criar_publicidade_demo() -> int:
    """3 campanhas fictícias marcadas como demo, com peças, 14 dias de métricas e faturas (uma paga, uma
    aberta). Recria do zero (idempotente). Chamado pelo `criar_dados_demo` do core."""
    from pagamentos.services import confirmar_pagamento, gerar_fatura_campanha

    apagar_publicidade_demo()
    hoje = timezone.localdate()
    t = tamanhos()
    for indice, dados in enumerate(DEMO):
        patrocinador = Patrocinador.objects.create(
            nome=dados["patrocinador"], email=dados["email"], demo=True
        )
        campanha = Campanha.objects.create(
            patrocinador=patrocinador,
            nome=dados["campanha"],
            posicoes=dados["posicoes"],
            inicio=hoje + timedelta(days=dados["inicio"]),
            fim=hoje + timedelta(days=dados["fim"]),
            valor=dados["valor"],
            situacao=Campanha.Situacao.ATIVA,
            demo=True,
        )
        principal = Banner(
            campanha=campanha,
            formato=dados["formato"],
            texto_alternativo=dados["texto"],
            texto=dados.get("frase", ""),
            titulo=patrocinador.nome.split(" (")[0] if dados["formato"] == Formato.CARD else "",
            link="https://www.example.com/",
            demo=True,
        )
        tamanho = t["card"] if dados["formato"] == Formato.CARD else t["banner"]
        principal.imagem.save("imagem.webp", _imagem_demo(tamanho, dados["texto"], dados["cor"]), save=False)
        if dados["formato"] == Formato.BANNER:
            principal.imagem_celular.save(
                "celular.webp", _imagem_demo(t["banner_celular"], "DEMO", dados["cor"]), save=False
            )
        principal.save()
        pecas = [principal]
        if "nativo" in dados:
            titulo, texto = dados["nativo"]
            pecas.append(
                Banner.objects.create(
                    campanha=campanha,
                    formato=Formato.NATIVO,
                    titulo=titulo,
                    texto=texto,
                    link="https://www.example.com/",
                    demo=True,
                )
            )
        for peca in pecas:  # 14 dias de números fictícios (determinísticos)
            MetricaDiaria.objects.bulk_create(
                MetricaDiaria(
                    banner=peca,
                    dia=hoje - timedelta(days=d),
                    impressoes=120 + 37 * ((d + indice) % 5),
                    cliques=2 + (d + indice) % 4,
                )
                for d in range(1, 15)
            )
        fatura = gerar_fatura_campanha(campanha, hoje)
        if indice == 0:
            confirmar_pagamento(fatura, None, observacao="Pix conferido (demonstração).")
    return len(DEMO)


def apagar_publicidade_demo() -> int:
    """Apaga a publicidade de demonstração (faturas das campanhas demo, peças com as imagens, campanhas e
    patrocinadores). As faturas demo das lojas ficam (são do planos/pagamentos)."""
    from pagamentos.models import Fatura

    for fatura in Fatura.objects.filter(campanha__demo=True):
        if fatura.comprovante:
            fatura.comprovante.delete(save=False)
    Fatura.objects.filter(campanha__demo=True).delete()
    Fatura.history.filter(demo=True, campanha_id__isnull=False).delete()
    quantas = Campanha.objects.filter(demo=True).count()
    for banner in Banner.objects.filter(Q(demo=True) | Q(campanha__demo=True)):
        for campo in ("imagem_original", "imagem", "imagem_celular_original", "imagem_celular"):
            arquivo = getattr(banner, campo)
            if arquivo:
                arquivo.delete(save=False)
    with transaction.atomic():
        Banner.objects.filter(Q(demo=True) | Q(campanha__demo=True)).delete()
        Campanha.objects.filter(demo=True).delete()
        Campanha.history.filter(demo=True).delete()
        Patrocinador.objects.filter(demo=True).delete()
        Patrocinador.history.filter(demo=True).delete()
    return quantas
