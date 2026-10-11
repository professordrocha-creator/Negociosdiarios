"""Comando `carregar_municipios`: carrega estados e cidades do IBGE a partir de core/dados/."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services import ARQUIVO_ESTADOS, ARQUIVO_MUNICIPIOS, carregar_municipios


class Command(BaseCommand):
    """Carrega ou atualiza estados e cidades. Seguro para rodar várias vezes (idempotente)."""

    help = (
        "Carrega estados e municípios do IBGE dos CSVs em core/dados/. Pode rodar de novo: "
        "atualiza nomes e coordenadas sem duplicar e sem mexer no que foi liberado no admin."
    )

    def add_arguments(self, parser):
        """Opções para usar outros arquivos (testes) ou outra UF inicial."""
        parser.add_argument("--estados", type=Path, default=ARQUIVO_ESTADOS, help="CSV de estados.")
        parser.add_argument("--municipios", type=Path, default=ARQUIVO_MUNICIPIOS, help="CSV de municípios.")
        parser.add_argument(
            "--uf-liberada",
            default="MT",
            help="UF que nasce liberada na primeira carga (padrão: MT). Não altera estados já existentes.",
        )

    def handle(self, *args, **opcoes):
        """Executa a carga e mostra o resumo."""
        try:
            resultado = carregar_municipios(opcoes["estados"], opcoes["municipios"], opcoes["uf_liberada"])
        except (OSError, ValueError) as erro:
            raise CommandError(f"Carga cancelada, nada foi gravado: {erro}") from erro

        self.stdout.write(
            self.style.SUCCESS(
                f"Estados: {resultado.estados_total} ({resultado.estados_novos} novos). "
                f"Cidades: {resultado.cidades_total} ({resultado.cidades_novas} novas)."
            )
        )
