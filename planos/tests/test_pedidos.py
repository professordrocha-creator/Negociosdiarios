"""Testes dos pedidos de troca de plano: pedir, aprovar e recusar (com e-mails)."""

import pytest
from django.contrib.auth.models import Group
from django.core import mail

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from planos.models import Assinatura, PedidoTrocaPlano, Periodicidade
from planos.services import aprovar_pedido, assinatura_de, pedir_troca, recusar_pedido

pytestmark = pytest.mark.django_db


@pytest.fixture
def financeiro(db):
    """Usuário do grupo Financeiro (recebe os pedidos por e-mail)."""
    usuario = Usuario.objects.create_user(email="fin@exemplo.com", password=SENHA, nome="Fin", is_staff=True)
    usuario.groups.add(Group.objects.get(name="Financeiro"))
    return usuario


def test_pedir_avisa_equipe_e_anunciante(assinante, plano, financeiro):
    """O pedido fica pendente; a equipe recebe o link do admin e o anunciante a confirmação."""
    loja = assinante()

    pedido = pedir_troca(loja, plano("premium"), Periodicidade.ANUAL)

    assert pedido.status == PedidoTrocaPlano.Status.PENDENTE
    assert pedido.plano_atual.slug == "basico" and not pedido.demo
    equipe, cliente = mail.outbox
    assert equipe.to == ["fin@exemplo.com"]
    assert "Premium" in equipe.body and f"/pedidotrocaplano/{pedido.pk}/change/" in equipe.body
    assert cliente.to == ["loja@exemplo.com"] and "Premium" in cliente.body


def test_sem_financeiro_o_pedido_vai_para_o_contato(assinante, plano):
    """Sem ninguém no Financeiro, o aviso vai para o e-mail de contato do site."""
    from core.services import configuracao

    pedir_troca(assinante(), plano("premium"), Periodicidade.MENSAL)

    assert mail.outbox[0].to == [configuracao().email_contato]


def test_pedir_o_mesmo_plano_e_recusado(assinante, plano):
    """Pedir o plano e a periodicidade que já tem não cria pedido."""
    with pytest.raises(ValueError, match="já está neste plano"):
        pedir_troca(assinante(), plano("basico"), Periodicidade.MENSAL)
    assert not PedidoTrocaPlano.objects.exists()


def test_pedir_plano_inativo_e_recusado(assinante, plano):
    """Plano fora de venda não pode ser pedido."""
    premium = plano("premium")
    premium.ativo = False
    premium.save()

    with pytest.raises(ValueError, match="não está mais à venda"):
        pedir_troca(assinante(), premium, Periodicidade.MENSAL)


def test_pedido_novo_substitui_o_pendente(assinante, plano):
    """Só um pedido pendente por loja: o anterior fica recusado como "substituído"."""
    loja = assinante()
    antigo = pedir_troca(loja, plano("profissional"), Periodicidade.MENSAL)

    novo = pedir_troca(loja, plano("premium"), Periodicidade.MENSAL)

    antigo.refresh_from_db()
    assert antigo.status == PedidoTrocaPlano.Status.RECUSADO and "Substituído" in antigo.motivo
    assert novo.status == PedidoTrocaPlano.Status.PENDENTE


def test_aprovar_troca_mantem_vencimento_e_avisa(assinante, plano, financeiro):
    """Troca aprovada: novo plano, mesmo vencimento, histórico com quem aprovou e e-mail."""
    loja = assinante()
    vencimento = assinatura_de(loja).vencimento
    pedido = pedir_troca(loja, plano("premium"), Periodicidade.ANUAL)
    mail.outbox.clear()

    assinatura = aprovar_pedido(pedido, financeiro)

    assert (assinatura.plano.slug, assinatura.periodicidade, assinatura.vencimento) == (
        "premium",
        "anual",
        vencimento,
    )
    assert assinatura.history.order_by("-history_id").first().history_user == financeiro
    pedido.refresh_from_db()
    assert pedido.status == PedidoTrocaPlano.Status.APROVADO and pedido.decidido_por == financeiro
    assert mail.outbox[0].to == ["loja@exemplo.com"] and "aprovado" in mail.outbox[0].body


def test_aprovar_primeiro_plano_cria_assinatura(criar_anunciante, plano):
    """Loja sem plano: a aprovação cria a assinatura ativa."""
    loja = criar_anunciante("nova@exemplo.com", "Loja Nova")
    pedido = pedir_troca(loja, plano("profissional"), Periodicidade.MENSAL)

    assinatura = aprovar_pedido(pedido, None)

    assert assinatura.situacao == Assinatura.Situacao.ATIVA and assinatura.plano.slug == "profissional"


def test_aprovar_downgrade_acima_do_limite_para(assinante, plano, monkeypatch):
    """Com mais anúncios que o novo limite, a aprovação para (o anunciante escolhe antes)."""
    loja = assinante(slug_plano="premium")
    pedido = pedir_troca(loja, plano("basico"), Periodicidade.MENSAL)
    monkeypatch.setattr("anuncios.services.ids_no_plano", lambda anunciante: list(range(1, 31)))

    with pytest.raises(ValueError, match="escolher quais manter"):
        aprovar_pedido(pedido, None)
    assert assinatura_de(loja).plano.slug == "premium"


def test_aprovar_duas_vezes_e_recusado(assinante, plano):
    """Pedido já decidido não é aplicado de novo."""
    pedido = pedir_troca(assinante(), plano("premium"), Periodicidade.MENSAL)
    aprovar_pedido(pedido, None)

    with pytest.raises(ValueError, match="já foi decidido"):
        aprovar_pedido(pedido, None)


def test_recusar_exige_motivo_e_avisa(assinante, plano):
    """Recusa com motivo: plano não muda e o anunciante recebe o motivo."""
    loja = assinante()
    pedido = pedir_troca(loja, plano("premium"), Periodicidade.MENSAL)
    mail.outbox.clear()

    with pytest.raises(ValueError, match="motivo"):
        recusar_pedido(pedido, None, "")
    recusar_pedido(pedido, None, "Pagamento não identificado.")

    assert pedido.status == PedidoTrocaPlano.Status.RECUSADO
    assert assinatura_de(loja).plano.slug == "basico"
    assert "Pagamento não identificado." in mail.outbox[0].body
