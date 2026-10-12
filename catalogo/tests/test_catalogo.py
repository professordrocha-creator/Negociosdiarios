"""Testes do catálogo de veículos: nomes da FIPE, carga idempotente, comandos e admin."""

import csv

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from catalogo import fipe
from catalogo.models import Marca, Modelo, Versao
from catalogo.services import (
    ARQUIVO_FIPE,
    COLUNAS,
    carregar_catalogo,
    marcas_do_tipo,
    modelos_da_marca,
    nome_da_marca,
    separar_modelo_e_versao,
    tipo_do_carro,
    versoes_do_modelo,
)
from contas.models import Usuario


def gravar_csv(caminho, linhas):
    """CSV pequeno no formato do fipe.csv."""
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


LINHAS = [
    {
        "tipo": "caminhonete",
        "marca": "Toyota",
        "modelo": "Hilux",
        "versao": "CD SRV 4x4 2.8 TDI Diesel Aut.",
        "codigo_fipe": "7406",
    },
    {
        "tipo": "carro",
        "marca": "Toyota",
        "modelo": "Corolla",
        "versao": "XEi 2.0 Flex 16V Aut.",
        "codigo_fipe": "6000",
    },
    {"tipo": "moto", "marca": "Toyota", "modelo": "Teste", "versao": "125", "codigo_fipe": "1"},
    {"tipo": "moto", "marca": "Honda", "modelo": "CG", "versao": "160 FAN Flex", "codigo_fipe": "8000"},
]


# --- Nomes da FIPE --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rotulo", "esperado"),
    [
        ("HONDA", "Honda"),
        ("HARLEY-DAVIDSON", "Harley-Davidson"),
        ("BMW", "BMW"),
        ("Toyota", "Toyota"),
        ("GM - Chevrolet", "Chevrolet"),
        ("VW - VolksWagen", "Volkswagen"),
        ("MERCEDES-BENZ", "Mercedes-Benz"),
    ],
)
def test_nome_da_marca(rotulo, esperado):
    """Marcas em caixa alta ficam legíveis; prefixo de sigla sai; a mesma marca vira um nome só."""
    assert nome_da_marca(rotulo) == esperado


@pytest.mark.parametrize(
    ("rotulo", "esperado"),
    [
        ("Hilux CD SRV 4x4 2.8 TDI Diesel Aut.", ("Hilux", "CD SRV 4x4 2.8 TDI Diesel Aut.")),
        ("Grand Siena ATTRACTIVE 1.4 Flex", ("Grand Siena", "ATTRACTIVE 1.4 Flex")),
        ("Range Rover Evoque 2.0", ("Range Rover", "Evoque 2.0")),
        ("Uno", ("Uno", "Uno")),
    ],
)
def test_separar_modelo_e_versao(rotulo, esperado):
    """A FIPE junta modelo e versão: o modelo é a 1ª palavra (ou as 2 primeiras, quando preciso)."""
    assert separar_modelo_e_versao(rotulo) == esperado


@pytest.mark.parametrize(
    ("marca", "modelo", "tipo"),
    [
        ("Toyota", "Hilux", "caminhonete"),
        ("Fiat", "Strada", "caminhonete"),
        ("RAM", "2500", "caminhonete"),
        ("Toyota", "Corolla", "carro"),
    ],
)
def test_picapes_viram_caminhonete(marca, modelo, tipo):
    """A FIPE lista picape como carro; o catálogo separa."""
    assert tipo_do_carro(marca, modelo) == tipo


# --- Carga -----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_carga_idempotente(tmp_path):
    """Rodar duas vezes não duplica; a marca serve a vários tipos (Toyota carro, caminhonete e moto)."""
    arquivo = gravar_csv(tmp_path / "fipe.csv", LINHAS)

    primeira = carregar_catalogo(arquivo)
    segunda = carregar_catalogo(arquivo)

    assert (primeira.marcas, primeira.modelos, primeira.versoes, primeira.versoes_novas) == (2, 4, 4, 4)
    assert segunda.versoes_novas == 0 and Versao.objects.count() == 4
    assert set(Modelo.objects.filter(marca__nome="Toyota").values_list("tipo", flat=True)) == {
        "carro",
        "caminhonete",
        "moto",
    }


@pytest.mark.django_db
def test_carga_nao_reativa_o_que_o_admin_escondeu(tmp_path):
    """ "ativo" é decisão do admin: a recarga não desfaz."""
    arquivo = gravar_csv(tmp_path / "fipe.csv", LINHAS)
    carregar_catalogo(arquivo)
    Versao.objects.filter(nome="160 FAN Flex").update(ativo=False)

    carregar_catalogo(arquivo)

    assert not Versao.objects.get(nome="160 FAN Flex").ativo


@pytest.mark.django_db
def test_linha_errada_cancela_tudo(tmp_path):
    """Uma linha com tipo desconhecido: nada é gravado e o erro diz a linha."""
    arquivo = gravar_csv(tmp_path / "fipe.csv", [*LINHAS, {**LINHAS[0], "tipo": "trator"}])

    with pytest.raises(ValueError, match="linha 6"):
        carregar_catalogo(arquivo)
    assert not Marca.objects.exists()


