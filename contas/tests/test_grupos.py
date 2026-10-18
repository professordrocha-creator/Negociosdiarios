"""Testes dos grupos de permissão criados pela migration contas/0002 (docs/ADMINISTRACAO.md)."""

import pytest
from django.contrib.auth.models import Group, Permission

pytestmark = pytest.mark.django_db

SO_CIDADES = {"core.view_estado", "core.view_cidade"}
VER_ANUNCIANTE = {"anunciantes.view_anunciante"}
GEOGRAFIA = {"core.view_regiao", "core.view_bairro"}
# Sprint 2, parte B (planos/0002): Financeiro e Administrador cuidam de planos, assinaturas e pedidos.
PLANOS_VER = {"planos.view_plano", "planos.view_assinatura", "planos.view_pedidotrocaplano"}
# Sprint 3 (anuncios/0002): Administrador e Moderador moderam; Financeiro e Comercial só consultam.
# Sprint 4 (anuncios/0006, catalogo/0002): ficha de veículo e catálogo FIPE ("ativo": só o Administrador).
CATALOGO_VER = {"catalogo.view_marca", "catalogo.view_modelo", "catalogo.view_versao"}
CATALOGO_TUDO = CATALOGO_VER | {"catalogo.change_marca", "catalogo.change_modelo", "catalogo.change_versao"}
ANUNCIOS_VER = {"anuncios.view_anuncio", "anuncios.view_detalheimovel", "anuncios.view_detalheveiculo"}
ANUNCIOS_MODERAR = ANUNCIOS_VER | {
    "anuncios.view_historicalanuncio",
    "anuncios.view_anuncioemmoderacao",
    "anuncios.change_anuncioemmoderacao",
}
PLANOS_TUDO = PLANOS_VER | {
    "planos.add_plano",
    "planos.change_plano",
    "planos.add_assinatura",
    "planos.change_assinatura",
    "planos.change_pedidotrocaplano",
}
# Sprint 6 (pagamentos/0002): só Financeiro e Administrador veem e decidem faturas e editam os e-mails
# de cobrança (Moderador e Comercial não veem faturas, docs/ADMINISTRACAO.md).
COBRANCA = {
    "pagamentos.view_fatura",
    "pagamentos.change_fatura",
    "pagamentos.view_modeloemailcobranca",
    "pagamentos.change_modeloemailcobranca",
}
# Sprint 7A (publicidade/0002): Comercial e Administrador vendem e cadastram; Financeiro só consulta.
PUBLICIDADE_VER = {"publicidade.view_patrocinador", "publicidade.view_campanha"}
PUBLICIDADE_TUDO = PUBLICIDADE_VER | {
    "publicidade.add_patrocinador",
    "publicidade.change_patrocinador",
    "publicidade.add_campanha",
    "publicidade.change_campanha",
    "publicidade.view_banner",
    "publicidade.add_banner",
    "publicidade.change_banner",
}
# Sprint 7B (privacidade/0002): só o Administrador cuida dos documentos legais e dos pedidos dos titulares.
PRIVACIDADE = {
    "privacidade.view_documentolegal",
    "privacidade.add_documentolegal",
    "privacidade.change_documentolegal",
    "privacidade.view_pedidotitular",
    "privacidade.add_pedidotitular",
    "privacidade.change_pedidotitular",
}
# Sprint 7B parte 2 (moderacao/0002): Moderador e Administrador decidem as denúncias.
DENUNCIAS = {"moderacao.view_denuncia", "moderacao.change_denuncia"}

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
    | PLANOS_TUDO
    | ANUNCIOS_MODERAR
    | CATALOGO_TUDO
    | COBRANCA
    | PUBLICIDADE_TUDO
    | PRIVACIDADE
    | DENUNCIAS,
    # Moderador aprova e suspende anunciantes (anunciantes/0002) e vê os pedidos de cidade.
    "Moderador": SO_CIDADES
    | VER_ANUNCIANTE
    | GEOGRAFIA
    | {
        "anunciantes.change_anunciante",
        "anunciantes.view_historicalanunciante",
        "anunciantes.view_solicitacaocidade",
    }
    | PLANOS_VER
    | ANUNCIOS_MODERAR
    | CATALOGO_VER
    | DENUNCIAS,
    "Financeiro": SO_CIDADES
    | VER_ANUNCIANTE
    | GEOGRAFIA
    | PLANOS_TUDO
    | ANUNCIOS_VER
    | CATALOGO_VER
    | COBRANCA
    | PUBLICIDADE_VER,
    "Comercial": SO_CIDADES
    | VER_ANUNCIANTE
    | GEOGRAFIA
    | PLANOS_VER
    | ANUNCIOS_VER
    | CATALOGO_VER
    | PUBLICIDADE_TUDO,
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
