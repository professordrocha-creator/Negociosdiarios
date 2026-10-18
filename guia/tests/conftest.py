"""Fixtures dos testes do guia: categorias carregadas do CSV, termo em vigor, perfil pronto para o convite e
usuários da equipe por grupo."""

import datetime

import pytest
from django.contrib.auth.models import Group
from django.contrib.gis.geos import Point

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from guia import services
from guia.models import CategoriaServico, PerfilGuia, TermoGuia


@pytest.fixture
def categorias(db):
    """As 82 categorias do docs/guia/categorias_iniciais.csv, por slug."""
    services.carregar_categorias()
    return {c.slug: c for c in CategoriaServico.objects.all()}


@pytest.fixture
def termo(db):
    """A versão inicial do termo (criada pela migration 0002), em vigor desde antes de hoje."""
    TermoGuia.objects.update(vigente_desde=datetime.date(2026, 1, 1))
    return TermoGuia.objects.get()


@pytest.fixture
def perfil_pronto(tangara, categorias, termo):
    """Fábrica: perfil completo (tudo menos o aceite), em rascunho, com endereço comercial em Tangará."""

    def _criar(nome="Vidraçaria Teste", whatsapp="+5565999990101", slugs=("eletricista",), **campos):
        perfil = PerfilGuia.objects.create(
            nome_publico=nome,
            tipo=campos.pop("tipo", PerfilGuia.Tipo.EMPRESA),
            cnpj=campos.pop("cnpj", "90000001000129"),
            responsavel_nome="Maria Responsável",
            responsavel_contato="maria@exemplo.com",
            whatsapp=whatsapp,
            cidade=tangara,
            atendimento=PerfilGuia.Atendimento.ENDERECO,
            endereco="Rua das Flores, 100",
            ponto=Point(-57.001, -14.001, srid=4326),
            **campos,
        )
        perfil.categorias.set([categorias[s] for s in slugs])
        return perfil

    return _criar


@pytest.fixture
def membro(db):
    """Fábrica: usuário da equipe (staff) num grupo."""

    def _criar(grupo: str) -> Usuario:
        usuario = Usuario.objects.create_user(
            email=f"{grupo.lower()}@exemplo.com", password=SENHA, nome=f"{grupo} Teste", is_staff=True
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return usuario

    return _criar


@pytest.fixture
def admin_guia(membro, entrar_no_admin):
    """Client logado no admin como membro do grupo Guia (navegador já verificado)."""
    return entrar_no_admin(membro("Guia"))


def dados_do_formulario(perfil: PerfilGuia | None = None, **extra) -> dict:
    """POST completo do cadastro assistido no admin (com os formulários das listas de aceites e convites)."""
    dados = {
        "tipo": "empresa",
        "nome_publico": "Vidraçaria Nova",
        "categorias": [],
        "frase": "",
        "whatsapp": "(65) 99999-0202",
        "telefone": "",
        "cidade": "",
        "bairro": "",
        "atendimento": "atende_em_endereco",
        "endereco": "Av. Brasil, 200",
        "latitude": "-14.001",
        "longitude": "-57.001",
        "area_atendimento": "",
        "cnpj": "90.000.002/0001-73",
        "cnpj_verificado_em": "",
        "cpf": "",
        "registro_profissional": "",
        "responsavel_nome": "João Dono",
        "responsavel_contato": "joao@exemplo.com",
        "anunciante": "",
        "anotacoes": "",
        **{f"horario_{dia}": "" for dia, _ in services.DIAS_DA_SEMANA},
    }
    for prefixo, relacao in (("aceites", "aceites"), ("convites", "convites")):
        total = getattr(perfil, relacao).count() if perfil else 0
        dados.update(
            {
                f"{prefixo}-TOTAL_FORMS": str(total),
                f"{prefixo}-INITIAL_FORMS": str(total),
                f"{prefixo}-MIN_NUM_FORMS": "0",
                f"{prefixo}-MAX_NUM_FORMS": "1000",
            }
        )
        if perfil:
            for i, obj in enumerate(getattr(perfil, relacao).all()):
                dados[f"{prefixo}-{i}-id"] = str(obj.pk)
                dados[f"{prefixo}-{i}-perfil"] = str(perfil.pk)
    dados.update(extra)
    return dados


@pytest.fixture
def guia_ligado(db):
    """Liga a aba do guia (ConfiguracaoGuia.ativo)."""
    config = services.configuracao_guia()
    config.ativo = True
    config.save()
    return config


@pytest.fixture
def perfil_publicado(perfil_pronto):
    """Fábrica: perfil completo e já publicado pelo caminho de verdade (convite + aceite)."""

    def _criar(**campos):
        perfil = perfil_pronto(**campos)
        _, token = services.gerar_convite(perfil)
        services.aceitar_convite(token, "Maria Responsável", avisar=False)
        perfil.refresh_from_db()
        return perfil

    return _criar
