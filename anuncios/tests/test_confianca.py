"""Testes da publicação por confiança (lote 3A; Configurações do site): loja aprovada e em dia publica direto,
corretor autônomo passa pela fila até ter N aprovados, a confiança se perde com remoção por golpe ou
suspensão, denúncia continua pausando, edição de campos sensíveis fica no histórico (ou volta à fila sem
confiança) e a chave geral volta à regra antiga."""

from decimal import Decimal

import pytest
from django.core import mail

from anunciantes import services as anunciantes
from anunciantes.models import Anunciante
from anuncios import services
from anuncios.models import Anuncio
from core.services import configuracao
from moderacao import services as moderacao
from moderacao.models import Denuncia
from planos.services import assinatura_de

pytestmark = pytest.mark.django_db

Situacao = Anuncio.Situacao


def mudar_config(**valores):
    """Altera as Configurações do site (como no admin)."""
    config = configuracao()
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    config.save()


def corretor(loja):
    """Corretor autônomo (pessoa física) com plano ativo."""
    return loja("corretor@exemplo.com", "Corretor Zé", tipo=Anunciante.Tipo.CORRETOR_AUTONOMO)


# --- Regras de publicação ------------------------------------------------------------------------------


def test_padrao_ligado_e_seguro():
    """Padrão: confiança ligada e corretor autônomo com 1 anúncio aprovado antes de publicar direto."""
    config = configuracao()
    assert config.confianca_ativa is True and config.confianca_aprovados_pessoa_fisica == 1


def test_loja_aprovada_e_em_dia_publica_direto(loja, imovel):
    """Loja (pessoa jurídica) aprovada e em dia: até o primeiro anúncio vai direto ao ar, sem fila."""
    anuncio = imovel(loja())

    assert services.enviar_para_publicacao(anuncio) == Situacao.PUBLICADO
    assert not any("moderação" in m.subject.lower() for m in mail.outbox)


def test_loja_sem_verificacao_vai_para_a_fila(loja):
    """Loja sem a verificação aprovada (situação diferente de "ativo") nunca tem confiança."""
    anunciante = loja()
    for status in (Anunciante.Status.PENDENTE, Anunciante.Status.SUSPENSO):
        anunciante.status = status
        assert services.precisa_moderacao(anunciante)


def test_loja_com_fatura_vencida_vai_para_a_fila(loja, imovel):
    """Plano em dia é parte da confiança: com fatura vencida, o anúncio novo vai para a fila."""
    from pagamentos.models import Fatura
    from pagamentos.services import gerar_fatura

    anunciante = loja()
    assinatura = assinatura_de(anunciante)
    fatura = gerar_fatura(assinatura, hoje=assinatura.vencimento, avisar=False)
    Fatura.objects.filter(pk=fatura.pk).update(situacao=Fatura.Situacao.VENCIDA)

    assert services.enviar_para_publicacao(imovel(anunciante)) == Situacao.EM_MODERACAO


def test_pessoa_fisica_fila_ate_n_aprovados(loja, imovel):
    """Corretor autônomo: 0 aprovados → fila; depois do 1º aprovado (N=1) → publica direto."""
    anunciante = corretor(loja)
    primeiro = imovel(anunciante)
    assert services.enviar_para_publicacao(primeiro) == Situacao.EM_MODERACAO

    services.aprovar(primeiro, None)
    segundo = imovel(anunciante, "Apartamento 2 quartos no Centro")
    assert services.enviar_para_publicacao(segundo) == Situacao.PUBLICADO


def test_numero_de_aprovados_configuravel(loja, imovel):
    """Com N=2, o segundo ainda vai para a fila; com N=0, nem o primeiro."""
    mudar_config(confianca_aprovados_pessoa_fisica=2)
    anunciante = corretor(loja)
    primeiro = imovel(anunciante)
    services.enviar_para_publicacao(primeiro)
    services.aprovar(primeiro, None)
    assert (
        services.enviar_para_publicacao(imovel(anunciante, "Segundo anúncio de casa"))
        == Situacao.EM_MODERACAO
    )

    mudar_config(confianca_aprovados_pessoa_fisica=0)
    novo = loja("c2@exemplo.com", "Corretor Dois", tipo=Anunciante.Tipo.CORRETOR_AUTONOMO)
    assert not services.precisa_moderacao(novo)


def test_chave_desligada_volta_a_regra_antiga(loja, imovel):
    """Confiança desligada: "só o primeiro" vale para todos (o primeiro da loja vai para a fila)."""
    mudar_config(confianca_ativa=False)
    assert services.enviar_para_publicacao(imovel(loja())) == Situacao.EM_MODERACAO


def test_todos_e_nenhum_valem_sobre_a_confianca(loja, imovel):
    """ "Todos" manda até a loja de confiança para a fila; "Nenhum" publica até quem não tem."""
    mudar_config(moderacao="todos")
    assert services.enviar_para_publicacao(imovel(loja())) == Situacao.EM_MODERACAO
    mudar_config(moderacao="nenhum")
    assert not services.precisa_moderacao(corretor(loja))


