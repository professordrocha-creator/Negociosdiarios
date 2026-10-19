"""Testes do lote de correções no admin (core): caixa "Pendências" por permissão, nomes novos dos menus,
rótulo do "mostrar botão Renovar" e os estáticos versionados ligados por variável."""

import environ
import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from config.settings import armazenamento_de_midia
from contas.models import Usuario
from core.models import Configuracao

pytestmark = pytest.mark.django_db


def entrar(entrar_no_admin, grupo: str):
    """Client no admin como membro do grupo."""
    usuario = Usuario.objects.create_user(
        email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=grupo, is_staff=True
    )
    usuario.groups.add(Group.objects.get(name=grupo))
    return entrar_no_admin(usuario)


def test_pendencias_so_do_que_o_grupo_pode_ver(entrar_no_admin, criar_anunciante):
    """Moderador: denúncias, pedidos do guia e lojas pendentes; não vê faturas nem privacidade."""
    from anunciantes.models import Anunciante

    criar_anunciante("pendente@exemplo.com", "Loja Pendente", status=Anunciante.Status.PENDENTE)
    pagina = entrar(entrar_no_admin, "Moderador").get(reverse("admin:index")).content.decode()

    assert "Pendências" in pagina
    assert "Denúncias pendentes" in pagina and "Pedidos do Guia de Negócios" in pagina
    assert '<b class="nd-pendencia-numero">1</b> Lojas pendentes de aprovação' in pagina
    assert "?status__exact=pendente" in pagina
    assert "Comprovantes aguardando" not in pagina and "Pedidos de privacidade do site" not in pagina


def test_pendencias_do_financeiro_e_do_dono(entrar_no_admin, client):
    """Financeiro vê comprovantes (e lojas), não denúncias; o superusuário vê os seis contadores."""
    pagina = entrar(entrar_no_admin, "Financeiro").get(reverse("admin:index")).content.decode()
    assert "Comprovantes aguardando confirmação" in pagina and "Denúncias pendentes" not in pagina

    dono = Usuario.objects.create_superuser(email="dono@exemplo.com", password=SENHA, nome="Dono")
    pagina = entrar_no_admin(dono).get(reverse("admin:index")).content.decode()
    assert pagina.count('class="nd-pendencia-numero"') == 6  # + "Interessados no Guia"


def test_menus_com_nomes_novos(entrar_no_admin):
    """ "Configurações do site" (antes "Identidade do site") e "Faturas e pagamentos" (antes "Cobrança")."""
    dono = Usuario.objects.create_superuser(email="dono@exemplo.com", password=SENHA, nome="Dono")
    pagina = entrar_no_admin(dono).get(reverse("admin:index")).content.decode()
    assert "Configurações do site" in pagina and "Faturas e pagamentos" in pagina
    assert "Identidade do site" not in pagina and ">Cobrança<" not in pagina


def test_rotulo_do_botao_renovar():
    """O campo não promete e-mail: só o botão Renovar."""
    campo = Configuracao._meta.get_field("aviso_expiracao_dias")
    assert campo.verbose_name == "mostrar botão Renovar a partir de (dias antes)"
    assert "Não envia e-mail" in campo.help_text


def test_estaticos_versionados_por_variavel(monkeypatch, tmp_path):
    """ESTATICOS_VERSIONADOS=True (produção): nomes com hash; sem ela (dev/testes), o armazenamento comum."""
    env = environ.Env()
    monkeypatch.setenv("ESTATICOS_VERSIONADOS", "True")
    assert armazenamento_de_midia("local", env, tmp_path)[0]["staticfiles"]["BACKEND"] == (
        "core.estaticos.EstaticosVersionados"
    )
    monkeypatch.delenv("ESTATICOS_VERSIONADOS")
    assert armazenamento_de_midia("local", env, tmp_path)[0]["staticfiles"]["BACKEND"].endswith(
        "StaticFilesStorage"
    )


def test_estaticos_versionados_ignoram_source_map():
    """Nenhuma regra de sourceMappingURL (os .map das bibliotecas não estão no projeto)."""
    from core.estaticos import EstaticosVersionados

    regras = repr(EstaticosVersionados.patterns)
    assert "sourceMappingURL" not in regras and "url\\\\(" in regras
