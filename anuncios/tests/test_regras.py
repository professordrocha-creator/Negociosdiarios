"""Testes das regras de anuncios.services: código, publicação dentro do limite (com concorrência),
moderação, pausa, renovação, expiração, exclusão lógica, pausa por atraso e downgrade."""

import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone

from anuncios import services
from anuncios.models import Anuncio
from anuncios.tasks import expirar_anuncios
from core.services import configuracao
from planos.models import Assinatura, Periodicidade, Plano
from planos.services import (
    LimiteDoPlano,
    SemAssinaturaAtiva,
    aprovar_pedido,
    assinatura_de,
    escolher_anuncios_para_manter,
    pedir_troca,
    processar_atrasos,
    registrar_pagamento,
    uso_do_plano,
)

pytestmark = pytest.mark.django_db

Situacao = Anuncio.Situacao


def mudar_config(**valores):
    """Altera a Configuracao (como no admin)."""
    config = configuracao()
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    config.save()


# --- Código e criação ------------------------------------------------------------------------


def test_codigo_publico_vem_do_id_e_vai_para_o_historico(loja, imovel):
    """ND-IM-00001…: nasce na primeira gravação, inclusive no histórico."""
    anuncio = imovel(loja())

    assert anuncio.codigo == f"ND-IM-{anuncio.pk:05d}"
    assert anuncio.history.last().codigo == anuncio.codigo
    assert anuncio.situacao == Situacao.RASCUNHO and anuncio.slug == "casa-3-quartos-com-area-gourmet"


def test_anuncio_de_loja_demo_nasce_demo(criar_anunciante, imovel):
    """Loja demo: anúncio demo (some no apagar_dados_demo)."""
    anunciante = criar_anunciante("demo@exemplo.com", "Loja Demo")
    anunciante.demo = True
    anunciante.save()

    assert imovel(anunciante, completo=False).demo


def test_pendencias_listam_o_que_falta(loja, imovel):
    """Sem descrição, ponto e foto: três pendências; "só o bairro" troca o ponto pelo bairro."""
    anuncio = imovel(loja(), completo=False)

    faltas = services.pendencias(anuncio)

    assert len(faltas) == 3
    anuncio.imovel.exibir_localizacao = "so_bairro"
    anuncio.imovel.save()
    assert any("bairro" in f for f in services.pendencias(anuncio))


def test_incompleto_nao_e_enviado(loja, imovel):
    """Enviar com pendências: erro e continua rascunho."""
    anuncio = imovel(loja(), completo=False)

    with pytest.raises(services.AnuncioIncompleto, match="foto"):
        services.enviar_para_publicacao(anuncio)
    assert Anuncio.objects.get(pk=anuncio.pk).situacao == Situacao.RASCUNHO


# --- Moderação ------------------------------------------------------------------------------


def test_primeiro_anuncio_vai_para_moderacao_e_avisa_a_equipe(loja, imovel):
    """Padrão "só o primeiro": em análise (conta no plano) e e-mail para a equipe."""
    anunciante = loja()
    anuncio = imovel(anunciante)

    assert services.enviar_para_publicacao(anuncio) == Situacao.EM_MODERACAO
    assert uso_do_plano(anunciante) == 1
    assert "moderação" in mail.outbox[0].subject.lower() and anuncio.codigo in mail.outbox[0].body


def test_depois_do_primeiro_aprovado_publica_direto_por_60_dias(loja, imovel):
    """Depois do primeiro aprovado, publicação direta com prazo da Configuracao (60 dias)."""
    anunciante = loja()
    primeiro = imovel(anunciante)
    services.enviar_para_publicacao(primeiro)
    services.aprovar(primeiro, None)
    segundo = imovel(anunciante, "Apartamento 2 quartos no Centro")

    assert services.enviar_para_publicacao(segundo) == Situacao.PUBLICADO
    assert segundo.expira_em - segundo.publicado_em == timedelta(days=60)


@pytest.mark.parametrize(
    ("regra", "esperado"), [("todos", Situacao.EM_MODERACAO), ("nenhum", Situacao.PUBLICADO)]
)
def test_moderacao_configuravel(loja, imovel, regra, esperado):
    """Configuracao.moderacao: todos passam pela equipe ou nenhum passa."""
    mudar_config(moderacao=regra)

    assert services.enviar_para_publicacao(imovel(loja())) == esperado


