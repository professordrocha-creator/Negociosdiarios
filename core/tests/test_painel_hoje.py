"""Testes do lote 3C: "Painel de hoje" na página inicial do admin (cartões por grupo, cores por urgência,
"Fazer agora" com o botão Aprovar) e o menu enxuto por grupo, com "Mais opções" só para o Administrador."""

from datetime import timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from config.menu_admin import MENU_POR_GRUPO
from contas.models import Usuario
from core.services import configuracao, fazer_agora, pendencias_da_equipe

pytestmark = pytest.mark.django_db


def membro(grupo: str) -> Usuario:
    """Alguém da equipe num grupo."""
    usuario = Usuario.objects.create_user(
        email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
    )
    usuario.groups.add(Group.objects.get(name=grupo))
    return usuario


def dono() -> Usuario:
    """O superusuário."""
    return Usuario.objects.create_superuser(email="dono@exemplo.com", password=SENHA, nome="Dono")


def mudar_config(**valores):
    """Altera as Configurações do site (como no admin)."""
    config = configuracao()
    for campo, valor in valores.items():
        setattr(config, campo, valor)
    config.save()


def com_fatura(anunciante, dias: int):
    """Fatura do ciclo da loja vencendo em `dias` (negativo = já vencida)."""
    from pagamentos.services import gerar_fatura
    from planos.models import Assinatura
    from planos.services import assinatura_de

    Assinatura.objects.filter(anunciante=anunciante).update(
        vencimento=timezone.localdate() + timedelta(days=dias)
    )
    return gerar_fatura(assinatura_de(anunciante), avisar=False)


def em_moderacao(loja, imovel, titulo: str = "Casa 3 quartos com área gourmet"):
    """Anúncio na fila de moderação (moderação de "todos" só para criar o caso)."""
    from anuncios import services as anuncios

    mudar_config(moderacao="todos")
    anuncio = imovel(loja, titulo)
    anuncios.enviar_para_publicacao(anuncio)
    mudar_config(moderacao="primeiro")
    return anuncio


# --- Cartões ---------------------------------------------------------------------------------------------


