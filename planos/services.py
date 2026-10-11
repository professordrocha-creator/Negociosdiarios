"""Regras do app planos (ARQUITETURA §5): limite do plano, downgrade, atraso e pedidos de troca.

O app planos não conhece o modelo de anúncio (Sprint 3). Onde precisa contar, publicar ou
pausar anúncios, recebe funções de quem chama (`reservar_vaga`, `aplicar_downgrade`) ou
dispara sinais (`planos.sinais`) para o app de anúncios reagir.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from anunciantes.models import Anunciante
from core.services import configuracao, enviar_email_modelo
from planos.models import Assinatura, PedidoTrocaPlano, Periodicidade, Plano
from planos.sinais import assinatura_em_atraso, assinatura_regularizada

if TYPE_CHECKING:
    from contas.models import Usuario


class SemAssinaturaAtiva(Exception):
    """O anunciante não tem assinatura ativa (sem plano, em atraso ou cancelada)."""


class LimiteDoPlano(Exception):
    """O plano já está no limite de anúncios ativos."""


def planos_a_venda() -> QuerySet[Plano]:
    """Planos mostrados em /planos/ e em "Meu plano", na ordem do admin."""
    return Plano.objects.filter(ativo=True).order_by("ordem", "limite_anuncios")


def assinatura_de(anunciante: Anunciante) -> Assinatura | None:
    """A assinatura do anunciante, se houver."""
    return Assinatura.objects.filter(anunciante=anunciante).select_related("plano").first()


def uso_do_plano(anunciante: Anunciante) -> int:
    """Anúncios que contam no limite (publicados + em análise).

    Até a Sprint 3 só lojas demo têm anúncios (demo.json); a Sprint 3 troca o corpo desta
    função pela contagem no banco, sem mudar quem chama.
    """
    from anunciantes.services import anuncios_da_loja

    return len(anuncios_da_loja(anunciante))


# --- Limite do plano (regra 1) -------------------------------------------------------------


def pode_publicar(anunciante: Anunciante, uso: int | None = None) -> bool:
    """Resposta rápida para a tela (sem trava): tem assinatura ativa e vaga no plano?

    A decisão que vale é a de `reservar_vaga`, que trava a assinatura.
    """
    assinatura = assinatura_de(anunciante)
    if assinatura is None or assinatura.situacao != Assinatura.Situacao.ATIVA:
        return False
    return (uso_do_plano(anunciante) if uso is None else uso) < assinatura.plano.limite_anuncios


def reservar_vaga[T](
    anunciante: Anunciante, contar: Callable[[Assinatura], int], publicar: Callable[[], T]
) -> T:
    """Publica um anúncio só se couber no plano, sem corrida entre dois cliques ao mesmo tempo.

    Numa transação, trava a linha da assinatura (`select_for_update`): uma segunda publicação
    da mesma loja espera a primeira terminar e só então conta. `contar(assinatura)` devolve os
    anúncios que já ocupam o plano; `publicar()` grava o anúncio (Sprint 3: funções do app
    anuncios). Levanta SemAssinaturaAtiva ou LimiteDoPlano; nesses casos nada é publicado.
    """
    with transaction.atomic():
        assinatura = (
            Assinatura.objects.select_for_update()
            .select_related("plano")
            .filter(anunciante=anunciante)
            .first()
        )
        if assinatura is None or assinatura.situacao != Assinatura.Situacao.ATIVA:
            raise SemAssinaturaAtiva("Sem assinatura ativa: escolha um plano ou regularize o pagamento.")
        if contar(assinatura) >= assinatura.plano.limite_anuncios:
            raise LimiteDoPlano(
                f"O plano {assinatura.plano.nome} permite {assinatura.plano.limite_anuncios} "
                "anúncios ativos. Pause um anúncio ou troque de plano."
            )
        return publicar()


# --- Downgrade (regra 3) ------------------------------------------------------------------


def aplicar_downgrade(
    assinatura: Assinatura,
    plano_novo: Plano,
    anuncios: Iterable[int],
    manter: Iterable[int],
    pausar: Callable[[set[int]], None],
) -> set[int]:
    """Troca para um plano menor: o anunciante escolhe quais anúncios manter; o resto é pausado.

    `anuncios` são os ids que hoje ocupam o plano; `manter`, os escolhidos (no máximo o novo
    limite, e só dentre os dele); `pausar(ids)` pausa (nunca apaga) os demais. Tudo numa
    transação com a assinatura travada. Devolve os ids pausados.
    """
    todos, escolhidos = set(anuncios), set(manter)
    if not escolhidos <= todos:
        raise ValueError("Só é possível manter anúncios da própria loja.")
    if len(escolhidos) > plano_novo.limite_anuncios:
        raise ValueError(
            f"O plano {plano_novo.nome} permite {plano_novo.limite_anuncios} anúncios: "
            f"escolha no máximo {plano_novo.limite_anuncios} para manter."
        )
    with transaction.atomic():
        travada = Assinatura.objects.select_for_update().get(pk=assinatura.pk)
        pausados = todos - escolhidos
        if pausados:
            pausar(pausados)
        travada.plano = plano_novo
        travada._change_reason = f"Downgrade para {plano_novo.nome}: {len(pausados)} anúncio(s) pausado(s)."
        travada.save(update_fields=["plano", "atualizado_em"])
    assinatura.refresh_from_db()
    return pausados


# --- Vencimento, atraso e pagamento (regra 2) --------------------------------------------


def proximo_vencimento(data: date, periodicidade: str) -> date:
    """Um mês (ou um ano) depois. Dia 31 em mês curto cai no último dia do mês."""
    if periodicidade == Periodicidade.ANUAL:
        ano, mes = data.year + 1, data.month
    else:
        ano, mes = (data.year + 1, 1) if data.month == 12 else (data.year, data.month + 1)
    return date(ano, mes, min(data.day, calendar.monthrange(ano, mes)[1]))


def criar_assinatura(
    anunciante: Anunciante, plano: Plano, periodicidade: str, inicio: date | None = None
) -> Assinatura:
    """Assinatura nova (ou troca da existente) ativa, com vencimento no próximo período."""
    inicio = inicio or timezone.localdate()
    assinatura, _ = Assinatura.objects.update_or_create(
        anunciante=anunciante,
        defaults={
            "plano": plano,
            "periodicidade": periodicidade,
            "inicio": inicio,
            "vencimento": proximo_vencimento(inicio, periodicidade),
            "situacao": Assinatura.Situacao.ATIVA,
            "demo": anunciante.demo,  # loja demo: assinatura também some no apagar_dados_demo
        },
    )
    return assinatura


def processar_atrasos(hoje: date | None = None) -> int:
    """Tarefa diária: assinatura vencida há mais que a carência vira "em atraso".

    Carência em Configuracao.carencia_dias (padrão 5). Para cada uma: muda a situação,
    dispara `assinatura_em_atraso` (o app de anúncios pausa os anúncios; nunca apaga) e
    avisa o anunciante por e-mail. Devolve quantas mudaram.
    """
    hoje = hoje or timezone.localdate()
    limite = hoje - timedelta(days=configuracao().carencia_dias)
    vencidas = Assinatura.objects.filter(situacao=Assinatura.Situacao.ATIVA, vencimento__lt=limite)
    total = 0
    for assinatura in vencidas.select_related("anunciante__usuario", "plano"):
        assinatura.situacao = Assinatura.Situacao.EM_ATRASO
        assinatura._change_reason = f"Vencida em {assinatura.vencimento:%d/%m/%Y}; carência encerrada."
        assinatura.save(update_fields=["situacao", "atualizado_em"])
        assinatura_em_atraso.send(sender=Assinatura, assinatura=assinatura)
        enviar_email_modelo(
            "assinatura_em_atraso",
            "Sua assinatura está em atraso",
            [assinatura.anunciante.usuario.email],
            {"assinatura": assinatura, "link_plano": settings.SITE_URL + reverse("planos:meu_plano")},
        )
        total += 1
    return total


def registrar_pagamento(
    assinatura: Assinatura, por: Usuario | None, motivo: str, hoje: date | None = None
) -> Assinatura:
    """Pagamento recebido (por enquanto, baixa manual pela equipe; Pix na Sprint 6).

    Empurra o vencimento um período (a partir de hoje, se estava em atraso) e, se estava em
    atraso, volta a "ativa" e dispara `assinatura_regularizada` (o app de anúncios reativa).
    """
    if not motivo.strip():
        raise ValueError("Informe o motivo/comprovante da baixa manual.")
    hoje = hoje or timezone.localdate()
    estava_em_atraso = assinatura.situacao == Assinatura.Situacao.EM_ATRASO
    base = hoje if estava_em_atraso or assinatura.vencimento < hoje else assinatura.vencimento
    assinatura.vencimento = proximo_vencimento(base, assinatura.periodicidade)
    assinatura.situacao = Assinatura.Situacao.ATIVA
    assinatura._history_user = por
    assinatura._change_reason = f"Pagamento registrado: {motivo.strip()}"[:100]
    assinatura.save(update_fields=["vencimento", "situacao", "atualizado_em"])
    if estava_em_atraso:
        assinatura_regularizada.send(sender=Assinatura, assinatura=assinatura)
    return assinatura


# --- Pedidos de troca de plano ------------------------------------------------------------


def destinatarios_financeiro() -> list[str]:
    """Quem recebe pedidos de plano: superusuários e o grupo Financeiro (ou o e-mail de contato)."""
    Usuario = get_user_model()
    emails = list(
        Usuario.objects.filter(is_active=True, is_staff=True)
        .filter(Q(is_superuser=True) | Q(groups__name="Financeiro"))
        .values_list("email", flat=True)
        .distinct()
    )
    return emails or [configuracao().email_contato]


def pedir_troca(anunciante: Anunciante, plano_novo: Plano, periodicidade: str) -> PedidoTrocaPlano:
    """Registra o pedido de plano (assinar ou trocar) e avisa a equipe e o anunciante por e-mail.

    Só um pedido pendente por vez: um pedido novo substitui (recusa) o anterior. Pedir o
    mesmo plano e periodicidade que já tem não faz sentido e é recusado.
    """
    assinatura = assinatura_de(anunciante)
    if assinatura and assinatura.plano_id == plano_novo.pk and assinatura.periodicidade == periodicidade:
        raise ValueError("Você já está neste plano.")
    if not plano_novo.ativo:
        raise ValueError("Este plano não está mais à venda.")
    with transaction.atomic():
        PedidoTrocaPlano.objects.filter(
            anunciante=anunciante, status=PedidoTrocaPlano.Status.PENDENTE
        ).update(
            status=PedidoTrocaPlano.Status.RECUSADO,
            motivo="Substituído por um pedido mais novo.",
            decidido_em=timezone.now(),
        )
        pedido = PedidoTrocaPlano.objects.create(
            anunciante=anunciante,
            plano_atual=assinatura.plano if assinatura else None,
            plano_novo=plano_novo,
            periodicidade=periodicidade,
            demo=anunciante.demo,
        )
    contexto = {"pedido": pedido, "uso": uso_do_plano(anunciante)}
    enviar_email_modelo(
        "plano_pedido_equipe",
        "Pedido de plano aguardando aprovação",
        destinatarios_financeiro(),
        {
            **contexto,
            "link_admin": settings.SITE_URL
            + reverse("admin:planos_pedidotrocaplano_change", args=[pedido.pk]),
        },
    )
    enviar_email_modelo(
        "plano_pedido_recebido", "Recebemos seu pedido de plano", [anunciante.usuario.email], contexto
    )
    return pedido


def aprovar_pedido(pedido: PedidoTrocaPlano, por: Usuario | None) -> Assinatura:
    """Aplica o plano pedido e avisa o anunciante. Downgrade acima do novo limite precisa de escolha.

    Se o novo plano for menor que o uso atual, a aprovação para: o anunciante precisa escolher
    quais anúncios manter (`aplicar_downgrade`, tela da Sprint 3).
    """
    if pedido.status != PedidoTrocaPlano.Status.PENDENTE:
        raise ValueError("Este pedido já foi decidido.")
    uso = uso_do_plano(pedido.anunciante)
    if uso > pedido.plano_novo.limite_anuncios:
        raise ValueError(
            f"{pedido.anunciante}: tem {uso} anúncios e o plano {pedido.plano_novo.nome} permite "
            f"{pedido.plano_novo.limite_anuncios}. O anunciante precisa escolher quais manter antes."
        )
    with transaction.atomic():
        assinatura = assinatura_de(pedido.anunciante)
        if assinatura:  # troca: mantém o vencimento atual
            assinatura.plano = pedido.plano_novo
            assinatura.periodicidade = pedido.periodicidade
            assinatura._history_user = por
            assinatura._change_reason = f"Troca aprovada: pedido {pedido.pk}."
            assinatura.save(update_fields=["plano", "periodicidade", "atualizado_em"])
        else:  # primeiro plano
            assinatura = criar_assinatura(pedido.anunciante, pedido.plano_novo, pedido.periodicidade)
        pedido.status = PedidoTrocaPlano.Status.APROVADO
        pedido.decidido_por, pedido.decidido_em = por, timezone.now()
        pedido.save(update_fields=["status", "decidido_por", "decidido_em"])
    enviar_email_modelo(
        "plano_pedido_aprovado",
        "Seu plano foi atualizado",
        [pedido.anunciante.usuario.email],
        {
            "pedido": pedido,
            "assinatura": assinatura,
            "link_plano": settings.SITE_URL + reverse("planos:meu_plano"),
        },
    )
    return assinatura


def recusar_pedido(pedido: PedidoTrocaPlano, por: Usuario | None, motivo: str) -> PedidoTrocaPlano:
    """Recusa o pedido (motivo obrigatório) e avisa o anunciante com o motivo."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da recusa.")
    if pedido.status != PedidoTrocaPlano.Status.PENDENTE:
        raise ValueError("Este pedido já foi decidido.")
    pedido.status = PedidoTrocaPlano.Status.RECUSADO
    pedido.motivo = motivo.strip()
    pedido.decidido_por, pedido.decidido_em = por, timezone.now()
    pedido.save(update_fields=["status", "motivo", "decidido_por", "decidido_em"])
    enviar_email_modelo(
        "plano_pedido_recusado",
        "Seu pedido de plano foi recusado",
        [pedido.anunciante.usuario.email],
        {"pedido": pedido},
    )
    return pedido


