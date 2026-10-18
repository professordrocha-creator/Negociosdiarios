"""Ajustes de layout, rodapé e login da equipe: rodapé sem "Admin" para ninguém, CNPJ e frase da identidade do
site, "Como denunciar", grupos de opções da busca, equipe entrando pela Área do anunciante (com o código de
navegador novo e o axes) e erro de login genérico."""

import pytest
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.services import configuracao

pytestmark = pytest.mark.django_db

NAVEGADOR = {"HTTP_USER_AGENT": "Mozilla/5.0"}


def rodape(client) -> str:
    """Só o HTML do rodapé da home."""
    return client.get(reverse("core:inicio"), **NAVEGADOR).content.decode().split("<footer", 1)[1]


@pytest.fixture
def equipe(db):
    """Membro da equipe com senha (grupo Moderador)."""
    from django.contrib.auth.models import Group

    usuario = Usuario.objects.create_user(
        email="equipe@exemplo.com", password=SENHA, nome="Equipe", is_staff=True
    )
    usuario.groups.add(Group.objects.get(name="Moderador"))
    return usuario


def entrar(client, email: str, senha: str = SENHA):
    """Login pela tela normal (/entrar/)."""
    return client.post(reverse("contas:entrar"), {"username": email, "password": senha}, **NAVEGADOR)


# --- Rodapé ------------------------------------------------------------------------------------------


def test_rodape_sem_link_admin_para_anonimo_cliente_e_equipe(client, settings, loja, equipe):
    """Nem visitante (mesmo em dev), nem cliente, nem equipe: o rodapé nunca leva ao admin."""
    settings.DEBUG = True
    admin = reverse("admin:index")
    assert admin not in rodape(client)
    client.force_login(loja().usuario)
    assert admin not in rodape(client)
    client.force_login(equipe)
    assert admin not in rodape(client)
    assert ">Admin<" not in rodape(client)


def test_cnpj_no_rodape_so_se_preenchido(client):
    """Vazio: nada de CNPJ no rodapé. Preenchido na identidade do site: formatado."""
    assert "CNPJ" not in rodape(client).split("<hr", 1)[1]
    config = configuracao()
    config.cnpj = "90000001000129"
    config.save()
    assert "CNPJ 90.000.001/0001-29" in rodape(client)


def test_slogan_e_frase_do_rodape_vem_da_identidade(client):
    """Valores atuais mantidos e editáveis no admin (vazio = a frase some)."""
    assert "Só anunciantes verificados: corretores com CRECI e revendas com CNPJ." in rodape(client)
    config = configuracao()
    config.slogan, config.frase_rodape = "Slogan novo.", ""
    config.save()
    html = rodape(client)
    assert "Slogan novo." in html and "Só anunciantes verificados" not in html


def test_rodape_leva_ao_como_denunciar(client):
    """O link do rodapé abre a página curta "Como denunciar", com "Sobre esta tela" e sem prometer prazo."""
    assert f'href="{reverse("moderacao:como_denunciar")}"' in rodape(client)
    html = client.get(reverse("moderacao:como_denunciar"), **NAVEGADOR).content.decode()
    assert 'botão <b>"Denunciar"</b>' in html and "Sobre esta tela" in html
    assert "dias" not in html.split("<main", 1)[1].split("</main>", 1)[0].lower()


# --- Busca: grupos de opções ------------------------------------------------------------------------


def test_grupos_de_opcoes_quebram_linha_e_coluna_sem_sombra(client, tangara):
    """Quartos, vagas e negócio em grupo que quebra linha (sem btn-group); coluna sem a sombra da home."""
    html = client.get(reverse("busca:imoveis"), **NAVEGADOR).content.decode()
    assert 'class="nd-opcoes"' in html and "btn-group" not in html
    assert 'class="btn btn-sm nd-opcao"' in html and 'class="col-lg-9 nd-busca"' not in html


# --- Login da equipe pela Área do anunciante ------------------------------------------------------------


def test_equipe_vai_ao_admin_e_cliente_ao_painel(client, loja, equipe):
    """Mesma tela: equipe → admin (com o código desligado em dev); cliente → painel; menu da equipe."""
    resposta = entrar(client, "equipe@exemplo.com")
    assert resposta.status_code == 302 and resposta["Location"] == reverse("admin:index")
    assert client.get(reverse("admin:index")).status_code == 200
    assert "Painel administrativo" in client.get(reverse("core:inicio"), **NAVEGADOR).content.decode()

    client.logout()
    loja()
    resposta = entrar(client, "loja@exemplo.com")
    assert resposta.status_code == 302 and resposta["Location"] != reverse("admin:index")
    assert "Painel administrativo" not in client.get(reverse("core:inicio"), **NAVEGADOR).content.decode()


def test_equipe_sem_codigo_em_navegador_novo_nao_entra(client, settings, equipe):
    """Com ADMIN_CODIGO_EMAIL ligado: a senha certa leva à tela do código e o admin continua fechado."""
    settings.DEBUG, settings.ADMIN_CODIGO_EMAIL = False, True

    resposta = entrar(client, "equipe@exemplo.com")

    assert resposta["Location"].startswith(reverse("admin:verificar"))
    painel = client.get(reverse("admin:index"))
    assert painel.status_code == 302  # sem o código, o admin continua fechado (volta ao login)


def test_erro_de_login_igual_para_email_inexistente_e_senha_errada(client, loja):
    """Não revela quem tem conta: a mesma mensagem nos dois casos."""
    loja()
    inexistente = entrar(client, "ninguem@exemplo.com", "qualquer").content.decode()
    senha_errada = entrar(client, "loja@exemplo.com", "errada").content.decode()

    mensagem = "E-mail ou senha incorretos."
    assert mensagem in inexistente and mensagem in senha_errada


def test_url_secreta_continua_funcionando(client, equipe):
    """A segunda porta: o login do admin direto."""
    resposta = client.post(
        reverse("admin:login"),
        {"username": "equipe@exemplo.com", "password": SENHA, "next": reverse("admin:index")},
    )
    assert resposta.status_code == 302 and client.get(reverse("admin:index")).status_code == 200
