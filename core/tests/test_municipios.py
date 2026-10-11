"""Testes da carga de estados/cidades do IBGE e da liberação de cidades."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.urls import reverse

from contas.models import Usuario
from core.models import Cidade, Estado
from core.services import carregar_municipios, liberar_cidades

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"

ESTADOS_CSV = """codigo_ibge,uf,nome
51,MT,Mato Grosso
24,RN,Rio Grande do Norte
42,SC,Santa Catarina
"""

MUNICIPIOS_CSV = """codigo_ibge,nome,uf,latitude,longitude
5107958,Tangará da Serra,MT,-14.6229,-57.4933
5103403,Cuiabá,MT,-15.601,-56.0974
2414001,Tangará,RN,-6.19649,-35.7989
4217907,Tangará,SC,-27.0996,-51.2473
"""


@pytest.fixture
def arquivos(tmp_path):
    """Grava CSVs pequenos de teste e devolve (estados, municipios)."""
    estados = tmp_path / "estados.csv"
    municipios = tmp_path / "municipios.csv"
    estados.write_text(ESTADOS_CSV, encoding="utf-8")
    municipios.write_text(MUNICIPIOS_CSV, encoding="utf-8")
    return estados, municipios


def test_carga_cria_estados_e_cidades(arquivos):
    """A carga cria tudo e informa quantos registros são novos."""
    resultado = carregar_municipios(*arquivos)

    assert (resultado.estados_total, resultado.estados_novos) == (3, 3)
    assert (resultado.cidades_total, resultado.cidades_novas) == (4, 4)
    tangara = Cidade.objects.get(codigo_ibge=5107958)
    assert tangara.nome == "Tangará da Serra"
    assert tangara.uf_id == "MT"
    assert (round(tangara.ponto.x, 4), round(tangara.ponto.y, 4)) == (-57.4933, -14.6229)  # x = longitude


def test_depois_da_carga_so_mt_liberado_e_nenhuma_cidade(arquivos):
    """Primeira carga: só MT liberado; nenhuma cidade liberada (o admin libera)."""
    carregar_municipios(*arquivos)

    assert list(Estado.objects.filter(liberado=True).values_list("uf", flat=True)) == ["MT"]
    assert not Cidade.objects.filter(liberada=True).exists()


def test_slug_sem_acento(arquivos):
    """Slug é o nome sem acentos, em minúsculas e com hífens."""
    carregar_municipios(*arquivos)

    assert Cidade.objects.get(codigo_ibge=5107958).slug == "tangara-da-serra"
    assert Cidade.objects.get(codigo_ibge=5103403).slug == "cuiaba"


def test_cidades_com_mesmo_nome_em_estados_diferentes(arquivos):
    """'Tangará' existe no RN e em SC: mesmo slug, cidades distintas, separadas pela UF."""
    carregar_municipios(*arquivos)

    tangaras = Cidade.objects.filter(slug="tangara").order_by("uf_id")
    assert [(c.uf_id, c.codigo_ibge) for c in tangaras] == [("RN", 2414001), ("SC", 4217907)]
    assert Cidade.objects.get(uf_id="SC", slug="tangara").codigo_ibge == 4217907


def test_slug_repetido_no_mesmo_estado_e_recusado(arquivos):
    """Dentro de um estado o slug é único (é ele que identifica a cidade na URL)."""
    carregar_municipios(*arquivos)

    with pytest.raises(IntegrityError):
        Cidade.objects.create(
            codigo_ibge=5199999,
            nome="Tangara da Serra",
            slug="tangara-da-serra",
            uf_id="MT",
            ponto="POINT(-57 -14)",
        )


def test_rodar_duas_vezes_nao_duplica(arquivos):
    """Segunda carga não cria nada novo."""
    carregar_municipios(*arquivos)
    resultado = carregar_municipios(*arquivos)

    assert (resultado.estados_novos, resultado.cidades_novas) == (0, 0)
    assert Estado.objects.count() == 3
    assert Cidade.objects.count() == 4


def test_recarga_nao_desfaz_liberacoes_do_admin(arquivos):
    """O que o admin ligou ou desligou continua igual depois de recarregar."""
    carregar_municipios(*arquivos)
    Estado.objects.filter(uf="SC").update(liberado=True)
    Estado.objects.filter(uf="MT").update(liberado=False)
    Cidade.objects.filter(codigo_ibge=5107958).update(liberada=True)

    carregar_municipios(*arquivos)

    assert set(Estado.objects.filter(liberado=True).values_list("uf", flat=True)) == {"SC"}
    assert list(Cidade.objects.filter(liberada=True).values_list("codigo_ibge", flat=True)) == [5107958]


def test_recarga_atualiza_dados_do_ibge(arquivos):
    """Se o IBGE muda um nome, a recarga atualiza nome e slug sem mexer na liberação."""
    estados, municipios = arquivos
    carregar_municipios(estados, municipios)
    Cidade.objects.filter(codigo_ibge=5103403).update(liberada=True)
    municipios.write_text(MUNICIPIOS_CSV.replace("Cuiabá", "Cuiabá Nova"), encoding="utf-8")

    carregar_municipios(estados, municipios)

    cuiaba = Cidade.objects.get(codigo_ibge=5103403)
    assert (cuiaba.nome, cuiaba.slug, cuiaba.liberada) == ("Cuiabá Nova", "cuiaba-nova", True)


def test_linha_invalida_cancela_toda_a_carga(arquivos):
    """Erro em uma linha: mensagem com o número da linha e nada gravado."""
    estados, municipios = arquivos
    municipios.write_text(MUNICIPIOS_CSV + "9999999,Lugar Nenhum,XX,0,0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="linha 6"):
        carregar_municipios(estados, municipios)

    assert not Estado.objects.exists()
    assert not Cidade.objects.exists()


def test_comando_carregar_municipios(arquivos):
    """O comando roda a carga e mostra o resumo."""
    estados, municipios = arquivos
    saida = StringIO()

    call_command("carregar_municipios", estados=estados, municipios=municipios, stdout=saida)

    assert "Cidades: 4 (4 novas)" in saida.getvalue()


def test_comando_com_uf_inexistente_falha_sem_gravar(arquivos):
    """UF inicial que não existe no CSV gera erro claro."""
    estados, municipios = arquivos

    with pytest.raises(CommandError, match="ZZ"):
        call_command("carregar_municipios", estados=estados, municipios=municipios, uf_liberada="ZZ")

    assert not Estado.objects.exists()


def test_carga_do_csv_real():
    """O CSV versionado carrega os 27 estados e 5.571 municípios do IBGE."""
    resultado = carregar_municipios()

    assert resultado.estados_total == 27
    assert resultado.cidades_total == 5571
    assert Cidade.objects.filter(uf_id="MT").count() == 142
    assert Cidade.objects.get(uf_id="MT", slug="tangara-da-serra").codigo_ibge == 5107958


def test_liberar_cidades_conta_so_as_que_mudaram(arquivos):
    """liberar_cidades ignora as que já estavam liberadas."""
    carregar_municipios(*arquivos)
    Cidade.objects.filter(codigo_ibge=5103403).update(liberada=True)

    assert liberar_cidades(Cidade.objects.filter(uf_id="MT")) == 1
    assert Cidade.objects.filter(uf_id="MT", liberada=True).count() == 2


def test_acao_do_admin_libera_cidades_selecionadas(client, entrar_no_admin, arquivos):
    """A ação em massa do admin libera só as cidades marcadas e avisa sobre estado bloqueado."""
    carregar_municipios(*arquivos)
    admin = Usuario.objects.create_superuser(email="admin@exemplo.com", password=SENHA, nome="Admin")
    entrar_no_admin(admin)
    selecionadas = Cidade.objects.filter(codigo_ibge__in=[5107958, 2414001])

    resposta = client.post(
        reverse("admin:core_cidade_changelist"),
        {"action": "liberar_selecionadas", "_selected_action": [c.pk for c in selecionadas]},
        follow=True,
    )

    assert set(Cidade.objects.filter(liberada=True).values_list("codigo_ibge", flat=True)) == {
        5107958,
        2414001,
    }
    conteudo = resposta.content.decode()
    assert "2 cidade(s) liberada(s)." in conteudo
    assert "RN" in conteudo and "não está liberado" in conteudo


@pytest.mark.parametrize(
    "rota", ["admin:core_cidade_changelist", "admin:core_estado_changelist", "admin:core_cidade_change"]
)
def test_paginas_do_admin_abrem(client, entrar_no_admin, arquivos, rota):
    """Listas e edição de cidade abrem; busca e filtros funcionam."""
    carregar_municipios(*arquivos)
    admin = Usuario.objects.create_superuser(email="admin@exemplo.com", password=SENHA, nome="Admin")
    entrar_no_admin(admin)
    args = [Cidade.objects.get(codigo_ibge=5107958).pk] if rota.endswith("change") else []

    resposta = client.get(reverse(rota, args=args), {"q": "tang"} if not args else {})

    assert resposta.status_code == 200
