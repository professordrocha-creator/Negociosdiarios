"""Comando `reindexar_busca`: recalcula o índice de busca de todos os anúncios.

Use depois de mudar a regra do índice (`anuncios/indice.py`) ou de renomear cidades, bairros ou
modelos do catálogo em massa. Seguro para rodar várias vezes.
"""

from django.core.management.base import BaseCommand

from anuncios.indice import reindexar_todos


class Command(BaseCommand):
    """Recalcula `busca` e `texto_busca` de todos os anúncios."""

    help = "Recalcula o índice de busca (texto e semelhança) de todos os anúncios."

    def handle(self, *args, **opcoes):
        """Executa e mostra quantos."""
        self.stdout.write(self.style.SUCCESS(f"{reindexar_todos()} anúncios reindexados."))
