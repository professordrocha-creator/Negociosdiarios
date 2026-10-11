"""Regras e verificações do app core."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from django.contrib.gis.geos import Point
from django.db import DatabaseError, connection, transaction
from django.db.models import QuerySet
from django.utils.text import slugify

from core.models import Cidade, Estado

logger = logging.getLogger(__name__)

DIR_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO_ESTADOS = DIR_DADOS / "estados.csv"
ARQUIVO_MUNICIPIOS = DIR_DADOS / "municipios.csv"


def banco_disponivel() -> bool:
    """Testa a conexão com o banco executando um `SELECT 1`.

    Retorna False (sem lançar exceção) se o banco não responder, e registra
    no log só o tipo do erro, sem a mensagem, que pode conter host e usuário.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as erro:
        logger.error("Banco indisponível na verificação de saúde: %s", type(erro).__name__)
        return False
    return True


@dataclass(frozen=True)
class ResultadoCarga:
    """Resumo de uma execução de `carregar_municipios`."""

    estados_novos: int
    estados_total: int
    cidades_novas: int
    cidades_total: int


def _ler_csv(caminho: Path, colunas: set[str]) -> list[dict[str, str]]:
    """Lê um CSV UTF-8 e confere se as colunas obrigatórias existem."""
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = colunas - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"{caminho.name}: faltam as colunas {sorted(faltando)}.")
        return list(leitor)


@transaction.atomic
def carregar_municipios(
    arquivo_estados: Path = ARQUIVO_ESTADOS,
    arquivo_municipios: Path = ARQUIVO_MUNICIPIOS,
    uf_liberada: str = "MT",
) -> ResultadoCarga:
    """Carrega (ou atualiza) estados e cidades a partir dos CSVs de `core/dados/`.

    Idempotente: pode rodar quantas vezes quiser. Registros existentes têm só
    os dados do IBGE atualizados (nome, slug, UF, ponto); `liberado` e
    `liberada` **nunca** são alterados, para não desfazer o que o admin liberou.
    Na primeira carga, só o estado `uf_liberada` nasce liberado e nenhuma
    cidade. Tudo roda numa transação: se uma linha estiver errada, nada é gravado.
    """
    uf_liberada = uf_liberada.upper()

    linhas_estados = _ler_csv(arquivo_estados, {"uf", "nome"})
    ufs_no_arquivo = {linha["uf"].strip().upper() for linha in linhas_estados}
    if uf_liberada not in ufs_no_arquivo:
        raise ValueError(f"UF '{uf_liberada}' não existe em {arquivo_estados.name}.")

    ufs_existentes = set(Estado.objects.values_list("uf", flat=True))
    estados = [
        Estado(
            uf=linha["uf"].strip().upper(),
            nome=linha["nome"].strip(),
            liberado=linha["uf"].strip().upper() == uf_liberada,  # só vale para estado novo
        )
        for linha in linhas_estados
    ]
    Estado.objects.bulk_create(estados, update_conflicts=True, unique_fields=["uf"], update_fields=["nome"])

    linhas_cidades = _ler_csv(arquivo_municipios, {"codigo_ibge", "nome", "uf", "latitude", "longitude"})
    codigos_existentes = set(Cidade.objects.values_list("codigo_ibge", flat=True))
    cidades = []
    for numero, linha in enumerate(linhas_cidades, start=2):  # linha 1 é o cabeçalho
        try:
            uf = linha["uf"].strip().upper()
            if uf not in ufs_no_arquivo:
                raise ValueError(f"UF '{uf}' desconhecida")
            nome = linha["nome"].strip()
            cidades.append(
                Cidade(
                    codigo_ibge=int(linha["codigo_ibge"]),
                    nome=nome,
                    slug=slugify(nome),
                    uf_id=uf,
                    ponto=Point(float(linha["longitude"]), float(linha["latitude"]), srid=4326),
                )
            )
        except (ValueError, TypeError) as erro:
            raise ValueError(f"{arquivo_municipios.name}, linha {numero}: {erro}") from erro

    Cidade.objects.bulk_create(
        cidades,
        update_conflicts=True,
        unique_fields=["codigo_ibge"],
        update_fields=["nome", "slug", "uf", "ponto"],
        batch_size=1000,
    )

    return ResultadoCarga(
        estados_novos=len(ufs_no_arquivo - ufs_existentes),
        estados_total=Estado.objects.count(),
        cidades_novas=len({c.codigo_ibge for c in cidades} - codigos_existentes),
        cidades_total=Cidade.objects.count(),
    )


def liberar_cidades(cidades: QuerySet[Cidade]) -> int:
    """Marca as cidades como liberadas e devolve quantas mudaram de situação.

    Cidades já liberadas são ignoradas na contagem. A cidade só aparece no site
    se o estado dela também estiver liberado (docs/ARQUITETURA.md §9).
    """
    # Quando existir o cache da lista de cidades liberadas (Redis), limpar aqui.
    return cidades.filter(liberada=False).update(liberada=True)


@dataclass(frozen=True)
class EstadoAtendido:
    """Um estado liberado e as suas cidades liberadas, para exibir no site."""

    estado: Estado
    cidades: list[Cidade]


def cidades_atendidas() -> list[EstadoAtendido]:
    """Lista as cidades que aparecem no site, agrupadas por estado.

    Regra (docs/ARQUITETURA.md §9): só cidades `liberada=True` de estados
    `liberado=True`. Estados sem nenhuma cidade liberada ficam de fora.
    Ordem: estados por nome, cidades por nome. Uma consulta só.
    """
    # Quando existir o cache (Redis), guardar este resultado e limpar ao liberar/bloquear.
    cidades = (
        Cidade.objects.filter(liberada=True, uf__liberado=True)
        .select_related("uf")
        .order_by("uf__nome", "nome")
    )
    grupos: dict[str, EstadoAtendido] = {}
    for cidade in cidades:
        if cidade.uf_id not in grupos:
            grupos[cidade.uf_id] = EstadoAtendido(estado=cidade.uf, cidades=[])
        grupos[cidade.uf_id].cidades.append(cidade)
    return list(grupos.values())
