"""Comando `testar_celery`: dispara a tarefa de exemplo e espera o worker responder."""

from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.core.management.base import BaseCommand, CommandError

from core.tasks import batimento


class Command(BaseCommand):
    """Prova ponta a ponta que a fila (Redis) e o worker do Celery estão funcionando."""

    help = "Coloca a tarefa de exemplo (core.tasks.batimento) na fila e espera o worker devolver a hora."

    def add_arguments(self, parser):
        """Quanto tempo esperar pelo worker."""
        parser.add_argument("--espera", type=int, default=15, help="Segundos de espera (padrão: 15).")

    def handle(self, *args, **opcoes):
        """Enfileira, espera e mostra o resultado (ou o que conferir se não vier)."""
        resultado = batimento.delay()
        self.stdout.write(f"Tarefa enviada para a fila (id {resultado.id}). Esperando o worker...")
        try:
            hora = resultado.get(timeout=opcoes["espera"])
        except CeleryTimeoutError as erro:
            raise CommandError(
                "O worker não respondeu. Confira: docker compose ps (worker de pé?) e "
                "docker compose logs --tail=50 worker."
            ) from erro
        self.stdout.write(self.style.SUCCESS(f"Celery funcionando: o worker executou a tarefa às {hora}."))