# --- Dados de demonstração ---------------------------------------------------------------


def criar_assinaturas_demo(slugs_em_atraso: Iterable[str] = ()) -> int:
    """Uma assinatura para cada loja demo ATIVA, alternando planos e periodicidades; algumas em atraso.

    As em atraso vencem há mais que a carência e já ficam "em atraso". Idempotente.
    """
    planos = list(planos_a_venda())
    lojas = Anunciante.objects.filter(demo=True, status=Anunciante.Status.ATIVO).order_by("pk")
    hoje = timezone.localdate()
    atrasadas = set(slugs_em_atraso)
    for indice, loja in enumerate(lojas):
        plano = planos[indice % len(planos)]
        periodicidade = Periodicidade.ANUAL if indice % 2 else Periodicidade.MENSAL
        if loja.slug in atrasadas:
            inicio = hoje - timedelta(days=45)
            situacao, vencimento = (
                Assinatura.Situacao.EM_ATRASO,
                hoje - timedelta(days=configuracao().carencia_dias + 10),
            )
        else:
            inicio = hoje - timedelta(days=10)
            situacao, vencimento = Assinatura.Situacao.ATIVA, proximo_vencimento(inicio, periodicidade)
        Assinatura.objects.update_or_create(
            anunciante=loja,
            defaults={
                "plano": plano,
                "periodicidade": periodicidade,
                "inicio": inicio,
                "vencimento": vencimento,
                "situacao": situacao,
                "demo": True,
            },
        )
    return lojas.count()


def apagar_assinaturas_demo() -> int:
    """Apaga assinaturas e pedidos de demonstração, com o histórico. Devolve quantas assinaturas eram.

    Chamado pelo `core.services.apagar_dados_demo` antes de apagar os anunciantes demo.
    """
    with transaction.atomic():
        quantas = Assinatura.objects.filter(demo=True).count()
        PedidoTrocaPlano.objects.filter(Q(demo=True) | Q(anunciante__demo=True)).delete()
        Assinatura.objects.filter(Q(demo=True) | Q(anunciante__demo=True)).delete()
        Assinatura.history.filter(demo=True).delete()
    return quantas
