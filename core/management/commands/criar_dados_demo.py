"""Comando `criar_dados_demo`: dados fictícios para ver e testar as telas (só em dev)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import criar_dados_demo, ler_demo


class Command(BaseCommand):
    """Cria ou atualiza os dados de demonstração. Pode rodar quantas vezes quiser."""

    help = (
        "Cria/atualiza os dados de DEMONSTRAÇÃO (core/dados/demo.json): usuários de equipe demo "
        "e cidades liberadas. Só com DEBUG=True; senha dos usuários = DEMO_SENHA do .env. "
        "Desfazer: apagar_dados_demo."
    )

    def handle(self, *args, **opcoes):
        """Cria os dados e mostra como acessar (sem mostrar a senha)."""
        try:
            resumo = criar_dados_demo(settings.DEMO_SENHA)
        except (PermissionError, ValueError) as erro:
            raise CommandError(str(erro)) from erro

        dados = ler_demo()
        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))
        self.stdout.write(f"Cidades liberadas agora pela demonstração: {resumo.cidades}")
        self.stdout.write(f"Usuários de equipe demo ({resumo.usuarios}), senha = DEMO_SENHA do .env:")
        for pessoa in dados["equipe"]:
            self.stdout.write(f"  {pessoa['email']}  (grupo {pessoa['grupo']})")
        self.stdout.write(
            f"Lojas ({len(dados['lojas'])}) e anúncios ({len(dados['anuncios'])}) fictícios aparecem na home "
            "com MOSTRAR_DEMO=True no .env (viram registros no banco nas Sprints 1 a 3)."
        )
