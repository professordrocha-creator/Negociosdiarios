"""Regras do app catalogo: interpretar os nomes da FIPE, carregar o CSV e listar as opções do formulário.

A FIPE não separa modelo e versão: o "modelo" dela é "Hilux CD SRV 4x4 2.8 Diesel Aut.". Aqui o
modelo é a primeira palavra ("Hilux"), ou as duas primeiras quando a primeira sozinha não identifica
o carro ("Grand Siena", "Range Rover", "Classe C"); o resto é a versão. A FIPE também junta picapes
e carros: as picapes conhecidas viram o tipo "caminhonete".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.db.models import QuerySet
from django.utils.text import slugify

from catalogo.models import Marca, Modelo, TipoVeiculo, Versao

DIR_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO_FIPE = DIR_DADOS / "fipe.csv"
COLUNAS = ["tipo", "marca", "modelo", "versao", "codigo_fipe"]

# Primeiras palavras que precisam da segunda para identificar o modelo.
PREFIXOS_DE_DUAS_PALAVRAS = {
    "grand",
    "range",
    "classe",
    "série",
    "serie",
    "new",
    "nova",
    "novo",
    "space",
    "land",
    "santa",
    "c4",
    "town",
    "e-tron",
    "model",
}

# Picapes vendidas no Brasil (a FIPE as lista como "carros").
PICAPES = {
    "amarok",
    "c-10",
    "c10",
    "courier",
    "d-20",
    "d20",
    "dakota",
    "f-1000",
    "f-150",
    "f-250",
    "f-4000",
    "f1000",
    "f150",
    "f250",
    "frontier",
    "gladiator",
    "hilux",
    "hoggar",
    "l200",
    "l-200",
    "maverick",
    "montana",
    "oroch",
    "pampa",
    "rampage",
    "ranger",
    "s10",
    "s-10",
    "saveiro",
    "silverado",
    "strada",
    "tacoma",
    "titano",
    "toro",
    "triton",
    "tundra",
    "1500",
    "2500",
    "3500",
}
MARCAS_SO_DE_PICAPE = {"ram"}

# Grafias da FIPE trocadas pelo nome comercial.
APELIDOS_DE_MARCA = {"volkswagen": "Volkswagen"}

# Siglas que ficam em maiúsculas ao normalizar marcas que a FIPE escreve TODA EM CAIXA ALTA.
SIGLAS = {
    "BMW",
    "BYD",
    "GWM",
    "JAC",
    "KTM",
    "MV",
    "VW",
    "MAN",
    "DAF",
    "JCB",
    "CAOA",
    "GAC",
    "RAM",
    "MINI",
    "TVS",
}


def nome_da_marca(rotulo: str) -> str:
    """Marca legível: "HONDA" → "Honda", "HARLEY-DAVIDSON" → "Harley-Davidson", "GM - Chevrolet" →
    "Chevrolet", "VW - VolksWagen" → "Volkswagen"; siglas ficam em caixa alta.

    Assim a mesma marca de carro, moto e caminhão vira um registro só (mesmo slug).
    """
    rotulo = " ".join(rotulo.split())
    if " - " in rotulo:  # a FIPE prefixa a sigla em algumas marcas de carro
        rotulo = rotulo.split(" - ", 1)[1]
    rotulo = APELIDOS_DE_MARCA.get(rotulo.lower(), rotulo)
    if rotulo != rotulo.upper():
        return rotulo  # a FIPE já escreveu bonito (carros)
    palavras = []
    for palavra in rotulo.split(" "):
        partes = [p if p in SIGLAS or len(p) <= 2 else p.capitalize() for p in palavra.split("-")]
        palavras.append("-".join(partes))
    return " ".join(palavras)


def separar_modelo_e_versao(rotulo: str) -> tuple[str, str]:
    """ "Hilux CD SRV 4x4 2.8 Diesel Aut." → ("Hilux", "CD SRV 4x4 2.8 Diesel Aut.")."""
    palavras = rotulo.split()
    if not palavras:
        raise ValueError("Nome de modelo vazio.")
    tamanho = 2 if palavras[0].lower() in PREFIXOS_DE_DUAS_PALAVRAS and len(palavras) > 1 else 1
    modelo = " ".join(palavras[:tamanho])
    versao = " ".join(palavras[tamanho:]) or modelo
    return modelo, versao


def tipo_do_carro(marca: str, modelo: str) -> str:
    """Carro da FIPE que é picape vira "caminhonete"."""
    if marca.lower() in MARCAS_SO_DE_PICAPE or modelo.lower() in PICAPES:
        return TipoVeiculo.CAMINHONETE
    return TipoVeiculo.CARRO


@dataclass(frozen=True)
class ResultadoCatalogo:
    """Resumo da carga."""

    marcas: int
    modelos: int
    versoes: int
    versoes_novas: int


def ler_arquivo(caminho: Path = ARQUIVO_FIPE) -> list[dict[str, str]]:
    """Lê o CSV do catálogo e confere as colunas."""
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = set(COLUNAS) - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"{caminho.name}: faltam as colunas {sorted(faltando)}.")
        return list(leitor)


def _validar(linhas: list[dict[str, str]], nome_arquivo: str) -> list[tuple[str, str, str, str, str]]:
    """Confere cada linha e devolve (tipo, marca, modelo, versão, código) já limpos."""
    limpas = []
    for numero, linha in enumerate(linhas, start=2):  # linha 1 é o cabeçalho
        try:
            tipo = linha["tipo"].strip()
            if tipo not in TipoVeiculo.values:
                raise ValueError(f"tipo '{tipo}' desconhecido")
            marca, modelo = limpar_rotulo(linha["marca"]), limpar_rotulo(linha["modelo"])
            versao = limpar_rotulo(linha["versao"])
            if not (marca and modelo and versao):
                raise ValueError("marca, modelo e versão são obrigatórios")
        except (KeyError, ValueError, AttributeError) as erro:
            raise ValueError(f"{nome_arquivo}, linha {numero}: {erro}") from erro
        limpas.append((tipo, marca, modelo, versao, (linha.get("codigo_fipe") or "").strip()))
    return limpas


@transaction.atomic
def carregar_catalogo(
    caminho: Path = ARQUIVO_FIPE, somente_marcas: set[str] | None = None
) -> ResultadoCatalogo:
    """Carrega (ou atualiza) marcas, modelos e versões do CSV, em lote. Idempotente; nunca apaga nem reativa.

    `somente_marcas` (nomes) limita a carga, para a demonstração e os testes não precisarem do
    catálogo inteiro. Tudo numa transação: uma linha errada cancela a carga (com o número da linha).
    O campo `ativo` só vale na criação (o que o admin escondeu continua escondido).
    """
    linhas = _validar(ler_arquivo(caminho), caminho.name)
    if somente_marcas is not None:
        filtro = {slugify(m) for m in somente_marcas}
        linhas = [linha for linha in linhas if slugify(linha[1]) in filtro]
    versoes_antes = Versao.objects.count()

    nomes_marca = {slugify(marca): marca for _, marca, _, _, _ in linhas}
    Marca.objects.bulk_create(
        [Marca(slug=slug, nome=nome) for slug, nome in nomes_marca.items()],
        update_conflicts=True,
        unique_fields=["slug"],
        update_fields=["nome"],
    )
    marca_id = dict(Marca.objects.filter(slug__in=nomes_marca).values_list("slug", "pk"))

    chaves_modelo = {
        (marca_id[slugify(marca)], tipo, slugify(modelo)): modelo for tipo, marca, modelo, _, _ in linhas
    }
    Modelo.objects.bulk_create(
        [
            Modelo(marca_id=m, tipo=tipo, slug=slug, nome=nome)
            for (m, tipo, slug), nome in chaves_modelo.items()
        ],
        update_conflicts=True,
        unique_fields=["marca", "tipo", "slug"],
        update_fields=["nome"],
        batch_size=2000,
    )
    modelo_id = {
        (m, tipo, slug): pk
        for m, tipo, slug, pk in Modelo.objects.filter(marca_id__in=marca_id.values()).values_list(
            "marca_id", "tipo", "slug", "pk"
        )
    }

    versoes = {}
    for tipo, marca, modelo, versao, codigo in linhas:
        chave = modelo_id[(marca_id[slugify(marca)], tipo, slugify(modelo))]
        versoes[(chave, versao)] = codigo  # repetida no arquivo: fica a última
    Versao.objects.bulk_create(
        [Versao(modelo_id=m, nome=nome, codigo_fipe=codigo) for (m, nome), codigo in versoes.items()],
        update_conflicts=True,
        unique_fields=["modelo", "nome"],
        update_fields=["codigo_fipe"],
        batch_size=2000,
    )
    return ResultadoCatalogo(
        marcas=Marca.objects.count(),
        modelos=Modelo.objects.count(),
        versoes=Versao.objects.count(),
        versoes_novas=Versao.objects.count() - versoes_antes,
    )


def catalogo_vazio() -> bool:
    """Ainda não rodou o `carregar_catalogo`?"""
    return not Versao.objects.exists()


# --- Opções do formulário (selects encadeados) ---------------------------------------------


def marcas_do_tipo(tipo: str) -> QuerySet[Marca]:
    """Marcas ativas que têm modelo ativo do tipo."""
    if tipo not in TipoVeiculo.values:
        return Marca.objects.none()
    return (
        Marca.objects.filter(ativo=True, modelos__tipo=tipo, modelos__ativo=True).distinct().order_by("nome")
    )


def modelos_da_marca(marca_id: int | str | None, tipo: str) -> QuerySet[Modelo]:
    """Modelos ativos da marca no tipo."""
    if not str(marca_id or "").isdigit() or tipo not in TipoVeiculo.values:
        return Modelo.objects.none()
    return Modelo.objects.filter(marca_id=int(marca_id), tipo=tipo, ativo=True).order_by("nome")


def versoes_do_modelo(modelo_id: int | str | None) -> QuerySet[Versao]:
    """Versões ativas do modelo."""
    if not str(modelo_id or "").isdigit():
        return Versao.objects.none()
    return Versao.objects.filter(modelo_id=int(modelo_id), ativo=True).order_by("nome")


def limpar_rotulo(texto: str) -> str:
    """Tira espaços duplos e pontas (a FIPE tem "2.8  Diesel")."""
    return re.sub(r"\s+", " ", texto).strip()
