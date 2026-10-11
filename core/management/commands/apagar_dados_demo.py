"""Comando `apagar_dados_demo`: remove de uma vez tudo o que é demonstração."""

from django.core.management.base import BaseCommand

from core.services import apagar_dados_demo


class Command(BaseCommand):
    """Apaga os dados de demonstração. Obrigatório antes do lançamento (Sprint 9)."""

    help = (
        "Remove TODOS os dados de demonstração (registros com demo=True) e desliga só as cidades "
        "que a demonstração liberou. Dados reais não são tocados. Pede confirmação."
    )

    def add_arguments(self, parser):
        """`--sim` pula a pergunta (para scripts)."""
        parser.add_argument("--sim", action="store_true", help="Não pedir confirmação.")

    def handle(self, *args, **opcoes):
        """Confirma, apaga e mostra o resumo."""
        if not opcoes["sim"]:
            resposta = input("Apagar todos os dados de demonstração? Digite 'sim' para confirmar: ")
            if resposta.strip().lower() != "sim":
                self.stdout.write("Nada foi apagado.")
                return
        resumo = apagar_dados_demo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Dados de demonstração apagados: {resumo.usuarios} usuário(s); "
                f"{resumo.cidades} cidade(s) desligada(s)."
            )
        )
