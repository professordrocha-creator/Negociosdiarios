"""Cliente da API pública da Tabela FIPE (veiculos.fipe.org.br), usado só para GERAR o fipe.csv.

O site nunca consulta a FIPE em produção: o arquivo fica no repositório e é carregado pelo
`carregar_catalogo`. O comando `atualizar_catalogo_fipe` usa este módulo para baixar a tabela
do mês e reescrever o CSV (uma requisição por marca, com pausa entre elas, para não sobrecarregar).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator

from catalogo.models import TipoVeiculo
from catalogo.services import limpar_rotulo, nome_da_marca, separar_modelo_e_versao, tipo_do_carro

BASE = "https://veiculos.fipe.org.br/api/veiculos/"
# Identifica o projeto (sem se passar por navegador).
AGENTE = "NegociosDiarios-catalogo/1.0 (catalogo de marcas e modelos; contato no site)"
TIPOS_FIPE = {1: "carros", 2: "motos", 3: "caminhoes"}


def _post(rota: str, dados: dict, tentativas: int = 6) -> object:
    """POST na API da FIPE (formulário) e devolve o JSON.

    Se a FIPE pedir calma (HTTP 429 ou 5xx), espera o que ela mandar (Retry-After) ou 30 s, 60 s,
    120 s... e tenta de novo, até `tentativas` vezes.
    """
    requisicao = urllib.request.Request(  # noqa: S310 (URL fixa https da FIPE)
        BASE + rota,
        data=urllib.parse.urlencode(dados).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://veiculos.fipe.org.br/",
            "User-Agent": AGENTE,
        },
    )
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(requisicao, timeout=30) as resposta:  # noqa: S310 (URL fixa da FIPE)
                return json.loads(resposta.read().decode())
        except urllib.error.HTTPError as erro:
            if erro.code != 429 and erro.code < 500 or tentativa == tentativas - 1:
                raise
            espera = erro.headers.get("Retry-After")
            time.sleep(int(espera) if espera and espera.isdigit() else 30 * 2**tentativa)
    raise OSError("FIPE sem resposta.")


def tabela_mais_recente() -> tuple[int, str]:
    """Código e mês da tabela de referência mais recente (ex.: 338, "outubro/2026")."""
    tabelas = _post("ConsultarTabelaDeReferencia", {})
    return int(tabelas[0]["Codigo"]), tabelas[0]["Mes"].strip()


def linhas_do_catalogo(
    referencia: int, pausa: float = 1.5, avisar: Callable[[str], None] = print
) -> Iterator[dict[str, str]]:
    """Linhas do CSV (tipo, marca, modelo, versao, codigo_fipe) para todas as marcas e tipos."""
    for codigo_tipo, nome_tipo in TIPOS_FIPE.items():
        marcas = _post(
            "ConsultarMarcas", {"codigoTabelaReferencia": referencia, "codigoTipoVeiculo": codigo_tipo}
        )
        avisar(f"{nome_tipo}: {len(marcas)} marcas")
        for marca in marcas:
            time.sleep(pausa)
            resposta = _post(
                "ConsultarModelos",
                {
                    "codigoTabelaReferencia": referencia,
                    "codigoTipoVeiculo": codigo_tipo,
                    "codigoMarca": marca["Value"],
                },
            )
            nome_marca = nome_da_marca(marca["Label"])
            for item in resposta.get("Modelos", []):
                modelo, versao = separar_modelo_e_versao(limpar_rotulo(item["Label"]))
                if codigo_tipo == 1:
                    tipo = tipo_do_carro(nome_marca, modelo)
                elif codigo_tipo == 2:
                    tipo = TipoVeiculo.MOTO
                else:
                    tipo = TipoVeiculo.CAMINHAO
                yield {
                    "tipo": str(tipo),
                    "marca": nome_marca,
                    "modelo": modelo,
                    "versao": versao,
                    "codigo_fipe": str(item["Value"]),
                }