@pytest.mark.django_db
def test_carga_so_de_algumas_marcas(tmp_path):
    """A demonstração carrega só as marcas que usa."""
    arquivo = gravar_csv(tmp_path / "fipe.csv", LINHAS)

    carregar_catalogo(arquivo, somente_marcas={"Honda"})

    assert list(Marca.objects.values_list("nome", flat=True)) == ["Honda"]


def test_arquivo_do_repositorio_e_valido():
    """O fipe.csv do repositório tem as colunas, os 4 tipos e as versões da demonstração."""
    with ARQUIVO_FIPE.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))

    assert len(linhas) > 5000
    assert {linha["tipo"] for linha in linhas} == {"carro", "caminhonete", "moto", "caminhao"}
    assert {
        "tipo": "caminhonete",
        "marca": "Toyota",
        "modelo": "Hilux",
        "versao": "CD SRV 4x4 2.8 TDI Diesel Aut.",
    }.items() <= next(
        linha for linha in linhas if linha["versao"] == "CD SRV 4x4 2.8 TDI Diesel Aut."
    ).items()
    assert not any(" - " in linha["marca"] for linha in linhas)  # "GM - Chevrolet" normalizado


@pytest.mark.django_db
def test_comando_carregar_catalogo(tmp_path, capsys):
    """Comando mostra o resumo; arquivo inválido vira erro de comando sem gravar nada."""
    call_command("carregar_catalogo", arquivo=gravar_csv(tmp_path / "fipe.csv", LINHAS))
    assert "Versões: 4 (4 novas)" in capsys.readouterr().out

    ruim = tmp_path / "ruim.csv"
    ruim.write_text("tipo,marca\nmoto,Honda\n", encoding="utf-8")
    with pytest.raises(CommandError, match="faltam as colunas"):
        call_command("carregar_catalogo", arquivo=ruim)


def test_comando_atualizar_gera_o_csv_sem_internet(tmp_path, monkeypatch):
    """O comando grava o CSV ordenado e o arquivo de referência (FIPE simulada, sem rede)."""
    monkeypatch.setattr(fipe, "tabela_mais_recente", lambda: (338, "outubro/2026"))
    monkeypatch.setattr(fipe, "linhas_do_catalogo", lambda referencia, pausa, avisar: iter(reversed(LINHAS)))
    saida = tmp_path / "fipe.csv"

    call_command("atualizar_catalogo_fipe", saida=saida)

    linhas = list(csv.DictReader(saida.open(encoding="utf-8")))
    assert [linha["modelo"] for linha in linhas] == ["Hilux", "Corolla", "CG", "Teste"]  # ordenado por tipo
    assert "outubro/2026" in (tmp_path / "fipe_referencia.txt").read_text(encoding="utf-8")


def test_comando_atualizar_sem_internet_nao_mexe_no_arquivo(tmp_path, monkeypatch):
    """Falha de rede: erro claro e o CSV antigo continua lá."""

    def falhar():
        raise OSError("sem rede")

    monkeypatch.setattr(fipe, "tabela_mais_recente", falhar)
    saida = tmp_path / "fipe.csv"
    saida.write_text("antigo", encoding="utf-8")

    with pytest.raises(CommandError, match="não foi alterado"):
        call_command("atualizar_catalogo_fipe", saida=saida)
    assert saida.read_text(encoding="utf-8") == "antigo"


# --- Opções dos selects ---------------------------------------------------------------------


def test_opcoes_encadeadas(catalogo_teste):
    """Marca só com modelo do tipo; modelos da marca no tipo; versões ativas do modelo."""
    toyota, honda = catalogo_teste["toyota"], catalogo_teste["honda"]

    assert list(marcas_do_tipo("moto")) == [honda]
    assert list(modelos_da_marca(toyota.pk, "caminhonete")) == [catalogo_teste["hilux"]]
    assert list(modelos_da_marca(toyota.pk, "moto")) == []
    catalogo_teste["hilux_sr"].ativo = False
    catalogo_teste["hilux_sr"].save()
    assert list(versoes_do_modelo(catalogo_teste["hilux"].pk)) == [catalogo_teste["hilux_srv"]]
    assert list(marcas_do_tipo("trator")) == [] and list(versoes_do_modelo("abc")) == []


# --- Admin ----------------------------------------------------------------------------------


def test_admin_nao_cria_nem_apaga_e_esconde_versao(client, entrar_no_admin, catalogo_teste):
    """Sem criar nem apagar pelo admin; "ativo" editável na lista."""
    daniel = Usuario.objects.create_superuser(email="daniel@exemplo.com", password=SENHA, nome="Daniel")
    entrar_no_admin(daniel)
    versao = catalogo_teste["cg_fan"]

    assert client.get(reverse("admin:catalogo_versao_add")).status_code == 403
    assert client.get(reverse("admin:catalogo_versao_delete", args=[versao.pk])).status_code == 403
    assert client.get(reverse("admin:catalogo_versao_changelist")).status_code == 200
