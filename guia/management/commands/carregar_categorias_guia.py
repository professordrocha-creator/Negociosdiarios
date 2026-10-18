"""Comando `carregar_categorias_guia`: grupos e categorias do guia (docs/guia/categorias_iniciais.csv)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DataError

from guia.services import ARQUIVO_CATEGORIAS, carregar_categorias


class Command(BaseCommand):
    """Carrega ou atualiza as categorias (upsert por slug). Seguro para rodar várias vezes (idempotente)."""

    help = (
        "Carrega grupos e categorias do Guia de Negócios do CSV. Pode rodar de novo: atualiza pelo slug sem "
        "duplicar; categoria que saiu do arquivo continua no banco (desative no admin)."
    )

    def add_arguments(self, parser):
        """Opção para usar outro arquivo (testes)."""
        parser.add_argument("--arquivo", type=Path, default=ARQUIVO_CATEGORIAS, help="CSV de categorias.")

    def handle(self, *args, **opcoes):
        """Executa a carga e mostra o resumo."""
        try:
            resultado = carregar_categorias(opcoes["arquivo"])
        except (OSError, ValueError, KeyError, DataError) as erro:
            raise CommandError(f"Carga cancelada, nada foi gravado: {erro}") from erro
        self.stdout.write(
            self.style.SUCCESS(
                f"Grupos: {resultado.grupos}. Categorias: {resultado.criadas} novas, "
                f"{resultado.atualizadas} atualizadas."
            )
        )
