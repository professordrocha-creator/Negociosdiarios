"""Testes das regras de planos.services: limite do plano (com concorrência), downgrade,
vencimento, atraso com carência (ligado à fatura vencida, Sprint 6) e pagamento manual."""

import threading
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone

from core.services import configuracao
from pagamentos.models import Fatura
from pagamentos.services import gerar_fatura, registrar_pagamento_manual
from pagamentos.tasks import rotina_de_cobranca
from planos.models import Assinatura, Periodicidade
from planos.services import (
    LimiteDoPlano,
    SemAssinaturaAtiva,
    aplicar_downgrade,
    assinatura_de,
    pode_publicar,
    processar_atrasos,
    proximo_vencimento,
    reservar_vaga,
)
from planos.sinais import assinatura_em_atraso, assinatura_regularizada

pytestmark = pytest.mark.django_db


# --- Dados iniciais -------------------------------------------------------------------------


def test_migration_cria_os_3_planos_com_os_valores_antigos(plano):
    """Os valores que estavam no settings viraram dados (e daqui em diante só mudam no admin)."""
    basico, profissional, premium = plano("basico"), plano("profissional"), plano("premium")

    assert (basico.limite_anuncios, basico.preco_mensal, basico.preco_anual) == (
        10,
        Decimal("49.90"),
        Decimal("499.00"),
    )
    assert (profissional.limite_anuncios, profissional.preco_mensal) == (25, Decimal("99.90"))
    assert (premium.limite_anuncios, premium.preco_anual) == (50, Decimal("1499.00"))
    assert basico.ordem < profissional.ordem < premium.ordem


def test_carencia_padrao_e_5_dias():
    """Valor configurável na Configuracao, padrão 5."""
    assert configuracao().carencia_dias == 5


# --- Limite do plano --------------------------------------------------------------------------


def test_pode_publicar_sem_assinatura_e_falso(criar_anunciante):
    """Sem plano, não publica."""
    assert not pode_publicar(criar_anunciante("a@exemplo.com", "Loja A"), uso=0)


def test_pode_publicar_respeita_o_limite(assinante):
    """Básico = 10: com 9 em uso cabe mais um; com 10, não."""
    loja = assinante()

    assert pode_publicar(loja, uso=9)
    assert not pode_publicar(loja, uso=10)


def test_pode_publicar_em_atraso_e_falso(assinante):
    """Assinatura em atraso não publica, mesmo com vaga."""
    loja = assinante()
    Assinatura.objects.filter(anunciante=loja).update(situacao=Assinatura.Situacao.EM_ATRASO)

    assert not pode_publicar(loja, uso=0)


def test_reservar_vaga_publica_quando_cabe(assinante):
    """Cabe no plano: chama publicar() e devolve o que ela devolve."""
    loja = assinante()

    assert reservar_vaga(loja, contar=lambda a: 3, publicar=lambda: "publicado") == "publicado"


def test_reservar_vaga_no_limite_nao_publica(assinante):
    """No limite: LimiteDoPlano e publicar() nunca é chamada."""
    loja = assinante()
    chamadas = []

    with pytest.raises(LimiteDoPlano, match="10 anúncios"):
        reservar_vaga(loja, contar=lambda a: 10, publicar=lambda: chamadas.append(1))
    assert chamadas == []


@pytest.mark.parametrize("situacao", [Assinatura.Situacao.EM_ATRASO, Assinatura.Situacao.CANCELADA])
def test_reservar_vaga_sem_assinatura_ativa(assinante, situacao):
    """Em atraso ou cancelada: SemAssinaturaAtiva."""
    loja = assinante()
    Assinatura.objects.filter(anunciante=loja).update(situacao=situacao)

    with pytest.raises(SemAssinaturaAtiva):
        reservar_vaga(loja, contar=lambda a: 0, publicar=lambda: None)


