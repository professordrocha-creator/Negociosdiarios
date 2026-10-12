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


# Nome da FIPE (marca, tipo) → (modelo, versão). Os nomes vêm do fipe.csv de outubro/2026.
NOMES = [
    ("Toyota", "carro", "Hilux CD SRV 4x4 2.8 TDI Diesel Aut.", ("Hilux", "CD SRV 4x4 2.8 TDI Diesel Aut.")),
    ("Fiat", "carro", "Grand Siena ATTRACTIVE 1.4 Flex", ("Grand Siena", "ATTRACTIVE 1.4 Flex")),
    ("Jeep", "carro", "Grand Cherokee Limited 3.6", ("Grand Cherokee", "Limited 3.6")),
    ("Toyota", "carro", "Land Cruiser Prado VX 3.0", ("Land Cruiser", "Prado VX 3.0")),
    ("Hyundai", "carro", "Santa Fe GLS 3.5 V6 4x4 Aut.", ("Santa Fe", "GLS 3.5 V6 4x4 Aut.")),
    ("Hyundai", "carro", "Santa Fe/GLS 2.7 V6 4x4 Aut.", ("Santa Fe", "GLS 2.7 V6 4x4 Aut.")),
    ("Hyundai", "carro", "Grand Santa Fe 3.3 V6 4x4 Aut.", ("Grand Santa Fe", "3.3 V6 4x4 Aut.")),
    (
        "Land Rover",
        "carro",
        "Range Rover Autobio 4.4 V8 TB 530cv Aut.",
        ("Range Rover", "Autobio 4.4 V8 TB 530cv Aut."),
    ),
    (
        "Land Rover",
        "carro",
        "Range R. Autobio. 3.0 I6 TB Die. (Híb.)",
        ("Range Rover", "Autobio. 3.0 I6 TB Die. (Híb.)"),
    ),
    ("Land Rover", "carro", "Range.R. Vogue 4.4", ("Range Rover", "Vogue 4.4")),
    ("Land Rover", "carro", "New Range/Range Rover Vogue 3.9 V8", ("Range Rover", "Vogue 3.9 V8")),
    (
        "Land Rover",
        "carro",
        "Range R.EVOQUE Autob. 2.0 P250 Flex Aut",
        ("Range Rover Evoque", "Autob. 2.0 P250 Flex Aut"),
    ),
    (
        "Land Rover",
        "carro",
        "Range R.EVOQ. HSE Dyn. Convers 2.0 Aut.",
        ("Range Rover Evoque", "HSE Dyn. Convers 2.0 Aut."),
    ),
    (
        "Land Rover",
        "carro",
        "Range R.EVO DYNAMIC. BLACK 2.0 Aut. 5p",
        ("Range Rover Evoque", "DYNAMIC. BLACK 2.0 Aut. 5p"),
    ),
    (
        "Land Rover",
        "carro",
        "Range R.Sport First.Ed.3.0 I6 Die.(Hib.)",
        ("Range Rover Sport", "First.Ed.3.0 I6 Die.(Hib.)"),
    ),
    (
        "Land Rover",
        "carro",
        "Range R.Sp.HSE Dyn.Bl. 3.0 I6 Die.(Híb.)",
        ("Range Rover Sport", "HSE Dyn.Bl. 3.0 I6 Die.(Híb.)"),
    ),
    (
        "Land Rover",
        "carro",
        "Range.R. SP.HSE Dyn.BL. 2.0 Si4(Hibrido)",
        ("Range Rover Sport", "HSE Dyn.BL. 2.0 Si4(Hibrido)"),
    ),
    (
        "Land Rover",
        "carro",
        "Range R. VELAR HSE 2.0 4x4 TB 250cv Aut.",
        ("Range Rover Velar", "HSE 2.0 4x4 TB 250cv Aut."),
    ),
    ("Land Rover", "carro", "Defe. 110 SE 2.0 P300", ("Defender", "110 SE 2.0 P300")),
    (
        "Land Rover",
        "carro",
        "Disc. Sp. S 2.0 4x4 Dies. Aut. (Híb.)",
        ("Discovery Sport", "S 2.0 4x4 Dies. Aut. (Híb.)"),
    ),
    (
        "Land Rover",
        "carro",
        "Discovery Sport HSE 2.0 4x4 Diesel Aut.",
        ("Discovery Sport", "HSE 2.0 4x4 Diesel Aut."),
    ),
    ("Land Rover", "carro", "Discov. SE 3.0 V6", ("Discovery", "SE 3.0 V6")),
    ("Land Rover", "carro", "Discovery3 TDV6 S 2.7 4x4", ("Discovery", "3 TDV6 S 2.7 4x4")),
    ("Land Rover", "carro", "Freelander2 HSE 2.0", ("Freelander", "2 HSE 2.0")),
    (
        "Mercedes-Benz",
        "carro",
        "C-180 1.6 Turbo 16V/Flex 16V Aut.",
        ("Classe C", "C 180 1.6 Turbo 16V/Flex 16V Aut."),
    ),
    ("Mercedes-Benz", "carro", "A-200 Style 1.3 TB Aut.", ("Classe A", "A 200 Style 1.3 TB Aut.")),
    ("Mercedes-Benz", "carro", "E-350 Avantgarde 3.5 V6", ("Classe E", "E 350 Avantgarde 3.5 V6")),
    ("Mercedes-Benz", "carro", "S-500L 5.0 V8", ("Classe S", "S 500L 5.0 V8")),
    ("Mercedes-Benz", "carro", "Classe A 160 Classic Semi-Aut.", ("Classe A", "160 Classic Semi-Aut.")),
    ("Mercedes-Benz", "carro", "GLA-200 Advance 1.6 TB Aut.", ("GLA", "GLA 200 Advance 1.6 TB Aut.")),
    ("Mercedes-Benz", "carro", "CLA-250 Sport 2.0 TB", ("CLA", "CLA 250 Sport 2.0 TB")),
    ("Mercedes-Benz", "carro", "Sprin. 415 CDI Furgão", ("Sprinter", "415 CDI Furgão")),
    ("Citroën", "carro", "C4 CACTUS Feel 1.6 Flex Aut.", ("C4 Cactus", "Feel 1.6 Flex Aut.")),
    ("Citroën", "carro", "C4 LOUNGE Tendance 1.6 THP", ("C4 Lounge", "Tendance 1.6 THP")),
    ("Citroën", "carro", "C4 GLX 2.0 Flex 16V 5p Aut.", ("C4", "GLX 2.0 Flex 16V 5p Aut.")),
    ("Citroën", "carro", "Grand C4 Picasso 2.0", ("Grand C4", "Picasso 2.0")),
    ("Audi", "carro", "E-TRON Sportb. Performance", ("e-tron Sportback", "Performance")),
    ("Audi", "carro", "E-TRON GT quattro", ("e-tron GT", "quattro")),
    ("Toyota", "carro", "Band.Picape 3.7 Diesel", ("Bandeirante", "Picape 3.7 Diesel")),
    ("Volvo", "carro", "XC 60 T-5 2.0 AWD", ("XC60", "T-5 2.0 AWD")),
    ("Fiat", "carro", "Strada/ Adventure 1.8", ("Strada", "Adventure 1.8")),
    ("Fiat", "carro", "Uno", ("Uno", "Uno")),
    ("Volkswagen", "carro", "Gol 1.0 Flex 12V 5p", ("Gol", "1.0 Flex 12V 5p")),  # 1.0 não vira modelo
    ("Honda", "moto", "CG 160 FAN Flex", ("CG 160", "FAN Flex")),
    ("Honda", "moto", "CB 300F Twister Flex", ("CB 300F", "Twister Flex")),
    ("BMW", "moto", "R 1250 GS Adventure", ("R 1250", "GS Adventure")),
    ("Yamaha", "moto", "FZ25 250 FAZER FLEX", ("FZ25", "250 FAZER FLEX")),  # sigla com número: fica
]


