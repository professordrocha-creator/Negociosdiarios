"""Regras das denúncias de anúncio (Sprint 7B parte 2; docs/LGPD.md, docs/SEGURANCA.md).

- Envio sem login: anúncio visível, honeypot (na view), limite por visitante por dia (resumo do dia com sal
  aleatório, como nas estatísticas: nenhum IP gravado). A mesma origem denunciando o mesmo anúncio no mesmo
  dia não cria outra denúncia.
- Pausa automática: X denúncias de golpe pendentes, de origens diferentes (`Configuracao`, padrão 3),
  tiram o anúncio do ar "em revisão" (o anunciante não reativa) e avisam a equipe e o anunciante.
- Decisão da equipe (vale para todas as denúncias pendentes do anúncio): aceitar pausando (o anunciante
  corrige e reativa) ou removendo (exclusão lógica), com o motivo por e-mail ao anunciante; ou descartar
  (se estava em revisão, volta ao ar). O anunciante nunca recebe quem denunciou, o e-mail ou o texto.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from anuncios.models import Anuncio
from core.services import configuracao, enviar_email_modelo
from moderacao.models import Denuncia

if TYPE_CHECKING:
    from django.http import HttpRequest

    from contas.models import Usuario

logger = logging.getLogger(__name__)

Situacao = Anuncio.Situacao
PausadoPor = Anuncio.PausadoPor


class LimiteDeDenuncias(Exception):
    """Este visitante já mandou o máximo de denúncias de hoje."""


def origem_do_visitante(request: HttpRequest) -> str:
    """Resumo do visitante no dia (IP + navegador + sal do dia, só no cache). Nunca o IP."""
    from estatisticas.services import assinatura_do_visitante

    return assinatura_do_visitante(request, timezone.localdate())


def destinatarios_moderacao() -> list[str]:
    """Quem recebe os avisos de denúncia: superusuários e os grupos Moderador e Administrador."""
    Usuario = get_user_model()
    emails = list(
        Usuario.objects.filter(is_active=True, is_staff=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=["Moderador", "Administrador"]))
        .values_list("email", flat=True)
        .distinct()
    )
    return emails or [configuracao().email_contato]


def denunciar(anuncio: Anuncio, motivo: str, texto: str, email: str, origem: str) -> Denuncia:
    """Registra a denúncia (ou devolve a que esta origem já fez hoje para este anúncio) e confere a pausa.

    Levanta LimiteDeDenuncias se a origem passou do limite do dia (`Configuracao.denuncias_por_dia`).
    """
    hoje = timezone.localdate()
    do_dia = Denuncia.objects.filter(origem=origem, criado_em__date=hoje)
    repetida = do_dia.filter(anuncio=anuncio).first()
    if repetida:
        return repetida
    if do_dia.count() >= configuracao().denuncias_por_dia:
        raise LimiteDeDenuncias("Você já enviou muitas denúncias hoje. Tente amanhã ou escreva para a gente.")
    denuncia = Denuncia.objects.create(
        anuncio=anuncio,
        motivo=motivo,
        texto=texto.strip(),
        email=email.strip(),
        origem=origem,
        demo=anuncio.demo,
    )
    if motivo == Denuncia.Motivo.GOLPE:
        pausar_se_golpe(anuncio)
    return denuncia


def origens_de_golpe(anuncio: Anuncio) -> int:
    """Quantas origens diferentes têm denúncia de golpe pendente neste anúncio."""
    return (
        anuncio.denuncias.filter(motivo=Denuncia.Motivo.GOLPE, situacao=Denuncia.Situacao.PENDENTE)
        .values("origem")
        .distinct()
        .count()
    )


def pausar_se_golpe(anuncio: Anuncio) -> bool:
    """Atingiu o limite de denúncias de golpe: tira do ar "em revisão" e avisa equipe e anunciante."""
    limite = configuracao().denuncias_golpe_para_pausar
    with transaction.atomic():
        anuncio = Anuncio.objects.select_for_update().get(pk=anuncio.pk)
        if anuncio.situacao != Situacao.PUBLICADO or origens_de_golpe(anuncio) < limite:
            return False
        anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, PausadoPor.DENUNCIA
        anuncio._change_reason = f"Em revisão: {limite} ou mais denúncias de golpe."
        anuncio.save(update_fields=["situacao", "pausado_por", "atualizado_em"])
    enviar_email_modelo(
        "denuncia_pausa_equipe",
        f"Anúncio {anuncio.codigo} saiu do ar: denúncias de golpe",
        destinatarios_moderacao(),
        {
            "anuncio": anuncio,
            "limite": limite,
            "link_admin": settings.SITE_URL
            + reverse("admin:moderacao_denuncia_changelist")
            + f"?q={anuncio.codigo}",
        },
    )
    enviar_email_modelo(
        "denuncia_em_revisao",
        f"Seu anúncio {anuncio.codigo} está em revisão",
        [anuncio.anunciante.usuario.email],
        {"anuncio": anuncio},
    )
    logger.info("Anúncio id=%s pausado por denúncias de golpe.", anuncio.pk)
    return True


def _pendentes(denuncia: Denuncia):
    """Todas as denúncias pendentes do mesmo anúncio (a decisão é sobre o anúncio)."""
    return Denuncia.objects.filter(anuncio_id=denuncia.anuncio_id, situacao=Denuncia.Situacao.PENDENTE)


def _registrar_decisao(denuncias, por, situacao: str, acao: str, motivo: str) -> int:
    """Grava a decisão em cada denúncia (com histórico)."""
    agora, total = timezone.now(), 0
    for item in denuncias:
        item.situacao, item.acao, item.motivo_decisao = situacao, acao, motivo
        item.decidido_por, item.decidido_em = por, agora
        item._history_user = por
        item._change_reason = f"Denúncia {item.get_situacao_display().lower()}."
        item.save()
        total += 1
    return total


def aceitar(denuncia: Denuncia, por: Usuario | None, acao: str, motivo: str) -> Anuncio:
    """Aceita as denúncias pendentes do anúncio: pausa (o anunciante corrige e reativa) ou remove (exclusão
    lógica). Motivo obrigatório: vai ao anunciante por e-mail, sem nada de quem denunciou."""
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("Escreva o motivo: ele vai para o anunciante (sem dizer quem denunciou).")
    if acao not in Denuncia.Acao.values:
        raise ValueError("Escolha pausar ou remover.")
    with transaction.atomic():
        anuncio = Anuncio.objects.select_for_update().get(pk=denuncia.anuncio_id)
        if denuncia.situacao != Denuncia.Situacao.PENDENTE:
            raise ValueError(f"A denúncia de {anuncio.codigo} já foi decidida.")
        if acao == Denuncia.Acao.REMOVER:
            if anuncio.situacao != Situacao.REMOVIDO:
                anuncio.situacao, anuncio.removido_em = Situacao.REMOVIDO, timezone.now()
        elif anuncio.situacao in (Situacao.PUBLICADO, Situacao.PAUSADO, Situacao.EM_MODERACAO):
            anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, PausadoPor.MODERACAO
        anuncio.motivo_moderacao, anuncio.moderado_por = motivo, por
        anuncio._history_user = por
        anuncio._change_reason = f"Denúncia aceita ({Denuncia.Acao(acao).label.lower()})."
        anuncio.save()
        _registrar_decisao(_pendentes(denuncia), por, Denuncia.Situacao.ACEITA, acao, motivo)
    enviar_email_modelo(
        "denuncia_aceita",
        f"Seu anúncio {anuncio.codigo} foi {'removido' if acao == Denuncia.Acao.REMOVER else 'pausado'}",
        [anuncio.anunciante.usuario.email],
        {
            "anuncio": anuncio,
            "removido": acao == Denuncia.Acao.REMOVER,
            "motivo": motivo,
            "link_painel": settings.SITE_URL + reverse("anunciantes:painel"),
        },
    )
    return anuncio


def descartar(denuncia: Denuncia, por: Usuario | None, motivo: str = "") -> Anuncio:
    """Descarta as denúncias pendentes do anúncio; se ele estava "em revisão", volta ao ar (ou expirado)."""
    with transaction.atomic():
        anuncio = Anuncio.objects.select_for_update().get(pk=denuncia.anuncio_id)
        if denuncia.situacao != Denuncia.Situacao.PENDENTE:
            raise ValueError(f"A denúncia de {anuncio.codigo} já foi decidida.")
        _registrar_decisao(_pendentes(denuncia), por, Denuncia.Situacao.DESCARTADA, "", motivo.strip())
        if anuncio.situacao == Situacao.PAUSADO and anuncio.pausado_por == PausadoPor.DENUNCIA:
            vencido = anuncio.expira_em is not None and anuncio.expira_em <= timezone.now()
            anuncio.situacao = Situacao.EXPIRADO if vencido else Situacao.PUBLICADO
            anuncio.pausado_por = ""
            anuncio._history_user = por
            anuncio._change_reason = "Denúncias descartadas: anúncio de volta."
            anuncio.save()
    return anuncio


def limpar_denuncias_antigas(hoje=None) -> int:
    """Denúncias decididas há mais que a guarda (`Configuracao.retencao_denuncia_dias`): apaga o e-mail e os
    detalhes (também no histórico). Fica o registro: anúncio, motivo, decisão e datas."""
    hoje = hoje or timezone.localdate()
    limite = hoje - timedelta(days=configuracao().retencao_denuncia_dias)
    antigas = Denuncia.objects.exclude(situacao=Denuncia.Situacao.PENDENTE).filter(
        decidido_em__date__lt=limite
    )
    antigas = antigas.exclude(email="", texto="")
    ids = list(antigas.values_list("pk", flat=True))
    Denuncia.objects.filter(pk__in=ids).update(email="", texto="")
    Denuncia.history.filter(id__in=ids).update(email="", texto="")
    return len(ids)


# --- Dados de demonstração --------------------------------------------------------------------------


def criar_denuncias_demo() -> int:
    """Duas denúncias fictícias pendentes em anúncios demo (um "golpe" e um "já vendido")."""
    apagar_denuncias_demo()
    anuncios = list(Anuncio.objects.filter(demo=True, situacao=Situacao.PUBLICADO).order_by("pk")[:2])
    dados = [
        (
            Denuncia.Motivo.GOLPE,
            "Pediram sinal por Pix antes da visita (demonstração).",
            "denunciante@demo.invalid",
        ),
        (Denuncia.Motivo.VENDIDO, "Liguei e disseram que já foi vendido (demonstração).", ""),
    ]
    for indice, (anuncio, (motivo, texto, email)) in enumerate(zip(anuncios, dados, strict=False)):
        Denuncia.objects.create(
            anuncio=anuncio, motivo=motivo, texto=texto, email=email, origem=f"demo{indice}", demo=True
        )
    return len(anuncios)


def apagar_denuncias_demo() -> int:
    """Apaga as denúncias de demonstração e as de anúncios demo, com o histórico."""
    quantas, _ = Denuncia.objects.filter(Q(demo=True) | Q(anuncio__demo=True)).delete()
    Denuncia.history.filter(demo=True).delete()
    return quantas