def test_reservar_vaga_sem_assinatura(criar_anunciante):
    """Sem assinatura nenhuma: SemAssinaturaAtiva."""
    with pytest.raises(SemAssinaturaAtiva):
        reservar_vaga(criar_anunciante("a@exemplo.com", "Loja A"), contar=lambda a: 0, publicar=lambda: None)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reservar_vaga_dois_cliques_ao_mesmo_tempo_so_um_publica(assinante, plano):
    """Concorrência: limite 1, duas publicações simultâneas (cada uma com sua conexão).

    Sem a trava, as duas contariam 0 e publicariam. Com select_for_update, a segunda espera
    a primeira terminar, conta 1 e recebe LimiteDoPlano.
    """
    loja = assinante()
    basico = plano("basico")
    basico.limite_anuncios = 1
    basico.save()
    publicados: list[str] = []
    erros: list[Exception] = []
    largada = threading.Barrier(2)

    def publicar_lento(nome: str):
        time.sleep(0.3)  # janela em que, sem trava, a outra thread também contaria 0
        publicados.append(nome)

    def tentar(nome: str):
        try:
            largada.wait()
            reservar_vaga(loja, contar=lambda a: len(publicados), publicar=lambda: publicar_lento(nome))
        except LimiteDoPlano as erro:
            erros.append(erro)
        finally:
            connection.close()

    threads = [threading.Thread(target=tentar, args=(n,)) for n in ("primeiro", "segundo")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(publicados) == 1
    assert len(erros) == 1


# --- Downgrade --------------------------------------------------------------------------------


def test_downgrade_pausa_os_nao_escolhidos(assinante, plano):
    """Premium → Básico: mantém os escolhidos (até 10) e pausa o resto; nada é apagado."""
    loja = assinante(slug_plano="premium")
    assinatura = assinatura_de(loja)
    anuncios = list(range(1, 16))  # 15 anúncios
    pausados_recebidos = []

    pausados = aplicar_downgrade(
        assinatura, plano("basico"), anuncios, manter=range(1, 11), pausar=pausados_recebidos.append
    )

    assert pausados == set(range(11, 16))
    assert pausados_recebidos == [set(range(11, 16))]
    assert assinatura.plano.slug == "basico"
    assert "Downgrade" in assinatura.history.order_by("-history_id").first().history_change_reason


def test_downgrade_recusa_escolher_mais_que_o_novo_limite(assinante, plano):
    """Escolher 11 para o Básico (10): erro, nada muda e nada é pausado."""
    loja = assinante(slug_plano="premium")
    chamadas = []

    with pytest.raises(ValueError, match="no máximo 10"):
        aplicar_downgrade(
            assinatura_de(loja), plano("basico"), range(1, 16), manter=range(1, 12), pausar=chamadas.append
        )
    assert chamadas == [] and assinatura_de(loja).plano.slug == "premium"


def test_downgrade_recusa_anuncio_de_outra_loja(assinante, plano):
    """Só dá para manter ids que são da própria loja (sem IDOR)."""
    loja = assinante(slug_plano="premium")

    with pytest.raises(ValueError, match="própria loja"):
        aplicar_downgrade(
            assinatura_de(loja), plano("basico"), [1, 2], manter=[1, 999], pausar=lambda ids: None
        )


def test_downgrade_dentro_do_limite_nao_pausa(assinante, plano):
    """Com menos anúncios que o novo limite, troca o plano sem pausar nada."""
    loja = assinante(slug_plano="premium")
    chamadas = []

    assert (
        aplicar_downgrade(assinatura_de(loja), plano("basico"), [1, 2], manter=[1, 2], pausar=chamadas.append)
        == set()
    )
    assert chamadas == []


# --- Vencimento -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "periodicidade", "esperado"),
    [
        (date(2026, 1, 15), Periodicidade.MENSAL, date(2026, 2, 15)),
        (date(2026, 1, 31), Periodicidade.MENSAL, date(2026, 2, 28)),
        (date(2026, 12, 10), Periodicidade.MENSAL, date(2027, 1, 10)),
        (date(2028, 2, 29), Periodicidade.ANUAL, date(2029, 2, 28)),
        (date(2026, 5, 1), Periodicidade.ANUAL, date(2027, 5, 1)),
    ],
)
def test_proximo_vencimento(data, periodicidade, esperado):
    """Um mês ou um ano depois; dia que não existe cai no último dia do mês."""
    assert proximo_vencimento(data, periodicidade) == esperado


# --- Atraso e carência ------------------------------------------------------------------------


def vencer(loja, dias_atras: int):
    """Põe o vencimento da assinatura `dias_atras` dias no passado, com a fatura desse ciclo sem pagar."""
    Assinatura.objects.filter(anunciante=loja).update(
        vencimento=timezone.localdate() - timedelta(days=dias_atras)
    )
    gerar_fatura(assinatura_de(loja), avisar=False)


def test_dentro_da_carencia_continua_ativa(assinante):
    """Vencida há 5 dias (carência 5): ainda ativa, sem e-mail."""
    loja = assinante()
    vencer(loja, 5)

    assert processar_atrasos() == 0
    assert assinatura_de(loja).situacao == Assinatura.Situacao.ATIVA
    assert mail.outbox == []


