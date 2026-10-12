"""Testes das regras da cobrança (pagamentos.services): geração X dias antes, vencida, régua de e-mails
com textos do admin, comprovante, confirmar/recusar/cancelar, pagamento manual, atraso pela fatura
vencida (pausa e reativação dos anúncios), troca de plano, painel e dados de demonstração."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone

from anuncios.models import Anuncio
from core.services import configuracao
from pagamentos import services
from pagamentos.models import Fatura, ModeloEmailCobranca
from pagamentos.tests.conftest import PDF_SIMPLES, envio, imagem
from planos.models import Assinatura, Periodicidade, Plano
from planos.services import aprovar_pedido, assinatura_de, pedir_troca, proximo_vencimento

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate


def vencendo_em(anunciante, dias: int) -> Assinatura:
    """Põe o vencimento da assinatura daqui a `dias` (negativo = no passado)."""
    Assinatura.objects.filter(anunciante=anunciante).update(vencimento=HOJE() + timedelta(days=dias))
    return assinatura_de(anunciante)


# --- Geração da fatura ------------------------------------------------------------------------


def test_gera_a_fatura_x_dias_antes_e_avisa(loja):
    """Antecedência padrão 10 dias: com 11 ainda não; com 10 gera (aberta) e manda "fatura disponível"."""
    anunciante = loja()
    vencendo_em(anunciante, 11)
    assert services.gerar_faturas() == 0

    assinatura = vencendo_em(anunciante, 10)
    assert services.gerar_faturas() == 1
    fatura = assinatura.faturas.get()
    assert fatura.codigo == f"ND-FT-{fatura.pk:05d}"
    assert (fatura.valor, fatura.descricao, fatura.situacao) == (
        Decimal("49.90"),
        "Básico · mensal",
        "aberta",
    )
    assert fatura.competencia == fatura.vencimento == assinatura.vencimento
    assert fatura.periodo_fim == proximo_vencimento(fatura.competencia, Periodicidade.MENSAL) - timedelta(
        days=1
    )
    (email,) = mail.outbox
    assert email.to == ["loja@exemplo.com"]
    assert fatura.codigo in email.subject and "R$ 49,90" in email.body and "/painel/faturas/" in email.body
    assert fatura.avisos_enviados == ["fatura_disponivel"]

    assert services.gerar_faturas() == 0  # idempotente: uma fatura por ciclo
    assert len(mail.outbox) == 1


def test_antecedencia_vem_da_configuracao(loja):
    """Mudar no admin muda a regra."""
    config = configuracao()
    config.fatura_antecedencia_dias = 15
    config.save()
    vencendo_em(loja(), 15)

    assert services.gerar_faturas() == 1


def test_assinatura_cancelada_nao_gera_e_fatura_cancelada_libera_o_ciclo(loja):
    """Cancelada não gera; fatura cancelada não conta (o ciclo pode ganhar uma fatura nova)."""
    anunciante = loja()
    assinatura = vencendo_em(anunciante, 5)
    Assinatura.objects.filter(pk=assinatura.pk).update(situacao=Assinatura.Situacao.CANCELADA)
    assert services.gerar_faturas() == 0

    Assinatura.objects.filter(pk=assinatura.pk).update(situacao=Assinatura.Situacao.ATIVA)
    fatura = services.gerar_fatura(assinatura, avisar=False)
    services.cancelar_fatura(fatura, None, "Valor errado")
    assert services.gerar_fatura(assinatura, avisar=False) is not None
    assert assinatura.faturas.count() == 2


def test_assinatura_antiga_ja_vencida_ganha_fatura_vencida(loja):
    """Vencimento no passado sem fatura (dado antigo): a fatura nasce vencida."""
    vencendo_em(loja(), -2)
    services.gerar_faturas()

    assert Fatura.objects.get().situacao == Fatura.Situacao.VENCIDA


def test_marca_vencidas_no_dia_seguinte(com_fatura):
    """Vence hoje: ainda aberta. Amanhã: vencida (com histórico)."""
    fatura = com_fatura(dias=0)
    assert services.marcar_vencidas() == 0
    assert services.marcar_vencidas(HOJE() + timedelta(days=1)) == 1
    fatura.refresh_from_db()
    assert fatura.situacao == Fatura.Situacao.VENCIDA
    assert "Vencida" in fatura.history.order_by("-history_id").first().history_change_reason


# --- Régua de e-mails -------------------------------------------------------------------------


def test_regua_3_dias_antes_no_dia_e_1_e_3_dias_depois(com_fatura):
    """Cada lembrete no seu dia, uma vez só; no 2º dia de atraso, nada."""
    fatura = com_fatura(dias=3)
    vencimento = fatura.vencimento
    esperado = {-3: "vence em 3 dias", 0: "vence hoje", 1: "venceu ontem", 2: None, 3: "em aberto há 3 dias"}
    for dias, trecho in esperado.items():
        mail.outbox.clear()
        dia = vencimento + timedelta(days=dias)
        services.marcar_vencidas(dia)
        enviados = services.enviar_avisos(dia)
        if trecho is None:
            assert enviados == 0
            continue
        assert enviados == 1 and trecho in mail.outbox[0].subject
        assert services.enviar_avisos(dia) == 0  # rodar de novo no mesmo dia não repete
    fatura.refresh_from_db()
    assert fatura.avisos_enviados == ["lembrete_3_dias", "vence_hoje", "vencida_1_dia", "vencida_3_dias"]


def test_regua_nao_cobra_quem_mandou_comprovante(com_fatura):
    """Aguardando confirmação: o anunciante já disse que pagou."""
    fatura = com_fatura(dias=0)
    Fatura.objects.filter(pk=fatura.pk).update(situacao=Fatura.Situacao.AGUARDANDO)

    assert services.enviar_avisos() == 0


def test_textos_vem_do_admin_e_podem_ser_desligados(com_fatura):
    """O assunto e o texto editados no admin valem; desligado não sai."""
    fatura = com_fatura(dias=0)
    modelo = ModeloEmailCobranca.objects.get(chave="vence_hoje")
    modelo.assunto = "Hoje é o dia, {loja}"
    modelo.corpo = "Valor {valor}, código {codigo}, link {link}. Atributo: {loja.usuario}"
    modelo.save()

    services.enviar_avisos()
    (email,) = mail.outbox
    assert email.subject.startswith("Hoje é o dia, Loja Alfa")
    assert "Valor R$ 49,90" in email.body and fatura.codigo in email.body
    assert "{loja.usuario}" in email.body  # nada de atributos: só variáveis simples são trocadas

    ModeloEmailCobranca.objects.update(ativo=False)
    Fatura.objects.update(avisos_enviados=[])
    assert services.enviar_avisos() == 0


def test_texto_com_variavel_desconhecida_e_recusado():
    """Uma variável errada sairia literalmente no e-mail do cliente: o admin recusa."""
    modelo = ModeloEmailCobranca.objects.get(chave="vence_hoje")
    modelo.corpo = "Olá {cliente}, pague {valor}."
    with pytest.raises(ValidationError, match="cliente"):
        modelo.clean()


def test_migration_cria_os_textos_de_todos_os_emails():
    """Um texto para cada e-mail automático, todos ligados."""
    assert set(ModeloEmailCobranca.objects.filter(ativo=True).values_list("chave", flat=True)) == set(
        ModeloEmailCobranca.Chave.values
    )


# --- Comprovante -----------------------------------------------------------------------------


def test_comprovante_imagem_sem_exif_privado_e_financeiro_avisado(com_fatura, settings):
    """Foto com GPS: regravada sem EXIF, fora da mídia pública; fatura aguardando; e-mail à equipe."""
    fatura = com_fatura()
    mail.outbox.clear()

    fatura = services.enviar_comprovante(
        fatura, envio("meu nome.jpg", imagem("JPEG", exif=True), "image/jpeg"), "Pix da empresa"
    )

    assert fatura.situacao == Fatura.Situacao.AGUARDANDO and fatura.comprovante_enviado_em
    assert "meu nome" not in fatura.comprovante.name and fatura.comprovante.name.endswith(".jpg")
    caminho = Path(fatura.comprovante.path)
    assert caminho.exists() and Path(settings.MEDIA_ROOT) not in caminho.parents
    from PIL import Image

    with Image.open(caminho) as salva:
        assert not salva.getexif()
    assert "Pix da empresa" in fatura.observacao
    (email,) = mail.outbox
    assert email.to == [configuracao().email_contato]  # sem Financeiro cadastrado, o e-mail de contato
    assert (
        fatura.codigo in email.body and "Pix da empresa" in email.body and "/pagamentos/fatura/" in email.body
    )


@pytest.mark.parametrize(
    ("nome", "conteudo", "trecho"),
    [
        ("nota.txt", b"so texto", "PDF, JPG, PNG ou WebP"),
        ("falso.png", b"\x89PNG\r\n\x1a\nquebrado", "PDF, JPG, PNG ou WebP"),
        (
            "ativo.pdf",
            PDF_SIMPLES.replace(b"/Type /Catalog", b"/OpenAction << /S /JavaScript >>"),
            "não pôde ser aceito",
        ),
        ("cortado.pdf", b"%PDF-1.4\n1 0 obj", "não pôde ser aceito"),
    ],
)
def test_comprovante_invalido_e_recusado(com_fatura, nome, conteudo, trecho):
    """Tipo real conferido (não pela extensão), PDF sem script e inteiro."""
    with pytest.raises(ValidationError, match=trecho):
        services.enviar_comprovante(com_fatura(), envio(nome, conteudo, "application/octet-stream"))
    assert Fatura.objects.get().situacao == Fatura.Situacao.ABERTA


def test_limite_do_comprovante_vem_da_configuracao(com_fatura):
    """Maior que o limite do admin: recusado."""
    config = configuracao()
    config.limite_comprovante_kb = 1
    config.save()
    with pytest.raises(ValidationError, match="até"):
        services.enviar_comprovante(com_fatura(), envio("grande.png", imagem(lado=900)))


def test_pdf_aceito_e_so_fatura_a_pagar(com_fatura):
    """PDF simples passa; fatura paga não recebe comprovante."""
    fatura = services.enviar_comprovante(com_fatura(), envio("c.pdf", PDF_SIMPLES, "application/pdf"))
    assert fatura.comprovante_e_pdf and Path(fatura.comprovante.path).read_bytes() == PDF_SIMPLES

    services.confirmar_pagamento(fatura, None)
    with pytest.raises(ValueError, match="não está esperando"):
        services.enviar_comprovante(fatura, envio("c.pdf", PDF_SIMPLES, "application/pdf"))


def test_reenvio_depois_da_recusa_troca_o_arquivo(com_fatura):
    """Recusado: volta a aberta com o motivo; o novo comprovante substitui o antigo (arquivo apagado)."""
    fatura = services.enviar_comprovante(com_fatura(), envio("a.png", imagem()))
    antigo = Path(fatura.comprovante.path)
    mail.outbox.clear()

    fatura = services.recusar_comprovante(fatura, None, "Valor diferente do da fatura.")
    assert (fatura.situacao, fatura.motivo_recusa) == ("aberta", "Valor diferente do da fatura.")
    (email,) = mail.outbox
    assert "Valor diferente do da fatura." in email.body

    fatura = services.enviar_comprovante(fatura, envio("b.png", imagem()))
    assert not antigo.exists() and fatura.motivo_recusa == ""


def test_recusa_exige_motivo_e_volta_a_vencida_se_ja_venceu(com_fatura):
    """Sem motivo não recusa; vencida antes do comprovante volta a vencida."""
    fatura = services.enviar_comprovante(com_fatura(dias=-1), envio("a.png", imagem()))
    with pytest.raises(ValueError, match="motivo"):
        services.recusar_comprovante(fatura, None, " ")

    assert services.recusar_comprovante(fatura, None, "Ilegível").situacao == Fatura.Situacao.VENCIDA


# --- Confirmação, pagamento manual e atraso ---------------------------------------------------------


def test_confirmar_renova_uma_vez_e_avisa(com_fatura, equipe):
    """Paga: forma, quem confirmou, vencimento + 1 mês (a partir do atual, pago antes) e e-mail."""
    financeiro = equipe("Financeiro")
    fatura = com_fatura(dias=5)
    vencimento = fatura.vencimento
    mail.outbox.clear()

    fatura = services.confirmar_pagamento(fatura, financeiro, Fatura.Forma.PIX, "Extrato de 12/10")

    assinatura = assinatura_de(fatura.assinatura.anunciante)
    assert (fatura.situacao, fatura.forma, fatura.confirmado_por) == ("paga", "pix", financeiro)
    assert assinatura.vencimento == proximo_vencimento(vencimento, Periodicidade.MENSAL)
    assert assinatura.history.order_by("-history_id").first().history_user == financeiro
    assert "Confirmamos o pagamento" in mail.outbox[-1].body
    with pytest.raises(ValueError, match="paga"):
        services.confirmar_pagamento(fatura, financeiro)


def test_confirmar_fatura_de_ciclo_antigo_nao_empurra_o_vencimento(com_fatura):
    """A assinatura já foi renovada por outro caminho: a baixa da fatura antiga não renova de novo."""
    fatura = com_fatura(dias=5)
    assinatura = fatura.assinatura
    Assinatura.objects.filter(pk=assinatura.pk).update(vencimento=fatura.vencimento + timedelta(days=30))

    services.confirmar_pagamento(fatura, None)

    assert assinatura_de(assinatura.anunciante).vencimento == fatura.vencimento + timedelta(days=30)


def test_atraso_pela_fatura_pausa_e_confirmacao_reativa(loja, publicado):
    """Fatura vencida além da carência: assinatura em atraso e anúncios pausados; confirmou: voltam."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    vencendo_em(anunciante, -6)

    resultado = services.rotina_de_cobranca()

    assert resultado["geradas"] == 1 and resultado["em_atraso"] == 1
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.PAUSADO
    fatura = Fatura.objects.get()
    services.confirmar_pagamento(fatura, None)
    anuncio.refresh_from_db()
    assinatura = assinatura_de(anunciante)
    assert anuncio.situacao == Anuncio.Situacao.PUBLICADO
    assert assinatura.situacao == Assinatura.Situacao.ATIVA
    # pago em atraso: o ciclo conta do vencimento original (o dia de cobrança da loja não muda)
    original = HOJE() - timedelta(days=6)
    assert assinatura.vencimento == proximo_vencimento(original, Periodicidade.MENSAL)