def test_aprovar_publica_e_avisa(loja, imovel):
    """Aprovado: publicado, prazo contando e e-mail para o anunciante."""
    anuncio = imovel(loja())
    services.enviar_para_publicacao(anuncio)
    mail.outbox.clear()

    services.aprovar(anuncio, None)

    assert anuncio.situacao == Situacao.PUBLICADO and anuncio.expira_em
    assert mail.outbox[0].to == ["loja@exemplo.com"] and "aprovado" in mail.outbox[0].body


def test_aprovar_com_assinatura_em_atraso_deixa_pausado(loja, imovel):
    """Aprovado durante o atraso: fica pausado por atraso (volta com o pagamento)."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    services.enviar_para_publicacao(anuncio)
    Assinatura.objects.filter(anunciante=anunciante).update(situacao=Assinatura.Situacao.EM_ATRASO)

    services.aprovar(anuncio, None)

    assert (anuncio.situacao, anuncio.pausado_por) == (Situacao.PAUSADO, "atraso")


def test_recusar_volta_para_rascunho_com_motivo(loja, imovel):
    """Recusa com motivo obrigatório: rascunho, motivo guardado e e-mail com o motivo."""
    anuncio = imovel(loja())
    services.enviar_para_publicacao(anuncio)
    mail.outbox.clear()

    with pytest.raises(ValueError, match="motivo"):
        services.recusar(anuncio, None, " ")
    services.recusar(anuncio, None, "Foto com placa de carro visível.")

    assert anuncio.situacao == Situacao.RASCUNHO
    assert anuncio.motivo_moderacao == "Foto com placa de carro visível."
    assert "placa de carro" in mail.outbox[0].body


def test_edicao_com_moderacao_de_todos_volta_para_analise(loja, publicado):
    """Com "todos", editar um publicado o devolve para a fila; com "só o primeiro", não."""
    anuncio = publicado(loja())
    services.atualizar_anuncio(anuncio, {"titulo": "Casa 3 quartos reformada"})
    assert anuncio.situacao == Situacao.PUBLICADO

    mudar_config(moderacao="todos")
    services.atualizar_anuncio(anuncio, {"titulo": "Casa 3 quartos reformada e pintada"})
    assert anuncio.situacao == Situacao.EM_MODERACAO


# --- Limite do plano ------------------------------------------------------------------------


def test_limite_do_plano_bloqueia_o_envio(loja, imovel, publicado):
    """Plano com 1 vaga ocupada: o segundo não é enviado e continua rascunho."""
    anunciante = loja(limite=1)
    publicado(anunciante)
    segundo = imovel(anunciante, "Apartamento 2 quartos no Centro")

    with pytest.raises(LimiteDoPlano):
        services.enviar_para_publicacao(segundo)
    assert Anuncio.objects.get(pk=segundo.pk).situacao == Situacao.RASCUNHO


def test_pausados_e_rascunhos_nao_contam_no_limite(loja, imovel, publicado):
    """Pausar libera a vaga; rascunho não ocupa."""
    anunciante = loja(limite=1)
    primeiro = publicado(anunciante)
    services.pausar(primeiro)
    segundo = imovel(anunciante, "Apartamento 2 quartos no Centro")

    assert services.enviar_para_publicacao(segundo) == Situacao.PUBLICADO
    assert services.contar_no_plano(anunciante) == 1


def test_sem_assinatura_nao_envia(criar_anunciante, imovel):
    """Loja sem plano: SemAssinaturaAtiva."""
    with pytest.raises(SemAssinaturaAtiva):
        services.enviar_para_publicacao(imovel(criar_anunciante("a@exemplo.com", "Loja Sem Plano")))


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_dois_envios_ao_mesmo_tempo_nao_passam_do_limite(loja, imovel):
    """Concorrência real: limite 1 e dois anúncios enviados ao mesmo tempo; só um entra."""
    anunciante = loja(limite=1)
    anuncios = [imovel(anunciante, f"Casa número {i} com quintal") for i in (1, 2)]
    resultados: list[str] = []
    largada = threading.Barrier(2)

    def enviar(anuncio):
        try:
            largada.wait()
            resultados.append(services.enviar_para_publicacao(Anuncio.objects.get(pk=anuncio.pk)))
        except LimiteDoPlano:
            resultados.append("limite")
        finally:
            connection.close()

    threads = [threading.Thread(target=enviar, args=(a,)) for a in anuncios]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert sorted(resultados) == sorted([Situacao.EM_MODERACAO, "limite"])
    assert services.contar_no_plano(anunciante) == 1


# --- Pausar, reativar, renovar, excluir, expirar -------------------------------------------


def test_pausar_e_reativar(loja, publicado):
    """Pausa pelo cliente e volta (com novo prazo)."""
    anuncio = publicado(loja())

    services.pausar(anuncio)
    assert (anuncio.situacao, anuncio.pausado_por) == (Situacao.PAUSADO, "cliente")
    services.reativar(anuncio)
    assert anuncio.situacao == Situacao.PUBLICADO


def test_reativar_respeita_o_limite(loja, imovel, publicado):
    """Pausou, publicou outro no lugar e o plano encheu: reativar é recusado."""
    anunciante = loja(limite=1)
    primeiro = publicado(anunciante)
    services.pausar(primeiro)
    services.enviar_para_publicacao(imovel(anunciante, "Apartamento 2 quartos no Centro"))

    with pytest.raises(LimiteDoPlano):
        services.reativar(primeiro)


def test_renovar_so_perto_de_expirar(loja, publicado):
    """Longe do prazo: recusa. Dentro do aviso (5 dias): mais 60 dias a partir de agora."""
    anuncio = publicado(loja())
    with pytest.raises(ValueError, match="perto da data"):
        services.renovar(anuncio)

    anuncio.expira_em = timezone.now() + timedelta(days=3)
    anuncio.save()
    services.renovar(anuncio)

    assert anuncio.expira_em > timezone.now() + timedelta(days=59)


def test_expirar_tira_do_ar_avisa_e_renovar_volta(loja, publicado):
    """Tarefa diária: prazo vencido → expirado + e-mail; Renovar devolve ao ar."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    Anuncio.objects.filter(pk=anuncio.pk).update(expira_em=timezone.now() - timedelta(minutes=1))
    mail.outbox.clear()

    assert expirar_anuncios.delay().get() == 1
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.EXPIRADO
    assert anuncio.codigo in mail.outbox[0].body and "Renovar" in mail.outbox[0].body
    assert services.contar_no_plano(anunciante) == 0

    services.renovar(anuncio)
    assert anuncio.situacao == Situacao.PUBLICADO


