"""Testes das telas: Painel › Meu plano, card do plano no painel e admin de planos."""

from decimal import Decimal

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from planos.models import Assinatura, PedidoTrocaPlano, Periodicidade, Plano
from planos.services import assinatura_de, pedir_troca

pytestmark = pytest.mark.django_db

MEU_PLANO = "planos:meu_plano"


# --- Painel › Meu plano -----------------------------------------------------------------------


def test_meu_plano_exige_login(client):
    """Visitante vai para o login."""
    resposta = client.get(reverse(MEU_PLANO))

    assert resposta.status_code == 302 and reverse("contas:entrar") in resposta["Location"]


def test_meu_plano_mostra_plano_uso_e_vencimento(client, assinante):
    """Plano, uso X de Y, vencimento e a caixa "Sobre esta tela"."""
    loja = assinante()
    client.force_login(loja.usuario)

    html = client.get(reverse(MEU_PLANO)).content.decode()

    assert "Básico" in html and "/ 10" in html
    assert assinatura_de(loja).vencimento.strftime("%d/%m/%Y") in html
    assert "Sobre esta tela" in html and "Para trocar de plano" in html
    assert 'class="ativo" aria-current="page" href="/painel/plano/"' in html  # item do menu


def test_meu_plano_mostra_so_a_propria_assinatura(client, assinante):
    """Sem IDOR: cada loja vê o próprio plano."""
    assinante("a@exemplo.com", "Loja Alfa", slug_plano="premium")
    beta = assinante("b@exemplo.com", "Loja Beta", slug_plano="basico")
    client.force_login(beta.usuario)

    html = client.get(reverse(MEU_PLANO)).content.decode()

    assert "/ 10" in html and "/ 50" not in html


def test_meu_plano_envia_pedido(client, assinante, plano):
    """POST cria o pedido da própria loja e manda e-mails; a tela mostra o pedido em análise."""
    loja = assinante()
    client.force_login(loja.usuario)

    resposta = client.post(
        reverse(MEU_PLANO), {"plano": plano("premium").pk, "periodicidade": "anual"}, follow=True
    )

    pedido = PedidoTrocaPlano.objects.get()
    assert pedido.anunciante == loja and pedido.plano_novo.slug == "premium"
    html = resposta.content.decode()
    assert "Pedido enviado" in html and "Pedido em análise" in html
    assert len(mail.outbox) == 2


def test_meu_plano_mesmo_plano_mostra_erro(client, assinante, plano):
    """Pedir o mesmo plano: a tela explica e não cria pedido."""
    loja = assinante()
    client.force_login(loja.usuario)

    html = client.post(
        reverse(MEU_PLANO), {"plano": plano("basico").pk, "periodicidade": "mensal"}
    ).content.decode()

    assert "já está neste plano" in html and not PedidoTrocaPlano.objects.exists()


def test_meu_plano_nao_aceita_plano_inativo(client, assinante, plano):
    """Plano fora de venda nem aparece como opção válida."""
    loja = assinante()
    premium = plano("premium")
    premium.ativo = False
    premium.save()
    client.force_login(loja.usuario)

    resposta = client.post(reverse(MEU_PLANO), {"plano": premium.pk, "periodicidade": "mensal"})

    assert resposta.status_code == 200 and not PedidoTrocaPlano.objects.exists()


def test_meu_plano_recusa_equipe_sem_loja(client):
    """Conta de equipe (sem anunciante) não tem "Meu plano"."""
    staff = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    client.force_login(staff)

    assert client.get(reverse(MEU_PLANO)).status_code in (302, 403)


# --- Card do plano no painel ------------------------------------------------------------------


