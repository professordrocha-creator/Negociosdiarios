"""Testes das telas: etapas do anúncio no painel, isolamento entre lojas, ações da lista,
fila de moderação no admin, "Regras do negócio" na Configuracao e a escolha do downgrade."""

from decimal import Decimal

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from anuncios import services
from anuncios.forms import ler_valor
from anuncios.models import Anuncio
from contas.models import Usuario
from core.models import Bairro, Cidade, Configuracao
from core.services import configuracao
from planos.models import PedidoTrocaPlano, Plano

pytestmark = pytest.mark.django_db

Situacao = Anuncio.Situacao
NOVO_IMOVEL = "/painel/anuncios/novo/?categoria=imovel"

DADOS = {
    "titulo": "Casa 3 quartos com área gourmet",
    "tipo": "casa",
    "modalidade": "venda",
    "preco": "420.000,00",
    "quartos": "3",
    "banheiros": "2",
    "vagas": "2",
    "area_total": "180",
    "area_construida": "120,5",
    "iptu": "",
    "descricao": "Casa ampla.",
}


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("R$ 420.000,00", Decimal("420000.00")),
        ("420000", Decimal("420000")),
        ("1.600", Decimal("1600")),
        ("64,5", Decimal("64.5")),
        ("1600.50", Decimal("1600.50")),
        ("", None),
    ],
)
def test_ler_valor_no_formato_brasileiro(texto, esperado):
    """Preço e área digitados do jeito brasileiro."""
    assert ler_valor(texto) == esperado


# --- Etapas ---------------------------------------------------------------------------------


def test_novo_exige_login(client):
    """Visitante vai para o login."""
    resposta = client.get(reverse("anuncios:novo"))

    assert resposta.status_code == 302 and reverse("contas:entrar") in resposta["Location"]


def test_equipe_sem_loja_recebe_403(client):
    """Conta de equipe não tem painel de anunciante."""
    staff = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    client.force_login(staff)

    assert client.get(reverse("anuncios:novo")).status_code == 403


def test_novo_cria_rascunho_e_segue_para_localizacao(client, loja):
    """Etapa 1: cria o rascunho com preço e área no formato brasileiro; caixa de ajuda presente."""
    anunciante = loja(tipo="imobiliaria")
    client.force_login(anunciante.usuario)
    assert "Sobre esta tela" in client.get(NOVO_IMOVEL).content.decode()

    resposta = client.post(NOVO_IMOVEL, DADOS)

    anuncio = Anuncio.objects.get()
    assert resposta["Location"] == reverse("anuncios:localizacao", args=[anuncio.codigo])
    assert anuncio.anunciante == anunciante and anuncio.situacao == Situacao.RASCUNHO
    assert anuncio.preco == Decimal("420000.00") and anuncio.imovel.area_construida == Decimal("120.5")
    assert anuncio.cidade == anunciante.cidade


@pytest.mark.parametrize(
    ("mudanca", "erro"),
    [
        ({"titulo": "Casa"}, "pelo menos 10 caracteres"),
        ({"area_construida": "500"}, "maior que a área total"),
        ({"preco": "abc"}, "Digite só números"),
    ],
)
def test_dados_invalidos(client, loja, mudanca, erro):
    """Título curto (limite da Configuracao), área construída maior que a total, preço inválido."""
    client.force_login(loja(tipo="imobiliaria").usuario)

    html = client.post(NOVO_IMOVEL, {**DADOS, **mudanca}).content.decode()

    assert erro in html and not Anuncio.objects.exists()