@pytest.mark.parametrize(("marca", "tipo", "rotulo", "esperado"), NOMES)
def test_separar_modelo_e_versao(marca, tipo, rotulo, esperado):
    """Nomes compostos, abreviações e códigos de motor da FIPE viram o modelo comercial."""
    assert separar_modelo_e_versao(rotulo, marca=marca, moto=tipo == "moto") == esperado


@pytest.mark.parametrize(("marca", "tipo", "rotulo", "esperado"), NOMES)
def test_reprocessar_e_idempotente(marca, tipo, rotulo, esperado):
    """Reprocessar o CSV já reprocessado não muda nada (o nome é refeito de modelo + versão)."""
    from catalogo.services import reprocessar_linha

    modelo, versao = esperado
    linha = {
        "tipo": "moto" if tipo == "moto" else "carro",
        "marca": marca,
        "modelo": modelo,
        "versao": versao,
        "codigo_fipe": "1",
    }
    assert (reprocessar_linha(linha)["modelo"], reprocessar_linha(linha)["versao"]) == esperado


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


# --- Recarga com as regras novas (versões reconhecidas pelo código FIPE) ---------------------

ANTIGO = [  # como o fipe.csv era gerado antes das exceções de nome
    {
        "tipo": "carro",
        "marca": "Mercedes-Benz",
        "modelo": "C-180",
        "versao": "1.6 Turbo Aut.",
        "codigo_fipe": "100",
    },
    {
        "tipo": "carro",
        "marca": "Mercedes-Benz",
        "modelo": "C-200",
        "versao": "1.5 TB Aut.",
        "codigo_fipe": "101",
    },
    {
        "tipo": "carro",
        "marca": "Land Rover",
        "modelo": "Range R.EVOQUE",
        "versao": "HSE 2.0",
        "codigo_fipe": "200",
    },
    {"tipo": "moto", "marca": "Honda", "modelo": "CG", "versao": "160 FAN Flex", "codigo_fipe": "300"},
]
NOVO = [  # o mesmo, reprocessado
    {
        "tipo": "carro",
        "marca": "Mercedes-Benz",
        "modelo": "Classe C",
        "versao": "C 180 1.6 Turbo Aut.",
        "codigo_fipe": "100",
    },
    {
        "tipo": "carro",
        "marca": "Mercedes-Benz",
        "modelo": "Classe C",
        "versao": "C 200 1.5 TB Aut.",
        "codigo_fipe": "101",
    },
    {
        "tipo": "carro",
        "marca": "Land Rover",
        "modelo": "Range Rover Evoque",
        "versao": "HSE 2.0",
        "codigo_fipe": "200",
    },
    {"tipo": "moto", "marca": "Honda", "modelo": "CG 160", "versao": "FAN Flex", "codigo_fipe": "300"},
]


