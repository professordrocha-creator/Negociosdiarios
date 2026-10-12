"""Regras do app catalogo: interpretar os nomes da FIPE, carregar o CSV e listar as opções do formulário.

A FIPE não separa modelo e versão: o "modelo" dela é "Hilux CD SRV 4x4 2.8 Diesel Aut.". Aqui o
modelo é a primeira palavra ("Hilux"), ou as duas primeiras quando a primeira sozinha não identifica
o carro ("Grand Siena", "Land Cruiser"); o resto é a versão. Abreviações e códigos de motor da FIPE
("Range R.EVOQUE", "C-180") passam por uma tabela de exceções por marca; nas motos, sigla + cilindrada
formam o modelo ("CG 160"). A FIPE também junta picapes
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

# Primeiras palavras que precisam da segunda para identificar o modelo ("Grand Siena", "Land Cruiser").
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
    "town",
    "model",
}

# Exceções por marca (slug): a FIPE abrevia ou usa o código do motor no lugar do nome do modelo.
# Cada regra: (expressão no começo do nome da FIPE, modelo, texto que vai na frente da versão).
# No modelo e no prefixo, \1, \2 viram os grupos da expressão. Testadas em catalogo/tests.
CLASSES_MERCEDES = "CL|CLA|CLC|CLK|CLS|GL|GLA|GLB|GLC|GLE|GLK|GLS|ML|SL|SLC|SLK|SLS"
EXCECOES_DE_MODELO: dict[str, list[tuple[str, str, str]]] = {
    "land-rover": [
        (r"range[\s.]*r(?:over)?\.?\s*evo\w*\.?", "Range Rover Evoque", ""),
        (r"range[\s.]*r(?:over)?\.?\s*velar(?![a-z])", "Range Rover Velar", ""),
        (r"range[\s.]*r(?:over)?\.?\s*sp(?:ort)?\.?(?![a-z])", "Range Rover Sport", ""),
        (r"(?:new range/range(?:\s+rover)?|range[\s.]*r(?:over)?\.?)(?![a-z])", "Range Rover", ""),
        (r"def(?:e)?\.", "Defender", ""),
        (r"disc(?:ov\.|\.|overy)\s*sp(?:ort)?\.?(?![a-z])", "Discovery Sport", ""),
        (r"disc(?:ov)?\.", "Discovery", ""),
        (r"discovery(\d)", "Discovery", "\\1 "),
        (r"freelander(\d)", "Freelander", "\\1 "),
    ],
    "mercedes-benz": [
        (r"(A|B|C|E|G|S)-(\d+\w*)", "Classe \\1", "\\1 \\2 "),
        (rf"({CLASSES_MERCEDES})-(\d+\w*)", "\\1", "\\1 \\2 "),
        (r"sprin\.", "Sprinter", ""),
    ],
    "citroen": [
        (r"c4\s+(cactus|lounge|picasso|pallas|pal\.)", "C4 \\1", ""),
        (r"c4(?![a-z0-9])", "C4", ""),
    ],
    "audi": [
        (r"e-tron\s+(?:sportback|sportb\.)", "e-tron Sportback", ""),
        (r"e-tron\s+gt(?![a-z])", "e-tron GT", ""),
        (r"e-tron(?![a-z])", "e-tron", ""),
    ],
    "toyota": [(r"band\.", "Bandeirante", "")],
    "hyundai": [
        (r"grand santa(?:\s+fe)?(?![a-z])", "Grand Santa Fe", ""),
        (r"santa fe\s*/?", "Santa Fe", ""),
    ],
    "volvo": [(r"xc\s*(\d{2})(?![0-9])", "XC\\1", "")],
}
# Nomes que a FIPE escreve de outro jeito (depois de separar), para o modelo ficar com a grafia comercial.
GRAFIA_DO_MODELO = {
    "c4 cactus": "C4 Cactus",
    "c4 lounge": "C4 Lounge",
    "c4 picasso": "C4 Picasso",
    "c4 pallas": "C4 Pallas",
    "c4 pal.": "C4 Pallas",
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


def _excecao(rotulo: str, marca: str) -> tuple[str, str] | None:
    """Aplica a primeira exceção da marca que casar com o começo do nome (ou None)."""
    for padrao, modelo, prefixo in EXCECOES_DE_MODELO.get(slugify(marca), []):
        achado = re.match(padrao, rotulo, flags=re.IGNORECASE)
        if achado:
            modelo = achado.expand(modelo)
            modelo = GRAFIA_DO_MODELO.get(modelo.lower(), modelo)
            resto = rotulo[achado.end() :].lstrip(" /.")
            versao = (achado.expand(prefixo) + resto).strip()
            return modelo, versao or modelo
    return None


def separar_modelo_e_versao(rotulo: str, marca: str = "", moto: bool = False) -> tuple[str, str]:
    """Modelo e versão a partir do nome da FIPE.

    - "Hilux CD SRV 4x4 2.8 Diesel Aut." → ("Hilux", "CD SRV 4x4 2.8 Diesel Aut.");
    - nomes compostos: "Grand Siena 1.4" → ("Grand Siena", "1.4"),
      "Land Cruiser Prado" → ("Land Cruiser", "Prado");
    - exceções da marca (`EXCECOES_DE_MODELO`): "Range R.EVOQUE Dyn." → ("Range Rover Evoque", "Dyn."),
      Mercedes "C-180 1.6 Turbo" → ("Classe C", "C 180 1.6 Turbo"), Volvo "XC 60 T-5" → ("XC60", "T-5");
    - moto (`moto=True`): sigla + cilindrada formam o modelo: "CG 160 FAN Flex" → ("CG 160", "FAN Flex").
    """
    rotulo = " ".join(rotulo.split())
    if not rotulo:
        raise ValueError("Nome de modelo vazio.")
    excecao = _excecao(rotulo, marca)
    if excecao:
        return excecao
    palavras = rotulo.split()
    if (
        moto
        and len(palavras) > 1
        and re.fullmatch(r"[A-Za-z]{1,5}", palavras[0])
        and re.fullmatch(r"\d{2,4}[A-Za-z]*", palavras[1])
    ):
        tamanho = 2
    elif palavras[0].lower() in PREFIXOS_DE_DUAS_PALAVRAS and len(palavras) > 1:
        tamanho = 2
    else:
        tamanho = 1
    modelo = " ".join(palavras[:tamanho])
    resto = " ".join(palavras[tamanho:])
    if "/" in modelo:  # "Strada/ Adventure", "Space Wagon/GLS": a barra é da versão
        modelo, sobra = modelo.split("/", 1)
        resto = f"{sobra} {resto}".strip(" /")
    return modelo.strip(), resto or modelo.strip()


def reprocessar_linha(linha: dict[str, str]) -> dict[str, str]:
    """Refaz modelo/versão (e carro × caminhonete) de uma linha do CSV com as regras atuais.

    O nome original da FIPE é modelo + versão (a versão igual ao modelo indica nome de uma palavra só).
    """
    rotulo = linha["modelo"] if linha["versao"] == linha["modelo"] else f"{linha['modelo']} {linha['versao']}"
    moto = linha["tipo"] == TipoVeiculo.MOTO
    modelo, versao = separar_modelo_e_versao(rotulo, marca=linha["marca"], moto=moto)
    tipo = linha["tipo"]
    if tipo in (TipoVeiculo.CARRO, TipoVeiculo.CAMINHONETE):
        tipo = tipo_do_carro(linha["marca"], modelo)
    return {**linha, "tipo": str(tipo), "modelo": modelo, "versao": versao}


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
    versoes_movidas: int = 0
    escondidas: int = 0


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

    A versão já existente é reconhecida pelo código FIPE e atualizada no lugar (mudou de modelo quando
    as regras de nome mudaram, por exemplo "C-180" → "Classe C"): os anúncios e o "ativo" do admin ficam.

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

    alvo: dict[tuple[int, str], tuple[str, int, str]] = {}  # (modelo, versão) → (código, marca, grupo)
    for tipo, marca, modelo, versao, codigo in linhas:
        m = marca_id[slugify(marca)]
        alvo[(modelo_id[(m, tipo, slugify(modelo))], versao)] = (codigo, m, _grupo(tipo))
    movidas = _gravar_versoes(alvo, marca_id.values())
    # Carga completa: o catálogo inteiro é comparado (marca que sumiu do arquivo também conta).
    escondidas = _esconder_o_que_saiu(alvo, None if somente_marcas is None else marca_id.values())
    return ResultadoCatalogo(
        marcas=Marca.objects.count(),
        modelos=Modelo.objects.count(),
        versoes=Versao.objects.count(),
        versoes_novas=Versao.objects.count() - versoes_antes,
        versoes_movidas=movidas,
        escondidas=escondidas,
    )


def _grupo(tipo: str) -> str:
    """Código FIPE é único por tabela (carros, motos, caminhões); carro e caminhonete: mesma tabela."""
    return "carro" if tipo in (TipoVeiculo.CARRO, TipoVeiculo.CAMINHONETE) else tipo


def _gravar_versoes(alvo: dict[tuple[int, str], tuple[str, int, str]], marcas) -> int:
    """Versão que já existe (mesma marca, tabela e código FIPE) é atualizada NO LUGAR: muda de modelo ou de
    nome sem virar outro registro, então os anúncios continuam ligados a ela e o "ativo" do admin fica.
    As que não existem são criadas. Devolve quantas mudaram de modelo ou de nome."""
    existentes = {
        (marca, _grupo(tipo), codigo): pk
        for pk, marca, tipo, codigo in Versao.objects.filter(modelo__marca_id__in=list(marcas))
        .exclude(codigo_fipe="")
        .values_list("pk", "modelo__marca_id", "modelo__tipo", "codigo_fipe")
    }
    atuais = {
        pk: (modelo, nome)
        for pk, modelo, nome in Versao.objects.filter(pk__in=existentes.values()).values_list(
            "pk", "modelo_id", "nome"
        )
    }
    mudar: dict[int, tuple[int, str]] = {}
    criar = []
    for (modelo, nome), (codigo, marca, grupo) in alvo.items():
        pk = existentes.get((marca, grupo, codigo)) if codigo else None
        if pk is None:
            criar.append(Versao(modelo_id=modelo, nome=nome, codigo_fipe=codigo))
        elif atuais[pk] != (modelo, nome):
            mudar[pk] = (modelo, nome)
    if mudar:
        # Duas fases: um nome provisório único evita colisão na troca (A vira B enquanto B vira C).
        provisorias = [Versao(pk=pk, nome=f"~{pk}") for pk in mudar]
        Versao.objects.bulk_update(provisorias, ["nome"], batch_size=2000)
        finais = [Versao(pk=pk, modelo_id=modelo, nome=nome) for pk, (modelo, nome) in mudar.items()]
        Versao.objects.bulk_update(finais, ["modelo", "nome"], batch_size=2000)
    Versao.objects.bulk_create(
        criar,
        update_conflicts=True,
        unique_fields=["modelo", "nome"],
        update_fields=["codigo_fipe"],
        batch_size=2000,
    )
    return len(mudar)


def _esconder_o_que_saiu(alvo: dict[tuple[int, str], tuple[str, int, str]], marcas=None) -> int:
    """Versões que saíram do arquivo ficam escondidas (ativo=False); nada é apagado (anúncios antigos
    continuam apontando para elas). Modelo sem versão ativa some dos selects sozinho (ver
    `modelos_da_marca`), sem mexer no "ativo" dele. Devolve quantas versões foram escondidas."""
    no_arquivo = set(alvo)
    versoes = Versao.objects.filter(ativo=True)
    if marcas is not None:  # carga parcial (só algumas marcas): só elas são comparadas
        versoes = versoes.filter(modelo__marca_id__in=list(marcas))
    sairam = [
        pk
        for pk, modelo, nome in versoes.values_list("pk", "modelo_id", "nome")
        if (modelo, nome) not in no_arquivo
    ]
    return Versao.objects.filter(pk__in=sairam).update(ativo=False)


def catalogo_vazio() -> bool:
    """Ainda não rodou o `carregar_catalogo`?"""
    return not Versao.objects.exists()


# --- Opções do formulário (selects encadeados) ---------------------------------------------


def marcas_do_tipo(tipo: str) -> QuerySet[Marca]:
    """Marcas ativas que têm modelo ativo do tipo com pelo menos uma versão ativa."""
    if tipo not in TipoVeiculo.values:
        return Marca.objects.none()
    return (
        Marca.objects.filter(
            ativo=True, modelos__tipo=tipo, modelos__ativo=True, modelos__versoes__ativo=True
        )
        .distinct()
        .order_by("nome")
    )


def modelos_da_marca(marca_id: int | str | None, tipo: str) -> QuerySet[Modelo]:
    """Modelos ativos da marca no tipo que têm versão ativa (modelo esvaziado pela recarga não aparece)."""
    if not str(marca_id or "").isdigit() or tipo not in TipoVeiculo.values:
        return Modelo.objects.none()
    return (
        Modelo.objects.filter(marca_id=int(marca_id), tipo=tipo, ativo=True, versoes__ativo=True)
        .distinct()
        .order_by("nome")
    )


def versoes_do_modelo(modelo_id: int | str | None) -> QuerySet[Versao]:
    """Versões ativas do modelo."""
    if not str(modelo_id or "").isdigit():
        return Versao.objects.none()
    return Versao.objects.filter(modelo_id=int(modelo_id), ativo=True).order_by("nome")


def limpar_rotulo(texto: str) -> str:
    """Tira espaços duplos e pontas (a FIPE tem "2.8  Diesel")."""
    return re.sub(r"\s+", " ", texto).strip()
