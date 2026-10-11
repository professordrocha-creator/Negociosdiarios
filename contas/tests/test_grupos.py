"""Testes dos grupos de permissão criados pela migration contas/0002 (docs/ADMINISTRACAO.md)."""

import pytest
from django.contrib.auth.models import Group, Permission

pytestmark = pytest.mark.django_db

SO_CIDADES = {"core.view_estado", "core.view_cidade"}

ESPERADO = {
    "Administrador": {
        "contas.view_usuario",
        "contas.add_usuario",
        "contas.change_usuario",
        "auth.view_group",
        "core.view_estado",
        "core.change_estado",
        "core.view_cidade",
        "core.change_cidade",
        "axes.view_accessattempt",
        "axes.delete_accessattempt",
        "admin.view_logentry",
    },
    "Moderador": SO_CIDADES,
    "Financeiro": SO_CIDADES,
    "Comercial": SO_CIDADES,
}


def permissoes(grupo: Group) -> set[str]:
    """Permissões do grupo no formato "app.codename"."""
    return {
        f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.select_related("content_type")
    }


def test_os_quatro_grupos_existem():
    """A migration cria exatamente os perfis do docs/ADMINISTRACAO.md."""
    assert set(Group.objects.values_list("name", flat=True)) == set(ESPERADO)


@pytest.mark.parametrize("nome", ESPERADO)
def test_permissoes_de_cada_grupo(nome):
    """Cada grupo tem só as permissões previstas, nada a mais."""
    assert permissoes(Group.objects.get(name=nome)) == ESPERADO[nome]


def test_nenhum_grupo_apaga_usuario_nem_mexe_em_codigos_de_acesso():
    """Exclusão de usuário é lógica, e códigos de acesso de terceiros são só com o superusuário."""
    proibidas = Permission.objects.filter(codename="delete_usuario") | Permission.objects.filter(
        content_type__app_label__in=["otp_email", "otp_static"]
    )

    assert not Group.objects.filter(permissions__in=proibidas).exists()
