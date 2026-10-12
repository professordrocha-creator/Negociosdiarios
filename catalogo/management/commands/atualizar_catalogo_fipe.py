"""Comando `atualizar_catalogo_fipe`: baixa a Tabela FIPE do mês e reescreve catalogo/dados/fipe.csv.

Opcional (o arquivo já vem no repositório). Depois de rodar, confira o diff, rode o
`carregar_catalogo` e faça o commit do CSV novo. Não grava nada no banco.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalogo import fipe
from catalogo.services import ARQUIVO_FIPE, COLUNAS


class Command(BaseCommand):
    """Gera o CSV do catálogo a partir da API pública da FIPE (veiculos.fipe.org.br)."""

    help = "Baixa marcas e modelos da Tabela FIPE e reescreve catalogo/dados/fipe.csv (não mexe no banco)."

    def add_arguments(self, parser):
        """Arquivo de saída e pausa entre requisições."""
        parser.add_argument("--saida", type=Path, default=ARQUIVO_FIPE, help="CSV a gravar.")
        parser.add_argument(
            "--pausa", type=float, default=1.5, help="Segundos entre requisições (padrão 1,5)."
        )

    def handle(self, *args, **opcoes):
        """Baixa, ordena e grava o CSV e o arquivo de referência (mês da tabela)."""
        try:
            referencia, mes = fipe.tabela_mais_recente()
            self.stdout.write(f"Tabela FIPE de {mes} (código {referencia}).")
            linhas = list(fipe.linhas_do_catalogo(referencia, opcoes["pausa"], self.stdout.write))
        except OSError as erro:
            raise CommandError(
                f"Não foi possível falar com a FIPE: {erro}. O arquivo não foi alterado."
            ) from erro
        unicas = {(l["tipo"], l["marca"], l["modelo"], l["versao"]): l for l in linhas}  # noqa: E741
        ordenadas = sorted(unicas.values(), key=lambda l: (l["tipo"], l["marca"], l["modelo"], l["versao"]))  # noqa: E741
        saida: Path = opcoes["saida"]
        with saida.open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, lineterminator="\n")
            escritor.writeheader()
            escritor.writerows(ordenadas)
        saida.with_name("fipe_referencia.txt").write_text(
            f"Tabela FIPE de {mes} (código {referencia}), gerada em {timezone.localdate():%d/%m/%Y}.\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"{len(ordenadas)} versões gravadas em {saida}."))
