"""Regras do app estatisticas: contar visualizações e cliques no WhatsApp sem guardar dado pessoal.

Como não guardamos IP (docs/LGPD.md): para contar "1 por visitante por dia", juntamos IP e
navegador com um SAL ALEATÓRIO DO DIA e tiramos um hash (SHA-256). Só esse hash vai para o
cache, com validade até o fim do dia; o sal do dia também expira. No banco ficam só os totais
por anúncio e dia. Robôs (buscadores, prévias de link) e o próprio dono do anúncio não contam.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import date, datetime, time, timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.http import HttpRequest
from django.utils import timezone

from anuncios.models import Anuncio
from estatisticas.models import EstatisticaDiaria

VISUALIZACAO = "visualizacoes"
CLIQUE_WHATSAPP = "cliques_whatsapp"
EVENTOS = (VISUALIZACAO, CLIQUE_WHATSAPP)

# Navegadores automáticos: buscadores, prévias de link (WhatsApp, Facebook, Telegram), monitores, scripts.
ROBOS = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|discord|skype|"
    r"curl|wget|python|httpx|okhttp|java/|go-http|headless|lighthouse|monitor|uptime|scrapy",
    re.IGNORECASE,
)


def e_robo(request: HttpRequest) -> bool:
    """Requisição de robô (pelo User-Agent; sem User-Agent também conta como robô)."""
    agente = request.META.get("HTTP_USER_AGENT", "")
    return not agente or bool(ROBOS.search(agente))


def _sal_do_dia(dia: date) -> str:
    """Sal aleatório do dia, guardado só no cache (some em 2 dias): o hash não pode ser refeito depois."""
    chave = f"estat:sal:{dia:%Y%m%d}"
    return cache.get_or_set(chave, secrets.token_hex(16), timeout=2 * 24 * 3600)


def _segundos_ate_o_fim_do_dia(agora: datetime) -> int:
    """Validade das marcas do dia (no fuso do site)."""
    amanha = timezone.localdate(agora) + timedelta(days=1)
    fim = timezone.make_aware(datetime.combine(amanha, time.min))
    return max(int((fim - agora).total_seconds()), 60)


def assinatura_do_visitante(request: HttpRequest, dia: date) -> str:
    """Hash do dia para o visitante (IP + navegador + sal do dia). Nunca é gravado no banco."""
    ip = request.META.get("REMOTE_ADDR", "")
    agente = request.META.get("HTTP_USER_AGENT", "")
    return hashlib.sha256(f"{_sal_do_dia(dia)}|{ip}|{agente}".encode()).hexdigest()[:32]


def _somar(anuncio_id: int, dia: date, evento: str) -> None:
    """+1 no total do dia, sem corrida (UPDATE com F(); cria a linha se for a primeira do dia)."""
    linhas = EstatisticaDiaria.objects.filter(anuncio_id=anuncio_id, dia=dia)
    if linhas.update(**{evento: F(evento) + 1}):
        return
    try:
        with transaction.atomic():
            EstatisticaDiaria.objects.create(anuncio_id=anuncio_id, dia=dia, **{evento: 1})
    except IntegrityError:  # outro acesso criou a linha no mesmo instante
        linhas.update(**{evento: F(evento) + 1})


def registrar(request: HttpRequest, anuncio: Anuncio, evento: str) -> bool:
    """Conta o evento se for de gente, não for o dono e for a primeira vez do visitante no dia.

    Devolve True se contou. Não levanta erro: estatística nunca derruba a página.
    """
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconhecido: {evento}")
    if request.method not in ("GET", "POST") or e_robo(request):
        return False
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated and usuario.pk == anuncio.anunciante.usuario_id:
        return False
    agora = timezone.now()
    dia = timezone.localdate(agora)
    marca = f"estat:{evento}:{anuncio.pk}:{dia:%Y%m%d}:{assinatura_do_visitante(request, dia)}"
    if not cache.add(marca, 1, timeout=_segundos_ate_o_fim_do_dia(agora)):
        return False  # este visitante já contou hoje
    _somar(anuncio.pk, dia, evento)
    return True


def totais_por_anuncio(ids: list[int]) -> dict[int, dict[str, int]]:
    """Totais de sempre por anúncio: {id: {"visualizacoes": n, "cliques_whatsapp": n}}."""
    linhas = (
        EstatisticaDiaria.objects.filter(anuncio_id__in=ids)
        .values("anuncio_id")
        .annotate(visualizacoes=Sum("visualizacoes"), cliques_whatsapp=Sum("cliques_whatsapp"))
    )
    totais = {i: {VISUALIZACAO: 0, CLIQUE_WHATSAPP: 0} for i in ids}
    for linha in linhas:
        totais[linha["anuncio_id"]] = {
            VISUALIZACAO: linha["visualizacoes"] or 0,
            CLIQUE_WHATSAPP: linha["cliques_whatsapp"] or 0,
        }
    return totais


def totais_da_loja(anunciante_id: int, dias: int = 30) -> dict[str, int]:
    """Soma dos últimos `dias` dias (hoje incluído) de todos os anúncios da loja."""
    inicio = timezone.localdate() - timedelta(days=dias - 1)
    soma = EstatisticaDiaria.objects.filter(anuncio__anunciante_id=anunciante_id, dia__gte=inicio).aggregate(
        visualizacoes=Sum("visualizacoes"), cliques_whatsapp=Sum("cliques_whatsapp")
    )
    return {VISUALIZACAO: soma["visualizacoes"] or 0, CLIQUE_WHATSAPP: soma["cliques_whatsapp"] or 0}


def total_de_visualizacoes(anuncio: Anuncio) -> int:
    """Visualizações de sempre (mostradas na página do anúncio)."""
    return EstatisticaDiaria.objects.filter(anuncio=anuncio).aggregate(t=Sum("visualizacoes"))["t"] or 0
