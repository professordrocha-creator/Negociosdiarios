"""Testes do login do cliente (/entrar/) e do painel (/painel/): quem entra e o que cada um vê."""

import pytest
from django.urls import reverse

from anunciantes.models import Anunciante
from anunciantes.tests.conftest import SENHA
from contas.models import Usuario

pytestmark = pytest.mark.django_db


def entrar(client, email: str, senha: str = SENHA):
    """Envia o formulário de /entrar/."""
    return client.post(reverse("contas:entrar"), {"username": email, "password": senha})


# --- Login do cliente ---------------------------------------------------------------------


def test_anunciante_ativo_entra_e_vai_ao_painel(client, criar_anunciante):
    """E-mail e senha certos, loja ativa: vai para o painel (sem código por e-mail)."""
    criar_anunciante("loja@exemplo.com", "Loja Ativa")

    resposta = entrar(client, "Loja@Exemplo.com")

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("anunciantes:painel")
    assert client.get(reverse("anunciantes:painel")).status_code == 200


def test_senha_errada_nao_entra(client, criar_anunciante):
    """Senha errada: volta ao formulário, sem sessão."""
    criar_anunciante("loja@exemplo.com", "Loja Ativa")

    resposta = entrar(client, "loja@exemplo.com", senha="errada")

    assert resposta.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize(
    ("status", "trecho"),
    [(Anunciante.Status.PENDENTE, "em análise"), (Anunciante.Status.SUSPENSO, "suspensa")],
)
def test_anunciante_pendente_ou_suspenso_nao_entra(client, criar_anunciante, status, trecho):
    """Loja não ativa: senha certa, mas o login é recusado com mensagem que explica."""
    criar_anunciante("loja@exemplo.com", "Loja X", status=status)

    resposta = entrar(client, "loja@exemplo.com")

    assert resposta.status_code == 200
    assert trecho in resposta.content.decode()
    assert "_auth_user_id" not in client.session


def test_equipe_pelo_login_do_cliente_vai_ao_admin(client, db):
    """Conta da equipe (staff) que entra pela Área do anunciante é levada ao admin, nunca ao painel do
    cliente (com a mesma verificação do login do admin: ver core/tests/test_rodape_e_login_equipe.py)."""
    Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")

    resposta = entrar(client, "daniel@exemplo.com")

    assert resposta.status_code == 302 and resposta["Location"] == reverse("admin:index")
    assert client.get(reverse("anunciantes:painel"))["Location"] == reverse("admin:index")


def test_usuario_sem_loja_nao_entra(client, db):
    """Conta comum sem anunciante: recusada, com indicação dos planos."""
    Usuario.objects.create_user(email="sem@exemplo.com", password=SENHA, nome="Sem Loja")

    resposta = entrar(client, "sem@exemplo.com")

    assert "não tem loja cadastrada" in resposta.content.decode()
    assert "_auth_user_id" not in client.session


def test_sair_desloga_e_volta_ao_inicio(client, criar_anunciante):
    """Sair (POST) encerra a sessão e leva à página inicial."""
    criar_anunciante("loja@exemplo.com", "Loja Ativa")
    entrar(client, "loja@exemplo.com")

    resposta = client.post(reverse("contas:sair"))

    assert resposta["Location"] == reverse("core:inicio")
    assert "_auth_user_id" not in client.session


def test_rodape_leva_a_area_do_anunciante_para_o_entrar(client, db):
    """O link "Área do anunciante" do rodapé aponta para /entrar/."""
    html = client.get(reverse("core:inicio")).content.decode()

    assert f'<a href="{reverse("contas:entrar")}">Área do anunciante</a>' in html


# --- Painel -------------------------------------------------------------------------------


def test_painel_sem_login_vai_para_o_entrar(client, db):
    """Visitante anônimo é mandado ao login, com volta ao painel."""
    resposta = client.get(reverse("anunciantes:painel"))

    assert resposta.status_code == 302
    assert resposta["Location"] == f"{reverse('contas:entrar')}?next={reverse('anunciantes:painel')}"


def test_equipe_logada_vai_do_painel_ao_admin(client, db):
    """Equipe já logada (pelo admin) que abre o painel do cliente ou o /entrar/ é levada ao admin, sem 403."""
    equipe = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    client.force_login(equipe)

    for url in (reverse("anunciantes:painel"), reverse("contas:entrar")):
        resposta = client.get(url)
        assert resposta.status_code == 302 and resposta["Location"] == reverse("admin:index"), url