def test_depois_da_carencia_vira_em_atraso_avisa_e_dispara_sinal(assinante):
    """Vencida há 6 dias: em_atraso, sinal para pausar os anúncios e e-mail ao anunciante."""
    loja = assinante()
    vencer(loja, 6)
    recebidos = []

    def ouvir(sender, assinatura, **kwargs):
        recebidos.append(assinatura.anunciante_id)

    assinatura_em_atraso.connect(ouvir)
    try:
        assert processar_atrasos() == 1
    finally:
        assinatura_em_atraso.disconnect(ouvir)

    assinatura = assinatura_de(loja)
    assert assinatura.situacao == Assinatura.Situacao.EM_ATRASO
    assert recebidos == [loja.pk]
    assert mail.outbox[0].to == ["loja@exemplo.com"]
    assert "pausados" in mail.outbox[0].body.lower() and "nada foi apagado" in mail.outbox[0].body
    assert "carência" in assinatura.history.order_by("-history_id").first().history_change_reason


def test_carencia_vem_da_configuracao(assinante):
    """Mudar a carência no admin muda a regra (nada fixo no código)."""
    config = configuracao()
    config.carencia_dias = 10
    config.save()
    loja = assinante()
    vencer(loja, 8)

    assert processar_atrasos() == 0
    vencer(loja, 11)
    assert processar_atrasos() == 1


def test_atraso_nao_reprocessa_quem_ja_esta_em_atraso(assinante):
    """Rodar a tarefa de novo não manda outro e-mail."""
    loja = assinante()
    vencer(loja, 20)
    processar_atrasos()

    assert processar_atrasos() == 0
    assert len(mail.outbox) == 1


def test_tarefa_diaria_chama_o_processamento(assinante, settings):
    """A rotina de cobrança do Celery beat roda o atraso e está agendada."""
    loja = assinante()
    vencer(loja, 30)

    assert rotina_de_cobranca.delay().get()["em_atraso"] == 1
    assert settings.CELERY_BEAT_SCHEDULE["cobranca"]["task"] == "pagamentos.tasks.rotina_de_cobranca"


def test_sem_fatura_a_pagar_nao_entra_em_atraso(assinante):
    """O atraso vem da fatura: vencida mas paga, ou com comprovante aguardando, não pausa."""
    loja = assinante()
    vencer(loja, 20)
    Fatura.objects.update(situacao=Fatura.Situacao.AGUARDANDO)

    assert processar_atrasos() == 0
    Fatura.objects.update(situacao=Fatura.Situacao.PAGA)
    assert processar_atrasos() == 0
    Fatura.objects.update(situacao=Fatura.Situacao.VENCIDA)
    assert processar_atrasos() == 1


# --- Pagamento --------------------------------------------------------------------------------


def test_pagamento_em_dia_empurra_o_vencimento(assinante):
    """Pago antes de vencer: o próximo vencimento conta a partir do vencimento atual."""
    loja = assinante()
    assinatura = assinatura_de(loja)
    vencimento = assinatura.vencimento

    fatura = registrar_pagamento_manual(assinatura, None, "Pix 123")

    assinatura.refresh_from_db()
    assert assinatura.vencimento == proximo_vencimento(vencimento, Periodicidade.MENSAL)
    assert (
        assinatura.history.order_by("-history_id").first().history_change_reason
        == f"Pagamento registrado: {fatura.codigo} (Pix 123)"
    )
    assert (fatura.situacao, fatura.forma, fatura.competencia) == ("paga", "outro", vencimento)


def test_pagamento_em_atraso_reativa_e_dispara_sinal(assinante):
    """Pagou: volta a ativa, vencimento a partir do VENCIMENTO ORIGINAL (não do dia do pagamento) e sinal
    para reativar os anúncios."""
    loja = assinante()
    vencer(loja, 20)
    processar_atrasos()
    assinatura = assinatura_de(loja)
    recebidos = []

    def ouvir(sender, assinatura, **kwargs):
        recebidos.append(assinatura.pk)

    assinatura_regularizada.connect(ouvir)
    try:
        registrar_pagamento_manual(assinatura, None, "Comprovante 456")
    finally:
        assinatura_regularizada.disconnect(ouvir)

    assinatura.refresh_from_db()

    assert assinatura.situacao == Assinatura.Situacao.ATIVA
    original = timezone.localdate() - timedelta(days=20)
    assert assinatura.vencimento == proximo_vencimento(original, Periodicidade.MENSAL)
    assert recebidos == [assinatura.pk]


def test_pagamento_exige_motivo(assinante):
    """Baixa manual sem motivo/comprovante é recusada."""
    with pytest.raises(ValueError, match="motivo"):
        registrar_pagamento_manual(assinatura_de(assinante()), None, "  ")