@pytest.mark.django_db
def test_reprocessar_o_csv_antigo_da_o_novo():
    """`reprocessar_linha` transforma as linhas antigas nas novas."""
    from catalogo.services import reprocessar_linha

    assert [reprocessar_linha(linha) for linha in ANTIGO] == NOVO


@pytest.mark.django_db
def test_recarga_move_versoes_sem_perder_anuncio_nem_o_escondido(tmp_path, loja, tangara):
    """Recarregar com as regras novas: a versão é o MESMO registro (anúncio continua ligado), muda de
    modelo, e a que o admin escondeu continua escondida. O modelo antigo, vazio, some dos selects."""
    from anuncios import services as anuncios

    carregar_catalogo(gravar_csv(tmp_path / "antigo.csv", ANTIGO))
    c180 = Versao.objects.get(codigo_fipe="100")
    Versao.objects.filter(codigo_fipe="101").update(ativo=False)  # escondida pelo admin
    anuncio = anuncios.criar_anuncio_veiculo(
        loja(),
        {"titulo": "", "descricao": "", "preco": 1, "cidade": tangara},
        {
            "versao": c180,
            "ano_fabricacao": 2020,
            "ano_modelo": 2020,
            "quilometragem": 1,
            "combustivel": "flex",
            "cambio": "automatico",
            "cor": "preto",
            "portas": 4,
            "final_placa": "",
            "opcionais": [],
        },
    )

    resultado = carregar_catalogo(gravar_csv(tmp_path / "novo.csv", NOVO))

    assert resultado.versoes_novas == 0 and resultado.versoes_movidas == 4
    c180.refresh_from_db()
    assert (c180.modelo.nome, c180.nome, c180.ativo) == ("Classe C", "C 180 1.6 Turbo Aut.", True)
    assert anuncio.veiculo.versao_id == c180.pk
    assert not Versao.objects.get(codigo_fipe="101").ativo  # o admin escondeu: continua escondida
    mercedes = Marca.objects.get(slug="mercedes-benz")
    assert [m.nome for m in modelos_da_marca(mercedes.pk, "carro")] == ["Classe C"]  # C-180/C-200 vazios
    honda = Marca.objects.get(slug="honda")
    assert [m.nome for m in modelos_da_marca(honda.pk, "moto")] == ["CG 160"]


@pytest.mark.django_db
def test_versao_que_saiu_do_arquivo_fica_escondida(tmp_path):
    """Sumiu da FIPE: escondida (ativo=False), nunca apagada."""
    carregar_catalogo(gravar_csv(tmp_path / "antigo.csv", NOVO))

    resultado = carregar_catalogo(gravar_csv(tmp_path / "menor.csv", NOVO[:3]))

    assert resultado.escondidas == 1
    assert not Versao.objects.get(codigo_fipe="300").ativo
    assert Versao.objects.count() == 4


def test_csv_do_repositorio_ja_usa_os_nomes_novos():
    """O fipe.csv do repositório foi reprocessado: nada de "C-180", "Range R." ou "XC" sozinho."""
    with ARQUIVO_FIPE.open(encoding="utf-8", newline="") as arquivo:
        modelos = {(linha["marca"], linha["modelo"]) for linha in csv.DictReader(arquivo)}

    assert ("Mercedes-Benz", "Classe C") in modelos and ("Mercedes-Benz", "C-180") not in modelos
    assert ("Land Rover", "Range Rover Evoque") in modelos and ("Land Rover", "Range R.") not in modelos
    assert ("Volvo", "XC60") in modelos and ("Volvo", "XC") not in modelos
    assert ("Honda", "CG 160") in modelos
