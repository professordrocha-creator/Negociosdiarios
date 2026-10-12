"""Comando `carregar_catalogo`: carrega marcas, modelos e versões de catalogo/dados/fipe.csv."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogo.services import ARQUIVO_FIPE, carregar_catalogo


class Command(BaseCommand):
    """Carrega ou atualiza o catálogo de veículos. Seguro para rodar várias vezes (idempotente)."""

    help = (
        "Carrega o catálogo de veículos (Tabela FIPE) do CSV em catalogo/dados/. Pode rodar de novo: "
        "atualiza sem duplicar, não apaga nada e não reativa o que o admin escondeu."
    )

    def add_arguments(self, parser):
        """Outro arquivo (testes)."""
        parser.add_argument("--arquivo", type=Path, default=ARQUIVO_FIPE, help="CSV do catálogo.")

    def handle(self, *args, **opcoes):
        """Executa a carga e mostra o resumo."""
        try:
            resultado = carregar_catalogo(opcoes["arquivo"])
        except (OSError, ValueError) as erro:
            raise CommandError(f"Carga cancelada, nada foi gravado: {erro}") from erro
        self.stdout.write(
            self.style.SUCCESS(
                f"Marcas: {resultado.marcas}. Modelos: {resultado.modelos}. "
                f"Versões: {resultado.versoes} ({resultado.versoes_novas} novas)."
            )
        )