def test_painel_mostra_dados_reais_do_plano(client, assinante):
    """Plano, uso X de Y e vencimento de verdade (sem aviso de "exemplo")."""
    loja = assinante(slug_plano="profissional", periodicidade=Periodicidade.ANUAL)
    client.force_login(loja.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Profissional" in html and "0 <span" in html and "/ 25" in html
    assert "R$ 999/ano" in html
    assert assinatura_de(loja).vencimento.strftime("%d/%m/%Y") in html
    assert "exemplo" not in html.lower()


def test_painel_em_atraso_avisa_que_anuncios_estao_pausados(client, assinante):
    """Em atraso: aviso de anúncios pausados (nunca apagados)."""
    loja = assinante()
    Assinatura.objects.filter(anunciante=loja).update(situacao=Assinatura.Situacao.EM_ATRASO)
    client.force_login(loja.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Assinatura em atraso" in html and "nada foi apagado" in html


# --- /planos/ lê do banco ---------------------------------------------------------------------


def test_pagina_publica_planos_reflete_o_admin(client, plano):
    """Mudar o preço no banco muda a página pública."""
    basico = plano("basico")
    basico.preco_mensal = Decimal("59.90")
    basico.save()

    assert "R$ 59,90" in client.get(reverse("core:planos")).content.decode()


# --- Admin ------------------------------------------------------------------------------------


@pytest.fixture
def daniel(entrar_no_admin):
    """Superusuário logado no admin."""
    usuario = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(usuario)
    return usuario


def test_admin_edita_preco_e_limite_na_lista(client, daniel, plano):
    """Preço e limite editáveis na lista; o histórico guarda a mudança."""
    url = reverse("admin:planos_plano_changelist")
    planos = list(Plano.objects.order_by("ordem"))
    dados = {"form-TOTAL_FORMS": "3", "form-INITIAL_FORMS": "3", "_save": "Salvar"}
    for i, p in enumerate(planos):
        dados.update(
            {
                f"form-{i}-id": p.pk,
                f"form-{i}-limite_anuncios": 12 if p.slug == "basico" else p.limite_anuncios,
                f"form-{i}-preco_mensal": p.preco_mensal,
                f"form-{i}-preco_anual": p.preco_anual,
                f"form-{i}-ordem": p.ordem,
                f"form-{i}-ativo": "on",
            }
        )

    resposta = client.post(url, dados)

    assert resposta.status_code == 302
    basico = plano("basico")
    assert basico.limite_anuncios == 12 and basico.history.first().history_user == daniel


def test_admin_nao_apaga_plano(client, daniel, plano):
    """Plano não se apaga (assinaturas dependem dele)."""
    assert client.get(reverse("admin:planos_plano_delete", args=[plano("basico").pk])).status_code == 403


def test_admin_assinaturas_filtra_por_situacao(client, daniel, assinante):
    """Filtro por situação na lista de assinaturas."""
    assinante("a@exemplo.com", "Loja Em Dia")
    atrasada = assinante("b@exemplo.com", "Loja Devendo")
    Assinatura.objects.filter(anunciante=atrasada).update(situacao=Assinatura.Situacao.EM_ATRASO)

    html = client.get(
        reverse("admin:planos_assinatura_changelist"), {"situacao__exact": "em_atraso"}
    ).content.decode()

    assert "Loja Devendo" in html and "Loja Em Dia" not in html


def test_admin_registrar_pagamento_pede_motivo_e_reativa(client, daniel, assinante):
    """Ação de pagamento manual: tela do motivo e, ao confirmar, a assinatura volta a ativa."""
    loja = assinante()
    assinatura = assinatura_de(loja)
    Assinatura.objects.filter(pk=assinatura.pk).update(situacao=Assinatura.Situacao.EM_ATRASO)
    url = reverse("admin:planos_assinatura_changelist")
    dados = {"action": "registrar_pagamento_manual", ACTION_CHECKBOX_NAME: [assinatura.pk]}

    tela = client.post(url, dados)
    assert tela.status_code == 200 and "Motivo" in tela.content.decode()
    client.post(url, {**dados, "aplicar": "1", "motivo": "Pix conferido"})

    assinatura.refresh_from_db()
    assert assinatura.situacao == Assinatura.Situacao.ATIVA
    assert assinatura.history.first().history_user == daniel


def test_admin_aprova_e_recusa_pedidos(client, daniel, assinante, plano):
    """Aprovar aplica o plano; recusar pede motivo e avisa por e-mail."""
    alfa = assinante("a@exemplo.com", "Loja Alfa")
    beta = assinante("b@exemplo.com", "Loja Beta")
    p_alfa = pedir_troca(alfa, plano("premium"), Periodicidade.MENSAL)
    p_beta = pedir_troca(beta, plano("premium"), Periodicidade.MENSAL)
    url = reverse("admin:planos_pedidotrocaplano_changelist")
    mail.outbox.clear()

    client.post(url, {"action": "aprovar_selecionados", ACTION_CHECKBOX_NAME: [p_alfa.pk]})
    client.post(
        url,
        {
            "action": "recusar_selecionados",
            ACTION_CHECKBOX_NAME: [p_beta.pk],
            "aplicar": "1",
            "motivo": "Sem pagamento.",
        },
    )

    assert assinatura_de(alfa).plano.slug == "premium"
    assert assinatura_de(beta).plano.slug == "basico"
    p_beta.refresh_from_db()
    assert p_beta.status == PedidoTrocaPlano.Status.RECUSADO and p_beta.decidido_por == daniel
    assert {m.to[0] for m in mail.outbox} == {"a@exemplo.com", "b@exemplo.com"}


def test_financeiro_gerencia_e_moderador_so_consulta(client, entrar_no_admin):
    """Permissões dos grupos: Financeiro muda planos; Moderador só vê."""
    fin = Usuario.objects.create_user(email="fin@exemplo.com", password=SENHA, nome="Fin", is_staff=True)
    fin.groups.add(Group.objects.get(name="Financeiro"))
    mod = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    mod.groups.add(Group.objects.get(name="Moderador"))

    assert fin.has_perm("planos.change_plano") and fin.has_perm("planos.change_pedidotrocaplano")
    assert mod.has_perm("planos.view_assinatura") and not mod.has_perm("planos.change_assinatura")
    entrar_no_admin(mod)
    assert client.get(reverse("admin:planos_assinatura_changelist")).status_code == 200