def test_validade_vem_da_configuracao(loja, imovel):
    """Mudar a validade no admin muda o prazo dos próximos."""
    mudar_config(expiracao_dias=30, moderacao="nenhum")
    anuncio = imovel(loja())

    services.enviar_para_publicacao(anuncio)

    assert anuncio.expira_em - anuncio.publicado_em == timedelta(days=30)


def test_excluir_e_logico(loja, publicado):
    """Excluir: some do painel, mas o registro e o histórico ficam."""
    anunciante = loja()
    anuncio = publicado(anunciante)

    services.excluir(anuncio)

    assert Anuncio.objects.filter(pk=anuncio.pk, situacao=Situacao.REMOVIDO).exists()
    assert not services.anuncios_do_dono(anunciante).exists()
    assert anuncio.history.first().history_change_reason == "Excluído pelo anunciante."


def test_excluir_o_primeiro_nao_reabre_a_moderacao(loja, publicado, imovel):
    """A regra "só o primeiro" olha se a loja JÁ teve anúncio publicado."""
    anunciante = loja()
    services.excluir(publicado(anunciante))

    assert not services.precisa_moderacao(anunciante)


# --- Atraso (sinais da Sprint 2) ------------------------------------------------------------


def atrasar(anunciante, dias: int = 30):
    """Vence a assinatura há `dias` e roda a tarefa diária do planos."""
    Assinatura.objects.filter(anunciante=anunciante).update(
        vencimento=timezone.localdate() - timedelta(days=dias)
    )
    processar_atrasos()


