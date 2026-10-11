"""Testes dos grupos de permissão criados pela migration contas/0002 (docs/ADMINISTRACAO.md)."""

import pytest
from django.contrib.auth.models import Group, Permission

pytestmark = pytest.mark.django_db

SO_CIDADES = {"core.view_estado", "core.view_cidade"}
VER_ANUNCIANTE = {"anunciantes.view_anunciante"}
GEOGRAFIA = {"core.view_regiao", "core.view_bairro"}
# Sprint 2, parte B (planos/0002): Financeiro e Administrador cuidam de planos, assinaturas e pedidos.
PLANOS_VER = {"planos.view_plano", "planos.view_assinatura", "planos.view_pedidotrocaplano"}
PLANOS_TUDO = PLANOS_VER | {
    "planos.add_plano",
    "planos.change_plano",
    "planos.add_assinatura",
    "planos.change_assinatura",
    "planos.change_pedidotrocaplano",
}

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
        "anunciantes.view_anunciante",
        "anunciantes.add_anunciante",
        "anunciantes.change_anunciante",
        "anunciantes.view_historicalanunciante",
        # Sprint 1, parte 3 (core/0004 e anunciantes/0004): identidade, textos, geografia, cidades pedidas.
        "core.view_configuracao",
        "core.change_configuracao",
        "core.view_valorempresa",
        "core.add_valorempresa",
        "core.change_valorempresa",
        "core.view_textoajuda",
        "core.add_textoajuda",
        "core.change_textoajuda",
        "core.view_regiao",
        "core.add_regiao",
        "core.change_regiao",
        "core.view_bairro",
        "core.add_bairro",
        "core.change_bairro",
        "anunciantes.view_solicitacaocidade",
        "anunciantes.change_solicitacaocidade",
    }
    | PLANOS_TUDO,
    # Moderador aprova e suspende anunciantes (anunciantes/0002) e vê os pedidos de cidade.
    "Moderador": SO_CIDADES
    | VER_ANUNCIANTE
    | GEOGRAFIA
    | {
        "anunciantes.change_anunciante",
        "anunciantes.view_historicalanunciante",
        "anunciantes.view_solicitacaocidade",
    }
    | PLANOS_VER,
    "Financeiro": SO_CIDADES | VER_ANUNCIANTE | GEOGRAFIA | PLANOS_TUDO,
    "Comercial": SO_CIDADES | VER_ANUNCIANTE | GEOGRAFIA | PLANOS_VER,
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
    proibidas = Permission.objects.filter(
        codename__in=["delete_usuario", "delete_anunciante"]
    ) | Permission.objects.filter(content_type__app_label__in=["otp_email", "otp_static"])

    assert not Group.objects.filter(permissions__in=proibidas).exists()
