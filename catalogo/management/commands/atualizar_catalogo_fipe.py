"""Comando `atualizar_catalogo_fipe`: reescreve catalogo/dados/fipe.csv.

- Sem opções: baixa a Tabela FIPE do mês (API pública) e grava o CSV.
- `--reprocessar`: não baixa nada; refaz a separação modelo/versão do CSV atual com as regras de
  `catalogo.services` (use depois de mudar as exceções de nomes).

Opcional (o arquivo já vem no repositório). Depois de rodar, confira o diff, rode o
`carregar_catalogo` e faça o commit do CSV novo. Não grava nada no banco.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalogo import fipe
from catalogo.services import ARQUIVO_FIPE, COLUNAS, ler_arquivo, reprocessar_linha


class Command(BaseCommand):
    """Gera o CSV do catálogo a partir da API pública da FIPE (veiculos.fipe.org.br) ou do CSV atual."""

    help = "Baixa marcas e modelos da Tabela FIPE (ou reprocessa o CSV atual) e reescreve o fipe.csv."

    def add_arguments(self, parser):
        """Arquivo de saída, pausa entre requisições e o modo sem internet."""
        parser.add_argument("--saida", type=Path, default=ARQUIVO_FIPE, help="CSV a gravar.")
        parser.add_argument(
            "--pausa", type=float, default=1.5, help="Segundos entre requisições (padrão 1,5)."
        )
        parser.add_argument(
            "--reprocessar",
            action="store_true",
            help="Não baixa: refaz a separação modelo/versão do CSV atual com as regras novas.",
        )

    def handle(self, *args, **opcoes):
        """Monta as linhas (FIPE ou CSV atual), ordena e grava."""
        saida: Path = opcoes["saida"]
        if opcoes["reprocessar"]:
            linhas = [reprocessar_linha(linha) for linha in ler_arquivo(saida)]
            self._gravar(saida, linhas)
            return
        try:
            referencia, mes = fipe.tabela_mais_recente()
            self.stdout.write(f"Tabela FIPE de {mes} (código {referencia}).")
            linhas = list(fipe.linhas_do_catalogo(referencia, opcoes["pausa"], self.stdout.write))
        except OSError as erro:
            raise CommandError(
                f"Não foi possível falar com a FIPE: {erro}. O arquivo não foi alterado."
            ) from erro
        self._gravar(saida, linhas)
        saida.with_name("fipe_referencia.txt").write_text(
            f"Tabela FIPE de {mes} (código {referencia}), gerada em {timezone.localdate():%d/%m/%Y}.\n",
            encoding="utf-8",
        )

    def _gravar(self, saida: Path, linhas: list[dict]) -> None:
        """Sem repetir (tipo, marca, modelo, versão), em ordem, com o fim de linha do Linux."""
        unicas = {(l["tipo"], l["marca"], l["modelo"], l["versao"]): l for l in linhas}  # noqa: E741
        ordenadas = sorted(unicas.values(), key=lambda l: (l["tipo"], l["marca"], l["modelo"], l["versao"]))  # noqa: E741
        with saida.open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, lineterminator="\n")
            escritor.writeheader()
            escritor.writerows(ordenadas)
        self.stdout.write(self.style.SUCCESS(f"{len(ordenadas)} versões gravadas em {saida}."))