def test_atraso_pausa_os_publicados_e_pagamento_reativa(loja, publicado):
    """Em atraso: publicados pausados (nunca apagados). Pagou: voltam; o pausado pelo cliente, não."""
    anunciante = loja()
    no_ar = publicado(anunciante)
    do_cliente = publicado(anunciante, "Apartamento 2 quartos no Centro")
    services.pausar(do_cliente)

    atrasar(anunciante)
    no_ar.refresh_from_db()
    assert (no_ar.situacao, no_ar.pausado_por) == (Situacao.PAUSADO, "atraso")
    with pytest.raises(ValueError, match="pagamento"):
        services.reativar(no_ar)

    registrar_pagamento(assinatura_de(anunciante), None, "Pix conferido")
    no_ar.refresh_from_db()
    do_cliente.refresh_from_db()
    assert no_ar.situacao == Situacao.PUBLICADO
    assert (do_cliente.situacao, do_cliente.pausado_por) == (Situacao.PAUSADO, "cliente")


def test_prazo_vencido_durante_o_atraso_volta_expirado(loja, publicado):
    """Se o prazo acabou enquanto estava pausado por atraso, volta como expirado (pede Renovar)."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    atrasar(anunciante)
    Anuncio.objects.filter(pk=anuncio.pk).update(expira_em=timezone.now() - timedelta(days=1))

    registrar_pagamento(assinatura_de(anunciante), None, "Pix conferido")

    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.EXPIRADO


# --- Downgrade ------------------------------------------------------------------------------


def test_downgrade_pausa_os_nao_escolhidos(loja, publicado, imovel):
    """Premium → plano de 2: o anunciante escolhe 2; na aprovação o resto pausa (em análise vira rascunho)."""
    anunciante = loja(slug_plano="premium")
    a, b, c = (publicado(anunciante, f"Casa número {i} com quintal") for i in (1, 2, 3))
    em_analise = imovel(anunciante, "Apartamento 2 quartos no Centro")
    mudar_config(moderacao="todos")
    services.enviar_para_publicacao(em_analise)
    basico = Plano.objects.get(slug="basico")
    basico.limite_anuncios = 2
    basico.save()
    pedido = pedir_troca(anunciante, basico, Periodicidade.MENSAL)

    with pytest.raises(ValueError, match="escolher quais manter"):
        aprovar_pedido(pedido, None)
    escolher_anuncios_para_manter(pedido, [a.pk, c.pk])
    aprovar_pedido(pedido, None)

    situacoes = dict(Anuncio.objects.filter(anunciante=anunciante).values_list("pk", "situacao"))
    assert situacoes[a.pk] == situacoes[c.pk] == Situacao.PUBLICADO
    assert situacoes[b.pk] == Situacao.PAUSADO
    assert situacoes[em_analise.pk] == Situacao.RASCUNHO
    assert assinatura_de(anunciante).plano == basico
    assert Anuncio.objects.get(pk=b.pk).pausado_por == "downgrade"


def test_escolha_do_downgrade_valida_limite_e_dono(loja, publicado):
    """Mais que o limite ou anúncio de outra loja: recusado."""
    anunciante = loja(slug_plano="premium")
    meus = [publicado(anunciante, f"Casa número {i} com quintal") for i in (1, 2)]
    alheio = publicado(loja("b@exemplo.com", "Loja Beta"))
    basico = Plano.objects.get(slug="basico")
    basico.limite_anuncios = 1
    basico.save()
    pedido = pedir_troca(anunciante, basico, Periodicidade.MENSAL)

    with pytest.raises(ValueError, match="no máximo 1"):
        escolher_anuncios_para_manter(pedido, [m.pk for m in meus])
    with pytest.raises(ValueError, match="seus anúncios"):
        escolher_anuncios_para_manter(pedido, [alheio.pk])


def test_pausar_por_downgrade_ignora_anuncio_de_outra_loja(loja, publicado):
    """Sem IDOR: ids de outra loja não são tocados."""
    alheio = publicado(loja("b@exemplo.com", "Loja Beta"))

    assert services.pausar_por_downgrade(loja(), [alheio.pk]) == 0
    assert Anuncio.objects.get(pk=alheio.pk).situacao == Situacao.PUBLICADO