def test_localizacao_grava_ponto_e_bairro(client, loja, imovel, tangara):
    """Etapa 2: cidade, bairro da cidade, endereço privado e ponto perto da cidade."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    bairro = Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")
    client.force_login(anunciante.usuario)

    resposta = client.post(
        reverse("anuncios:localizacao", args=[anuncio.codigo]),
        {
            "cidade": tangara.pk,
            "bairro": bairro.pk,
            "endereco": "Rua A, 10",
            "latitude": "-14.1",
            "longitude": "-57.2",
            "exibir_localizacao": "aproximada",
        },
    )

    assert resposta["Location"] == reverse("anuncios:fotos", args=[anuncio.codigo])
    anuncio.refresh_from_db()
    assert anuncio.bairro == bairro and anuncio.imovel.endereco == "Rua A, 10"
    assert (round(anuncio.imovel.ponto.y, 1), round(anuncio.imovel.ponto.x, 1)) == (-14.1, -57.2)


@pytest.mark.parametrize(
    ("dados", "erro"),
    [
        ({"latitude": "-3.1", "longitude": "-60.0"}, "longe de"),
        ({"exibir_localizacao": "so_bairro", "latitude": "", "longitude": ""}, "escolha o bairro"),
    ],
)
def test_localizacao_invalida(client, loja, imovel, tangara, dados, erro):
    """Ponto longe da cidade (clique errado) e "só o bairro" sem bairro."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    base = {
        "cidade": tangara.pk,
        "latitude": "-14.6",
        "longitude": "-57.5",
        "exibir_localizacao": "aproximada",
    }

    html = client.post(
        reverse("anuncios:localizacao", args=[anuncio.codigo]), {**base, **dados}
    ).content.decode()

    assert erro in html


def test_localizacao_so_mostra_cidades_liberadas(client, loja, imovel, tangara):
    """Cidade não liberada não aparece nem é aceita."""
    fechada = Cidade.objects.create(
        codigo_ibge=5103403, nome="Cuiabá", slug="cuiaba", uf=tangara.uf, liberada=False, ponto=tangara.ponto
    )
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    url = reverse("anuncios:localizacao", args=[anuncio.codigo])

    assert "Cuiabá" not in client.get(url).content.decode()
    assert client.post(url, {"cidade": fechada.pk, "exibir_localizacao": "so_bairro"}).status_code == 200