@pytest.mark.parametrize("codigo_ligado", [False, True])
def test_superusuario_sem_loja_pelo_login_do_cliente_chega_ao_admin(client, db, settings, codigo_ligado):
    """Regressão: superusuário SEM anunciante, vindo do painel (?next=/painel/), entra pela tela do cliente e
    chega ao admin; com ADMIN_CODIGO_EMAIL ligado passa pelo código (sem atalho), nunca por "sem loja"."""
    settings.ADMIN_CODIGO_EMAIL = codigo_ligado
    Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    ida = client.get(reverse("anunciantes:painel"))

    resposta = client.post(ida["Location"], {"username": "daniel@exemplo.com", "password": SENHA})

    destino = reverse("admin:index")
    if codigo_ligado:
        assert resposta["Location"].startswith(reverse("admin:verificar"))
        assert client.get(destino).status_code == 302  # admin ainda fechado: falta o código
        assert client.get(reverse("anunciantes:painel"))["Location"].startswith(reverse("admin:verificar"))
    else:
        assert resposta["Location"] == destino
        assert client.get(destino).status_code == 200
        assert client.get(reverse("anunciantes:painel"))["Location"] == destino


def test_cliente_comum_vai_ao_painel_e_nao_ao_admin(client, criar_anunciante):
    """Cliente com loja ativa entra pela mesma tela e vai ao painel dele; o admin continua fechado."""
    criar_anunciante("loja@exemplo.com", "Loja X", status=Anunciante.Status.ATIVO)

    resposta = entrar(client, "loja@exemplo.com")

    assert resposta["Location"] == reverse("anunciantes:painel")
    assert client.get(reverse("anunciantes:painel")).status_code == 200
    assert client.get(reverse("admin:index")).status_code == 302  # vai ao login do admin, não entra


def test_menu_mostra_painel_administrativo_so_para_a_equipe(client, criar_anunciante, db):
    """Topo: equipe vê "Painel administrativo"; cliente vê "Meu painel"."""
    anunciante = criar_anunciante("loja@exemplo.com", "Loja X", status=Anunciante.Status.ATIVO)
    client.force_login(anunciante.usuario)
    cliente = client.get(reverse("core:inicio")).content.decode()
    client.force_login(Usuario.objects.create_superuser(email="d@exemplo.com", password=SENHA, nome="D"))
    equipe = client.get(reverse("core:inicio")).content.decode()

    assert "Meu painel" in cliente and "Painel administrativo" not in cliente
    assert "Painel administrativo" in equipe and "Meu painel" not in equipe


def test_anunciante_pendente_logado_nao_entra_no_painel(client, criar_anunciante):
    """Se a loja deixou de estar ativa com a sessão aberta, o painel fecha na hora."""
    anunciante = criar_anunciante("loja@exemplo.com", "Loja X", status=Anunciante.Status.PENDENTE)
    client.force_login(anunciante.usuario)

    assert client.get(reverse("anunciantes:painel")).status_code == 403


def test_cliente_a_nao_ve_dados_do_cliente_b(client, criar_anunciante):
    """O painel mostra só a loja de quem está logado (sem id na URL, sem IDOR)."""
    a = criar_anunciante("a@exemplo.com", "Loja Alfa", email_publico="publico-a@exemplo.com")
    criar_anunciante("b@exemplo.com", "Loja Beta", email_publico="publico-b@exemplo.com")
    client.force_login(a.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Loja Alfa" in html and "publico-a@exemplo.com" in html
    assert "Loja Beta" not in html and "publico-b@exemplo.com" not in html


def test_painel_mostra_dados_da_loja_e_aviso_sem_plano(client, criar_anunciante):
    """Dados da loja formatados; sem assinatura, o card do plano leva a "Meu plano"."""
    anunciante = criar_anunciante("loja@exemplo.com", "Loja Alfa")
    client.force_login(anunciante.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "90.000.001/0001-29" in html  # CNPJ formatado
    assert "(65) 99999-0001" in html  # WhatsApp formatado
    assert "Tangará da Serra/MT" in html
    assert "Você ainda não tem plano" in html
    assert reverse("planos:meu_plano") in html
    assert "Você ainda não tem anúncios" in html  # loja real: nada do demo.json


def test_loja_real_com_slug_de_demo_nao_ve_anuncios_ficticios(client, criar_anunciante):
    """Só lojas demo leem o demo.json: uma loja real com o mesmo endereço não herda anúncios."""
    anunciante = criar_anunciante("loja@exemplo.com", "Garagem Rota 358")
    assert anunciante.slug == "garagem-rota-358" and not anunciante.demo
    client.force_login(anunciante.usuario)

    html = client.get(reverse("anunciantes:painel")).content.decode()

    assert "Toyota Hilux" not in html