# --- Denúncias e perda de confiança -----------------------------------------------------------------------


def test_denuncia_pausa_mesmo_com_confianca(loja, imovel):
    """Publicado direto pela confiança, o anúncio continua sujeito à pausa automática por golpe."""
    anuncio = imovel(loja())
    services.enviar_para_publicacao(anuncio)
    for origem in ("a" * 32, "b" * 32, "c" * 32):
        moderacao.denunciar(anuncio, Denuncia.Motivo.GOLPE, "", "", origem)

    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PAUSADO and anuncio.pausado_por == Anuncio.PausadoPor.DENUNCIA


def test_remocao_por_golpe_tira_a_confianca(loja, imovel):
    """Denúncia de golpe aceita com "remover": a loja perde a confiança; o próximo anúncio vai para a fila."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    services.enviar_para_publicacao(anuncio)
    denuncia = moderacao.denunciar(anuncio, Denuncia.Motivo.GOLPE, "Pediu sinal adiantado", "", "x" * 32)

    moderacao.aceitar(denuncia, None, Denuncia.Acao.REMOVER, "Golpe confirmado.")

    anunciante.refresh_from_db()
    assert anunciante.confianca_retirada_em is not None and "golpe" in anunciante.motivo_confianca
    assert (
        services.enviar_para_publicacao(imovel(anunciante, "Outra casa com piscina")) == Situacao.EM_MODERACAO
    )


def test_remocao_por_outro_motivo_nao_tira_a_confianca(loja, imovel):
    """Remover por "já vendido" não é golpe: a confiança fica."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    services.enviar_para_publicacao(anuncio)
    denuncia = moderacao.denunciar(anuncio, Denuncia.Motivo.VENDIDO, "", "", "y" * 32)
    moderacao.aceitar(denuncia, None, Denuncia.Acao.REMOVER, "Já vendido.")

    anunciante.refresh_from_db()
    assert anunciante.confianca_retirada_em is None


def test_suspensao_tira_e_a_equipe_devolve(loja, imovel):
    """Suspensa e aprovada de novo: fila até a equipe devolver a confiança."""
    anunciante = loja()
    anunciantes.suspender(anunciante, None, "Documento vencido.")
    anunciante.refresh_from_db()
    anunciante.status = Anunciante.Status.ATIVO
    anunciante.save()
    assert services.precisa_moderacao(anunciante) and "suspensa" in anunciante.motivo_confianca

    anunciantes.devolver_confianca(anunciante, None)
    assert not services.precisa_moderacao(anunciante)


# --- Edição de campos sensíveis ---------------------------------------------------------------------------


def test_edicao_sensivel_com_confianca_fica_no_ar_e_no_historico(loja, imovel):
    """Com confiança: muda o preço e continua publicado; o histórico diz quais campos sensíveis mudaram."""
    anuncio = imovel(loja())
    services.enviar_para_publicacao(anuncio)

    services.atualizar_anuncio(anuncio, {"preco": Decimal("99000")})

    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO
    assert "Campos sensíveis: preço" in anuncio.history.order_by("-history_id").first().history_change_reason


def test_edicao_sensivel_sem_confianca_volta_para_a_fila(loja, imovel):
    """Sem confiança (retirada pela equipe): a mudança de tipo volta o anúncio para a fila; a de texto não."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    services.enviar_para_publicacao(anuncio)
    anunciantes.retirar_confianca(anunciante, "Teste")

    services.atualizar_anuncio(anuncio, {"descricao": "Casa reformada."})
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO

    services.atualizar_anuncio(anuncio, {}, {"tipo": "apartamento"})
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.EM_MODERACAO


def test_nenhum_publica_direto_so_com_plano_em_dia(loja, imovel, criar_anunciante):
    """Moderação "Nenhum": loja aprovada com plano em dia publica direto; sem plano ou com o plano vencido,
    não publica (nada muda no anúncio)."""
    from datetime import timedelta

    from django.utils import timezone

    from planos.services import SemAssinaturaAtiva

    mudar_config(moderacao="nenhum")
    em_dia = imovel(loja())
    assert services.enviar_para_publicacao(em_dia) == Situacao.PUBLICADO

    sem_plano = imovel(criar_anunciante("sem@exemplo.com", "Loja Sem Plano"))
    with pytest.raises(SemAssinaturaAtiva):
        services.enviar_para_publicacao(sem_plano)

    vencida = loja("vencida@exemplo.com", "Loja Vencida")
    assinatura = assinatura_de(vencida)
    assinatura.vencimento = timezone.localdate() - timedelta(days=1)
    assinatura.save()
    anuncio_vencido = imovel(vencida)
    with pytest.raises(SemAssinaturaAtiva):
        services.enviar_para_publicacao(anuncio_vencido)

    for anuncio in (sem_plano, anuncio_vencido):
        anuncio.refresh_from_db()
        assert anuncio.situacao == Situacao.RASCUNHO