def test_revisao_envia_para_publicacao(client, loja, imovel):
    """Etapa 4: enviar leva para a análise (primeiro anúncio) e volta ao painel."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    client.force_login(anunciante.usuario)

    resposta = client.post(
        reverse("anuncios:revisao", args=[anuncio.codigo]), {"acao": "enviar"}, follow=True
    )

    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.EM_MODERACAO
    assert "A equipe confere o anúncio" in resposta.content.decode()


def test_revisao_no_limite_bloqueia_e_oferece_upgrade(client, loja, imovel, publicado):
    """Plano cheio: botão desabilitado com oferta de upgrade; o POST também é recusado."""
    anunciante = loja(limite=1)
    publicado(anunciante)
    anuncio = imovel(anunciante, "Apartamento 2 quartos no Centro")
    client.force_login(anunciante.usuario)
    url = reverse("anuncios:revisao", args=[anuncio.codigo])

    html = client.get(url).content.decode()
    assert "Seu plano está no limite" in html and "disabled" in html and reverse("planos:meu_plano") in html

    client.post(url, {"acao": "enviar"})
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.RASCUNHO


def test_rascunho_recusado_mostra_o_motivo(client, loja, imovel):
    """Depois da recusa, as etapas mostram o que a equipe pediu."""
    anunciante = loja()
    anuncio = imovel(anunciante)
    services.enviar_para_publicacao(anuncio)
    services.recusar(anuncio, None, "Troque a foto da fachada.")
    client.force_login(anunciante.usuario)

    assert (
        "Troque a foto da fachada."
        in client.get(reverse("anuncios:editar", args=[anuncio.codigo])).content.decode()
    )


# --- Isolamento entre lojas -----------------------------------------------------------------


@pytest.mark.parametrize("rota", ["editar", "localizacao", "fotos", "revisao"])
def test_outra_loja_nao_abre_as_etapas(client, loja, imovel, rota):
    """Código de outra loja: 404 em todas as etapas."""
    anuncio = imovel(loja())
    client.force_login(loja("b@exemplo.com", "Loja Beta").usuario)

    assert client.get(reverse(f"anuncios:{rota}", args=[anuncio.codigo])).status_code == 404


@pytest.mark.parametrize("nome", ["pausar", "excluir", "renovar", "reativar"])
def test_outra_loja_nao_usa_as_acoes(client, loja, publicado, nome):
    """Ações por POST com código de outra loja: 404 e nada muda."""
    anuncio = publicado(loja())
    client.force_login(loja("b@exemplo.com", "Loja Beta").usuario)

    assert client.post(reverse("anuncios:acao", args=[anuncio.codigo, nome])).status_code == 404
    assert Anuncio.objects.get(pk=anuncio.pk).situacao == Situacao.PUBLICADO


def test_painel_lista_so_os_anuncios_da_loja(client, loja, publicado):
    """Meus anúncios: só os da loja logada, com os botões."""
    publicado(loja(), "Casa da Loja Alfa no Centro")
    beta = loja("b@exemplo.com", "Loja Beta")
    publicado(beta, "Casa da Loja Beta no Jardim")
    client.force_login(beta.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Casa da Loja Beta no Jardim" in html and "Casa da Loja Alfa" not in html
    assert "Pausar" in html and "Excluir" in html


def test_acoes_da_lista(client, loja, publicado):
    """Pausar e reativar pela lista; ação só por POST."""
    anunciante = loja()
    anuncio = publicado(anunciante)
    client.force_login(anunciante.usuario)

    assert client.get(reverse("anuncios:acao", args=[anuncio.codigo, "pausar"])).status_code == 405
    client.post(reverse("anuncios:acao", args=[anuncio.codigo, "pausar"]))
    assert Anuncio.objects.get(pk=anuncio.pk).situacao == Situacao.PAUSADO
    resposta = client.post(reverse("anuncios:acao", args=[anuncio.codigo, "reativar"]), follow=True)
    assert Anuncio.objects.get(pk=anuncio.pk).situacao == Situacao.PUBLICADO
    assert "de volta ao ar" in resposta.content.decode()


def test_painel_no_limite_avisa(client, loja, publicado):
    """Plano cheio: aviso com link para mudar de plano."""
    anunciante = loja(limite=1)
    publicado(anunciante)
    client.force_login(anunciante.usuario)

    assert "Plano no limite (1 de 1)" in client.get(reverse("anunciantes:painel")).content.decode()


# --- Admin: fila de moderação ---------------------------------------------------------------


@pytest.fixture
def moderador(entrar_no_admin):
    """Usuário do grupo Moderador logado no admin."""
    usuario = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    usuario.groups.add(Group.objects.get(name="Moderador"))
    entrar_no_admin(usuario)
    return usuario


def em_analise(loja, imovel, titulo="Casa 3 quartos com área gourmet", email="loja@exemplo.com"):
    """Cria um anúncio e envia para a fila."""
    anuncio = imovel(loja(email, f"Loja {email[0].upper()}"), titulo)
    services.enviar_para_publicacao(anuncio)
    return anuncio


def test_fila_mostra_so_em_analise_com_fotos_grandes(client, moderador, loja, imovel, publicado):
    """Fila: só em análise; a tela do anúncio mostra as fotos grandes e o endereço privado."""
    anuncio = em_analise(loja, imovel)
    publicado(loja("c@exemplo.com", "Loja Publicada"), "Casa publicada fora da fila")

    lista = client.get(reverse("admin:anuncios_anuncioemmoderacao_changelist")).content.decode()
    assert anuncio.codigo in lista and "Casa publicada fora da fila" not in lista

    tela = client.get(reverse("admin:anuncios_anuncioemmoderacao_change", args=[anuncio.pk])).content.decode()
    assert anuncio.fotos.first().imagem.url in tela and 'class="nd-adm-foto"' in tela


def test_fila_aprova_e_recusa(client, moderador, loja, imovel):
    """Aprovar publica; recusar pede motivo, volta a rascunho e avisa por e-mail."""
    aprovar = em_analise(loja, imovel)
    recusar = em_analise(loja, imovel, "Apartamento 2 quartos no Centro", "b@exemplo.com")
    url = reverse("admin:anuncios_anuncioemmoderacao_changelist")
    mail.outbox.clear()

    client.post(url, {"action": "aprovar_selecionados", ACTION_CHECKBOX_NAME: [aprovar.pk]})
    tela = client.post(url, {"action": "recusar_selecionados", ACTION_CHECKBOX_NAME: [recusar.pk]})
    assert "Motivo" in tela.content.decode()
    client.post(
        url,
        {
            "action": "recusar_selecionados",
            ACTION_CHECKBOX_NAME: [recusar.pk],
            "aplicar": "1",
            "motivo": "Foto escura.",
        },
    )

    aprovar.refresh_from_db()
    recusar.refresh_from_db()
    assert aprovar.situacao == Situacao.PUBLICADO and aprovar.moderado_por == moderador
    assert recusar.situacao == Situacao.RASCUNHO and recusar.motivo_moderacao == "Foto escura."
    assert recusar.history.first().history_user == moderador  # histórico gravado mesmo pela fila (proxy)
    assert {m.to[0] for m in mail.outbox} == {"loja@exemplo.com", "b@exemplo.com"}


def test_financeiro_nao_modera(client, entrar_no_admin, loja, imovel):
    """Financeiro vê os anúncios, mas não a fila de moderação."""
    fin = Usuario.objects.create_user(email="fin@exemplo.com", password=SENHA, nome="Fin", is_staff=True)
    fin.groups.add(Group.objects.get(name="Financeiro"))
    entrar_no_admin(fin)

    assert client.get(reverse("admin:anuncios_anuncio_changelist")).status_code == 200
    assert client.get(reverse("admin:anuncios_anuncioemmoderacao_changelist")).status_code == 403


def test_admin_nao_cria_nem_apaga_anuncio(client, entrar_no_admin, loja, publicado):
    """Nem o superusuário cria ou apaga anúncio no admin (exclusão é lógica, pelo anunciante)."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    anuncio = publicado(loja())

    assert client.get(reverse("admin:anuncios_anuncio_add")).status_code == 403
    assert client.get(reverse("admin:anuncios_anuncio_delete", args=[anuncio.pk])).status_code == 403