def test_cada_cartao_conta_o_certo(criar_anunciante, loja, imovel):
    """Cadastro novo e renovação aguardando conferência, faturas vencendo/em atraso, fila, denúncias e lojas
    pendentes; urgência na cor (atraso e denúncia = urgente) e zero sem cor."""
    from anuncios import services as anuncios
    from moderacao import services as moderacao
    from moderacao.models import Denuncia
    from pagamentos import services as pagamentos
    from planos.models import Periodicidade, Plano

    pendente = criar_anunciante("nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)
    pedido = pagamentos.fazer_pedido(pendente, Plano.objects.get(slug="basico"), Periodicidade.MENSAL)
    pagamentos.enviar_comprovante(pedido, None)
    pagamentos.enviar_comprovante(com_fatura(loja("a@exemplo.com", "Loja A"), 5), None)  # renovação
    com_fatura(loja("b@exemplo.com", "Loja B"), 3)  # vencendo em 3 dias
    com_fatura(loja("c@exemplo.com", "Loja C"), -2)  # em atraso
    lojab = Anunciante.objects.get(slug="loja-b")
    em_moderacao(lojab, imovel)
    no_ar = imovel(lojab, "Apartamento no centro")
    anuncios.enviar_para_publicacao(no_ar)
    moderacao.denunciar(no_ar, Denuncia.Motivo.GOLPE, "", "", "a" * 32)

    cartoes = {c.chave: c for c in pendencias_da_equipe(dono())}

    assert (cartoes["cadastros"].total, cartoes["renovacoes"].total) == (1, 1)
    assert cartoes["faturas"].total == 2 and cartoes["faturas"].detalhe == "1 vencendo · 1 em atraso"
    assert cartoes["faturas"].nivel == "urgente" and cartoes["cadastros"].nivel == "atencao"
    assert (cartoes["fila"].total, cartoes["denuncias"].total, cartoes["lojas"].total) == (1, 1, 1)
    assert cartoes["denuncias"].nivel == "urgente"
    assert cartoes["publicidade"].total == 0 and cartoes["publicidade"].nivel == ""
    assert "tipo=novo" in cartoes["cadastros"].url and "tipo=renovacao" in cartoes["renovacoes"].url


def test_link_do_cartao_abre_a_lista_filtrada(entrar_no_admin, criar_anunciante, loja):
    """O link "Cadastros aguardando conferência" mostra só o pedido novo (a renovação tem outro cartão)."""
    from pagamentos import services as pagamentos
    from planos.models import Periodicidade, Plano

    pendente = criar_anunciante("nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)
    pedido = pagamentos.fazer_pedido(pendente, Plano.objects.get(slug="basico"), Periodicidade.MENSAL)
    pagamentos.enviar_comprovante(pedido, None)
    renovacao = com_fatura(loja("a@exemplo.com", "Loja A"), 5)
    pagamentos.enviar_comprovante(renovacao, None)
    usuario = dono()
    cartoes = {c.chave: c for c in pendencias_da_equipe(usuario)}

    pagina = entrar_no_admin(usuario).get(cartoes["cadastros"].url).content.decode()
    assert pedido.codigo in pagina and renovacao.codigo not in pagina


@pytest.mark.parametrize(
    ("grupo", "esperados"),
    [
        ("Moderador", {"fila", "denuncias", "pedidos_guia", "lojas"}),
        ("Financeiro", {"cadastros", "renovacoes", "faturas", "lojas", "publicidade"}),
        ("Comercial", {"cadastros", "renovacoes", "lojas"}),
        ("Guia", {"interessados"}),
    ],
)
def test_cada_grupo_ve_so_os_seus_cartoes(grupo, esperados):
    """Os cartões seguem as permissões de cada grupo (nada a mais)."""
    assert {c.chave for c in pendencias_da_equipe(membro(grupo))} == esperados


def test_tudo_zero_mostra_nada_pendente(entrar_no_admin):
    """Sem nada esperando: "Nada pendente por aqui" em cada cartão e o aviso geral."""
    pagina = entrar_no_admin(membro("Comercial")).get(reverse("admin:index")).content.decode()
    assert "Tudo em dia: nada pendente por aqui." in pagina
    assert pagina.count("Nada pendente por aqui</span>") == 3


# --- Fazer agora -----------------------------------------------------------------------------------------


def test_fazer_agora_mostra_os_5_mais_antigos(loja, imovel):
    """Até 5 por tipo, do mais antigo para o mais novo, com o botão Aprovar da fila."""
    from anuncios.models import Anuncio

    anunciante = loja()
    criados = [em_moderacao(anunciante, imovel, f"Casa número {n} no centro") for n in range(6)]
    for dias, anuncio in enumerate(reversed(criados)):  # o primeiro criado fica o mais antigo
        Anuncio.objects.filter(pk=anuncio.pk).update(atualizado_em=timezone.now() - timedelta(days=dias))

    (fila,) = (g for g in fazer_agora(dono()) if g.titulo == "Anúncios na fila de moderação")

    assert [item.pk for item in fila.itens] == [a.pk for a in criados[:5]]
    assert all(item.aprovar_agora == "anuncio" for item in fila.itens)


def test_aprovar_do_fazer_agora_gera_o_mesmo_historico(entrar_no_admin, loja, imovel):
    """O botão da página inicial usa a MESMA ação da fila: mesma situação, mesmo autor e mesmo motivo no
    histórico que aprovar pela lista."""
    from anuncios.models import Anuncio

    anunciante = loja()
    pela_lista = em_moderacao(anunciante, imovel, "Casa aprovada pela lista")
    pelo_painel = em_moderacao(anunciante, imovel, "Casa aprovada pelo painel")
    moderador = membro("Moderador")
    client = entrar_no_admin(moderador)
    assert (
        reverse("admin:aprovar_agora", args=["anuncio", pelo_painel.pk])
        in client.get(reverse("admin:index")).content.decode()
    )

    client.post(
        reverse("admin:anuncios_anuncioemmoderacao_changelist"),
        {"action": "aprovar_selecionados", ACTION_CHECKBOX_NAME: [pela_lista.pk]},
    )
    resposta = client.post(reverse("admin:aprovar_agora", args=["anuncio", pelo_painel.pk]))

    assert resposta.status_code == 302 and resposta["Location"] == reverse("admin:index")
    ultimos = [
        Anuncio.objects.get(pk=a.pk).history.order_by("-history_id").first()
        for a in (pela_lista, pelo_painel)
    ]
    assert {h.situacao for h in ultimos} == {Anuncio.Situacao.PUBLICADO}
    assert ultimos[0].history_user == ultimos[1].history_user == moderador
    assert ultimos[0].history_change_reason == ultimos[1].history_change_reason


def test_aprovar_agora_exige_a_permissao_da_acao(entrar_no_admin, loja, imovel):
    """Quem não tem a ação "Aprovar" da fila (Financeiro) recebe 403; GET não aprova nada."""
    from anuncios.models import Anuncio

    anuncio = em_moderacao(loja(), imovel)
    url = reverse("admin:aprovar_agora", args=["anuncio", anuncio.pk])

    assert entrar_no_admin(membro("Financeiro")).post(url).status_code == 403
    assert entrar_no_admin(membro("Moderador")).get(url).status_code == 405
    assert Anuncio.objects.get(pk=anuncio.pk).situacao == Anuncio.Situacao.EM_MODERACAO


def test_pedido_no_fazer_agora_leva_a_tela_das_datas(criar_anunciante):
    """Cadastro aguardando conferência: "Aprovar" abre a tela que já existe (vigência ajustável)."""
    from pagamentos import services as pagamentos
    from planos.models import Periodicidade, Plano

    pendente = criar_anunciante("nova@exemplo.com", "Loja Nova", status=Anunciante.Status.PENDENTE)
    pedido = pagamentos.fazer_pedido(pendente, Plano.objects.get(slug="basico"), Periodicidade.MENSAL)
    pagamentos.enviar_comprovante(pedido, None)

    (grupo,) = (g for g in fazer_agora(membro("Comercial")) if g.titulo == "Cadastros aguardando conferência")
    assert grupo.itens[0].url_aprovar == reverse(
        "admin:pagamentos_pedidoaguardando_aprovar", args=[pedido.pk]
    )


# --- Menu enxuto por grupo ----------------------------------------------------------------------------------


def menu_de(usuario) -> set[str]:
    """ "app.modelo" do menu do dia a dia (o mesmo da página inicial e da barra lateral)."""
    from django.contrib import admin

    pedido = RequestFactory().get("/")
    pedido.user = usuario
    return {
        f"{app['app_label']}.{modelo['object_name'].lower()}"
        for app in admin.site.get_app_list(pedido)
        for modelo in app["models"]
    }


@pytest.mark.parametrize("grupo", sorted(MENU_POR_GRUPO))
def test_cada_grupo_ve_so_os_seus_menus(grupo):
    """Moderador, Financeiro, Comercial e Guia: exatamente os menus do grupo (config.menu_admin)."""
    assert menu_de(membro(grupo)) == MENU_POR_GRUPO[grupo]


def test_mais_opcoes_so_para_o_administrador(entrar_no_admin):
    """Administrador (grupo ou superusuário): técnico (bloqueios de login, catálogo, grupos) fica em "Mais
    opções"; os outros grupos nem veem o bloco."""
    tecnico = reverse("admin:axes_accessattempt_changelist")
    for usuario in (dono(), membro("Administrador")):
        pagina = entrar_no_admin(usuario).get(reverse("admin:index")).content.decode()
        mais = pagina[pagina.index('<details class="nd-mais-opcoes">') :]
        assert "Mais opções" in pagina and tecnico in mais and "Bloqueios de login" in mais
        assert "axes.accessattempt" not in menu_de(usuario) and "catalogo.marca" not in menu_de(usuario)
    for grupo in ("Moderador", "Financeiro", "Comercial", "Guia"):
        pagina = entrar_no_admin(membro(grupo)).get(reverse("admin:index")).content.decode()
        assert "nd-mais-opcoes" not in pagina


def test_esconder_do_menu_nao_tira_permissao(entrar_no_admin):
    """Regiões e bairros saem do menu do Moderador, mas a permissão e o endereço continuam valendo."""
    moderador = membro("Moderador")
    antes = moderador.get_all_permissions()
    client = entrar_no_admin(moderador)

    assert "core.regiao" not in menu_de(moderador)
    assert client.get(reverse("admin:core_regiao_changelist")).status_code == 200
    assert client.get(reverse("admin:app_list", args=["core"])).status_code == 200
    assert Usuario.objects.get(pk=moderador.pk).get_all_permissions() == antes


def test_nomes_simples_no_menu():
    """Nomes em português simples só no menu ("Convites e interessados", "Lojas (anunciantes)")."""
    from django.contrib import admin

    pedido = RequestFactory().get("/")
    pedido.user = membro("Guia")
    nomes = {modelo["name"] for app in admin.site.get_app_list(pedido) for modelo in app["models"]}
    assert "Convites e interessados" in nomes
    pedido.user = membro("Comercial")
    assert "Lojas (anunciantes)" in {app["name"] for app in admin.site.get_app_list(pedido)}
