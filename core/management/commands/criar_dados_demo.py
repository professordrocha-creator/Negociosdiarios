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
        self.stdout.write("Todas as senhas = DEMO_SENHA do .env.")
        self.stdout.write(f"Equipe demo ({len(dados['equipe'])}), entra pelo admin:")
        for pessoa in dados["equipe"]:
            self.stdout.write(f"  {pessoa['email']}  (grupo {pessoa['grupo']})")
        self.stdout.write(f"Lojas demo ativas ({len(dados['lojas'])}), entram em /entrar/ e veem o /painel/:")
        for loja in dados["lojas"]:
            self.stdout.write(f"  {loja['email']}  ({loja['nome']})")
        pendentes = dados.get("lojas_pendentes", [])
        if pendentes:
            self.stdout.write(f"Lojas demo pendentes ({len(pendentes)}), para testar a aprovação no admin:")
            for loja in pendentes:
                self.stdout.write(f"  {loja['email']}  ({loja['nome']})")
        em_atraso = dados.get("assinaturas_em_atraso", [])
        self.stdout.write(
            "Cada loja ativa tem um plano (Básico, Profissional ou Premium, mensal ou anual); "
            f"em atraso, com os anúncios pausados: {', '.join(em_atraso) or 'nenhuma'}."
        )
        self.stdout.write(
            f"{resumo.anuncios} imóveis demo no banco, com fotos de exemplo e estatísticas "
            "(veículos: Sprint 4). Aparecem na home e nas lojas com MOSTRAR_DEMO=True "
            "e no painel do Paulo Mendes."
        )