def test_comprovante_aguardando_segura_a_pausa_ate_a_decisao(loja, publicado):
    """Comprovante enviado: não pausa. Recusado depois da carência: a próxima rotina pausa."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    vencendo_em(anunciante, -3)
    services.gerar_faturas()
    fatura = services.enviar_comprovante(Fatura.objects.get(), envio("a.png", imagem()))

    dia = HOJE() + timedelta(days=5)  # vencida há 8 dias (carência 5)
    assert services.rotina_de_cobranca(dia)["em_atraso"] == 0
    services.recusar_comprovante(fatura, None, "Não caiu na conta", dia)
    assert services.rotina_de_cobranca(dia)["em_atraso"] == 1
    anuncio.refresh_from_db()
    assert anuncio.situacao == Anuncio.Situacao.PAUSADO


def test_pagamento_manual_baixa_a_fatura_em_aberto_ou_cria(loja):
    """Com fatura em aberto: baixa ela. Sem: cria a do ciclo e baixa. Motivo obrigatório."""
    anunciante = loja()
    assinatura = vencendo_em(anunciante, 3)
    aberta = services.gerar_fatura(assinatura, avisar=False)

    paga = services.registrar_pagamento_manual(assinatura, None, "Dinheiro no balcão")
    assert paga.pk == aberta.pk and paga.situacao == "paga" and "Dinheiro no balcão" in paga.observacao

    nova = services.registrar_pagamento_manual(assinatura_de(anunciante), None, "Transferência")
    assert nova.pk != aberta.pk and nova.situacao == "paga"
    with pytest.raises(ValueError, match="motivo"):
        services.registrar_pagamento_manual(assinatura_de(anunciante), None, "")


def test_cancelar_exige_motivo_e_nao_cancela_paga(com_fatura):
    """Cancelada fica no histórico; paga não cancela."""
    fatura = com_fatura()
    with pytest.raises(ValueError, match="motivo"):
        services.cancelar_fatura(fatura, None, "")
    assert services.cancelar_fatura(fatura, None, "Cortesia").situacao == "cancelada"
    with pytest.raises(ValueError, match="cancelada"):
        services.cancelar_fatura(fatura, None, "De novo")


def test_troca_de_plano_atualiza_a_fatura_aberta(com_fatura):
    """Aprovou o Premium com a fatura do ciclo aberta: ela passa a cobrar o Premium."""
    fatura = com_fatura()
    pedido = pedir_troca(
        fatura.assinatura.anunciante, Plano.objects.get(slug="premium"), Periodicidade.MENSAL
    )
    aprovar_pedido(pedido, None)

    fatura.refresh_from_db()
    assert (fatura.valor, fatura.descricao) == (Decimal("149.90"), "Premium · mensal")
    assert "Plano trocado" in fatura.history.order_by("-history_id").first().history_change_reason


# --- Painel do admin e demonstração -----------------------------------------------------------


def test_resumo_da_cobranca(com_fatura):
    """Vencendo em 7 dias, vencidas, aguardando e recebido no mês."""
    vencendo = com_fatura("a@exemplo.com", "Loja A", dias=3)
    vencida = com_fatura("b@exemplo.com", "Loja B", dias=-2)
    services.marcar_vencidas()
    aguardando = services.enviar_comprovante(
        com_fatura("c@exemplo.com", "Loja C", dias=1), envio("a.png", imagem())
    )
    paga = services.confirmar_pagamento(com_fatura("d@exemplo.com", "Loja D", dias=8), None)

    resumo = services.resumo_cobranca()

    assert resumo["vencendo_7_dias"]["quantas"] == 1 and resumo["vencendo_7_dias"]["total"] == vencendo.valor
    assert resumo["vencidas"]["quantas"] == 1 and vencida.pk
    assert resumo["aguardando"]["quantas"] == 1 and aguardando.pk
    assert resumo["recebido_mes"]["quantas"] == 1 and paga.pk
    assert "situacao__exact=vencida" in resumo["vencidas"]["filtro"]


def test_faturas_demo(loja):
    """Histórico pago, uma aberta, uma aguardando (com comprovante) e a da loja em atraso vencida."""
    lojas = [loja(f"{n}@exemplo.com", f"Loja {n}") for n in ("a", "b", "c")]
    Assinatura.objects.update(demo=True)
    atrasada = assinatura_de(lojas[2])
    Assinatura.objects.filter(pk=atrasada.pk).update(
        vencimento=HOJE() - timedelta(days=15), situacao=Assinatura.Situacao.EM_ATRASO
    )

    services.criar_faturas_demo([lojas[2].slug])
    situacoes = sorted(Fatura.objects.exclude(situacao="paga").values_list("situacao", flat=True))

    assert situacoes == ["aberta", "aguardando_confirmacao", "vencida"]
    assert (
        Fatura.objects.filter(situacao="paga").count() == 9 and not Fatura.objects.filter(demo=False).exists()
    )
    comprovante = Path(Fatura.objects.get(situacao="aguardando_confirmacao").comprovante.path)
    assert comprovante.exists()
    services.criar_faturas_demo([lojas[2].slug])  # idempotente
    assert Fatura.objects.count() == 12

    services.apagar_faturas_demo()
    assert not Fatura.objects.exists() and not Fatura.history.exists()


# --- Passo 0 da Sprint 7: vencimento original, primeira fatura e lembrete perdido -------------------


def test_renovacao_conta_do_vencimento_original_mesmo_pagando_depois(com_fatura):
    """Pagou 2 dias depois (dentro da carência): o próximo é vencimento + 1 mês, não hoje + 1 mês."""
    fatura = com_fatura(dias=-2)
    services.confirmar_pagamento(fatura, None)

    assinatura = assinatura_de(fatura.assinatura.anunciante)
    assert assinatura.vencimento == proximo_vencimento(fatura.vencimento, Periodicidade.MENSAL)


def test_primeiro_plano_aprovado_gera_a_primeira_fatura(criar_anunciante):
    """Loja sem plano pede o Básico; a aprovação cria a assinatura com o 1º ciclo vencendo hoje e a fatura."""
    anunciante = criar_anunciante("nova@exemplo.com", "Loja Nova")
    pedido = pedir_troca(anunciante, Plano.objects.get(slug="basico"), Periodicidade.MENSAL)
    mail.outbox.clear()

    assinatura = aprovar_pedido(pedido, None)

    fatura = assinatura.faturas.get()
    assert (fatura.competencia, fatura.vencimento, fatura.situacao) == (HOJE(), HOJE(), "aberta")
    assert fatura.valor == Decimal("49.90") and assinatura.vencimento == HOJE()
    assert any(fatura.codigo in email.subject for email in mail.outbox)  # "fatura disponível"
    services.confirmar_pagamento(fatura, None)
    assert assinatura_de(anunciante).vencimento == proximo_vencimento(HOJE(), Periodicidade.MENSAL)


def test_beat_parado_o_lembrete_sai_no_dia_seguinte(com_fatura):
    """Sem rotina no dia do vencimento: no dia seguinte sai só o lembrete mais recente (sem rajada); um dia
    perdido depois disso também é recuperado."""
    fatura = com_fatura(dias=0)
    vencimento = fatura.vencimento
    mail.outbox.clear()

    dia = vencimento + timedelta(days=1)  # não rodou nem no lembrete de 3 dias nem no dia
    services.marcar_vencidas(dia)
    assert services.enviar_avisos(dia) == 1
    assert "venceu ontem" in mail.outbox[-1].subject
    fatura.refresh_from_db()
    assert fatura.avisos_enviados == ["vencida_1_dia", "lembrete_3_dias", "vence_hoje"]

    assert services.enviar_avisos(vencimento + timedelta(days=2)) == 0
    assert services.enviar_avisos(vencimento + timedelta(days=5)) == 1  # o de 3 dias, recuperado
    assert "há 3 dias" in mail.outbox[-1].subject
