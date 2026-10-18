"""Comando `apagar_dados_demo`: remove de uma vez tudo o que é demonstração (antes do lançamento).

Seguro: só registros com demo=True (e as cidades que a demonstração ligou); superusuário, contas reais e as
configurações (Identidade do site, Configuração do guia, planos, categorias) não são tocados. Pede que
a pessoa digite um texto exato para confirmar (docs/DEPLOY.md, "Antes de abrir ao público")."""

from django.core.management.base import BaseCommand

from core.services import apagar_dados_demo


class Command(BaseCommand):
    """Apaga os dados de demonstração. Obrigatório antes do lançamento (Sprint 9)."""

    help = (
        "Remove TODOS os dados de demonstração (registros com demo=True) e desliga só as cidades "
        "que a demonstração liberou. Dados reais não são tocados. Pede confirmação."
    )

    TEXTO = "APAGAR DEMONSTRACAO"

    def add_arguments(self, parser):
        """`--confirmar "APAGAR DEMONSTRACAO"` pula a pergunta (para scripts); qualquer outro texto recusa."""
        parser.add_argument("--confirmar", default="", help=f'Digite "{self.TEXTO}" para não perguntar.')

    def handle(self, *args, **opcoes):
        """Confirma pelo texto exato, apaga e mostra o resumo."""
        resposta = opcoes["confirmar"] or input(
            f"Isto apaga TODOS os dados de demonstração. Para confirmar, digite {self.TEXTO}: "
        )
        if resposta.strip() != self.TEXTO:
            self.stdout.write("Nada foi apagado (texto de confirmação diferente).")
            return
        resumo = apagar_dados_demo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Dados de demonstração apagados: {resumo.usuarios} usuário(s); "
                f"{resumo.cidades} cidade(s) desligada(s)."
            )
        )