def test_configuracao_tem_secao_regras_do_negocio(client, entrar_no_admin):
    """Carência, validade, aviso e moderação ficam juntos em "Regras do negócio"."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    configuracao()  # o registro único nasce na primeira leitura

    html = client.get(
        reverse("admin:core_configuracao_change", args=[Configuracao.ID_UNICO])
    ).content.decode()

    secao = html[html.index("Regras do negócio") :]
    for campo in ("carencia_dias", "expiracao_dias", "aviso_expiracao_dias", "moderacao"):
        assert f'name="{campo}"' in secao
    limites = html[html.index("Limites de mídia") : html.index("Regras do negócio")]
    assert 'name="carencia_dias"' not in limites


# --- Downgrade: escolher os anúncios --------------------------------------------------------


def test_pedido_de_plano_menor_leva_a_escolha_dos_anuncios(client, loja, publicado):
    """Plano menor que o uso: depois do pedido, a tela de escolha; a escolha fica no pedido."""
    anunciante = loja(slug_plano="premium")
    a, b = (publicado(anunciante, f"Casa número {i} com quintal") for i in (1, 2))
    basico = Plano.objects.get(slug="basico")
    basico.limite_anuncios = 1
    basico.save()
    client.force_login(anunciante.usuario)

    resposta = client.post(reverse("planos:meu_plano"), {"plano": basico.pk, "periodicidade": "mensal"})
    assert resposta["Location"] == reverse("planos:escolher_anuncios")

    html = client.post(reverse("planos:escolher_anuncios"), {"manter": [a.pk, b.pk]}).content.decode()
    assert "no máximo 1" in html

    client.post(reverse("planos:escolher_anuncios"), {"manter": [b.pk]})
    assert PedidoTrocaPlano.objects.get().anuncios_manter == [b.pk]
    assert "Falta você escolher" not in client.get(reverse("planos:meu_plano")).content.decode()


def test_escolha_sem_pedido_da_404(client, loja):
    """Sem pedido pendente, a tela não existe."""
    client.force_login(loja().usuario)

    assert client.get(reverse("planos:escolher_anuncios")).status_code == 404
