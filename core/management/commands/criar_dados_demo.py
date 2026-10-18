"""Comando `criar_dados_demo`: dados fictícios para ver e testar as telas (dev ou servidor de teste)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services import criar_dados_demo, ler_demo


class Command(BaseCommand):
    """Cria ou atualiza os dados de demonstração. Pode rodar quantas vezes quiser."""

    help = (
        "Cria/atualiza os dados de DEMONSTRAÇÃO (core/dados/demo.json), todos marcados como demo: usuários "
        "de equipe (um por grupo), cidades, regiões e bairros, lojas com login e planos, anúncios com "
        "fotos e "
        "estatísticas, faturas, campanhas de publicidade, pedido de titular, denúncias e o Guia de Negócios "
        "(perfis, pedidos, lista de convites e um termo novo). Roda em dev (DEBUG=True) ou no servidor de "
        "teste "
        "(DEMO_NO_SERVIDOR=True, que exige SITE_NOINDEX=True). Senha dos usuários = DEMO_SENHA (atenção: "
        "rodar de novo redefine essas senhas). Desfazer: apagar_dados_demo."
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
            "Faturas demo (Painel › Faturas e admin › Faturas e pagamentos): histórico pago em todas as "
            "lojas, uma "
            "aberta, uma aguardando confirmação (comprovante fictício) e a das lojas em atraso vencida."
        )
        self.stdout.write(
            "Publicidade demo: 3 campanhas fictícias (banner na home e no anúncio, banner e nativo na busca, "
            "card no rodapé da home), com 14 dias de números e faturas (uma paga, duas abertas)."
        )
        self.stdout.write("LGPD demo: 1 pedido de titular fictício em aberto (admin › Privacidade).")
        self.stdout.write(
            "Denúncias demo: 2 pendentes (golpe e já vendido) em admin › Moderação › Denúncias."
        )
        self.stdout.write(
            f"{resumo.anuncios} anúncios demo no banco (imóveis do Paulo Mendes e veículos das revendas), "
            "com fotos de exemplo e estatísticas. Aparecem na home e nas lojas com MOSTRAR_DEMO=True "
            "e no painel de cada loja."
        )
        self.stdout.write(
            "Guia de Negócios demo: cerca de 60 perfis em 3 cidades, 6 pedidos do titular, 15 contatos de "
            "convite "
            "e um termo novo pendente (admin › Guia de Negócios)."
        )
