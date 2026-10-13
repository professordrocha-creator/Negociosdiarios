"""Versão 1 dos Termos e da Política (o texto de rascunho que estava nos templates, agora editável no admin),
permissões e textos de ajuda. A versão é a mesma já gravada nos aceites do cadastro ("2026-10-rascunho"):
ninguém precisa aceitar de novo por causa desta mudança. Idempotente."""

import datetime

from django.contrib.auth.management import create_permissions
from django.db import migrations

VERSAO = "2026-10-rascunho"

TERMOS = """Ao usar o {site}, você concorda com estas regras. Elas valem para quem procura (visitantes) e para quem anuncia (anunciantes).

## 1. O que é o {site}
É um site de classificados de imóveis e veículos operado por {empresa}, com sede em {cidade_sede}. Só anunciam profissionais verificados: corretores com CRECI e empresas com CNPJ.

Não intermediamos negócios. Não somos parte da compra, venda ou locação, não recebemos sinal nem pagamento por elas e não garantimos o negócio. A negociação é sempre direta entre você e o anunciante.

## 2. Para quem procura
- Você pode navegar e falar com os anunciantes sem cadastro.
- As informações dos anúncios (preço, fotos, descrição, situação do bem) são de responsabilidade de quem anuncia. Confira tudo pessoalmente antes de fechar negócio.
- Cuidado com golpes: desconfie de preço muito abaixo do mercado, nunca pague sinal sem ver o bem e a documentação, e confira se quem anuncia é o profissional verificado da página da loja.
- É proibido usar o site para coletar contatos em massa, enviar spam ou tentar acessar áreas restritas.

## 3. Para quem anuncia
- Verificação: o cadastro só é aprovado após conferirmos CRECI (corretores) ou CNPJ (empresas). Podemos pedir documentos e recusar ou suspender cadastros irregulares.
- Responsabilidade pelo conteúdo: você garante que tem autorização para anunciar o bem, que as informações são verdadeiras e que tem direito de uso das fotos.
- É proibido anunciar: bens inexistentes, de terceiros sem autorização, com preço enganoso ou ilegais; conteúdo discriminatório ou ofensivo; dados pessoais de outras pessoas (documentos, placas completas, rostos sem autorização).
- Moderação: anúncios podem passar por análise e ser recusados, suspensos ou removidos se descumprirem estas regras, com aviso do motivo.
- Planos e pagamentos: a assinatura é mensal ou anual e define quantos anúncios ficam ativos ao mesmo tempo. Com a fatura vencida além da carência, os anúncios saem do ar até o pagamento ser confirmado. Regras de cancelamento e reembolso estarão no contrato do anunciante.

## 4. Denúncias e remoção de conteúdo
Qualquer pessoa pode denunciar um anúncio. Analisamos as denúncias e removemos o que violar a lei ou estes termos. Conteúdo que exponha dados pessoais ou imagens íntimas sem autorização é tratado com prioridade (Marco Civil da Internet, arts. 19 e 21).

## 5. Marca e conteúdo do site
A marca, o layout e os textos do {site} pertencem a {empresa}. Os anúncios continuam sendo de quem os criou, que nos autoriza a exibi-los e divulgá-los enquanto estiverem no ar.

## 6. Limites de responsabilidade
Fazemos o possível para o site funcionar sem interrupções e com segurança, mas não respondemos por negócios feitos entre visitantes e anunciantes, nem por informações falsas fornecidas por anunciantes, sem prejuízo dos direitos do consumidor previstos em lei.

## 7. Privacidade
O uso de dados pessoais e os cookies estão descritos na Política de Privacidade.

## 8. Mudanças nestes termos
Podemos atualizar estes termos. A versão em vigor fica sempre nesta página, com o número e a data; anunciantes veem o resumo das mudanças e aceitam a versão nova no próximo acesso ao painel.

## 9. Lei e foro
Valem as leis brasileiras. Fica eleito o foro da comarca de {cidade_sede}, ressalvado o direito do consumidor de propor ação no foro do seu domicílio.

## 10. Contato
Dúvidas: {email_contato}."""

PRIVACIDADE = """Em poucas palavras: quem só procura imóveis e veículos não precisa se cadastrar, e a conversa com o anunciante acontece direto no WhatsApp, sem passar por nós. Coletamos o mínimo necessário para o site funcionar com segurança.

## 1. Quem cuida dos seus dados
O {site} é operado por {empresa}, com sede em {cidade_sede}, que é a controladora dos dados pessoais tratados no site (Lei nº 13.709/2018, a LGPD). O contato do encarregado está no fim desta página.

## 2. Quais dados tratamos, para quê e por quanto tempo
- Visitante: registros de acesso (IP, data e hora), para segurança e cumprimento do Marco Civil da Internet (art. 15). Base legal: obrigação legal. Guarda: 6 meses.
- Visitante: visualizações de anúncios e de publicidade, contadas sem guardar IP nem usar cookie (só números). Base legal: legítimo interesse.
- Anunciante: nome, e-mail, senha (guardada só como código irreversível) e datas de acesso, para criar e manter a conta. Base legal: execução de contrato. Guarda: enquanto a conta existir.
- Anunciante: CRECI ou CNPJ (e CPF do corretor autônomo, quando houver nota), para verificar que é profissional e emitir nota fiscal. Base legal: contrato, obrigação legal e legítimo interesse. Guarda: enquanto ativo e 5 anos depois.
- Anunciante: telefone/WhatsApp público, para os interessados falarem com você. Base legal: contrato. Guarda: enquanto a conta estiver ativa.
- Anunciante: faturas e comprovantes de pagamento (que podem ter nome e banco de quem pagou), para cobrança e obrigações fiscais. Base legal: obrigação legal. Guarda: 5 anos, em armazenamento privado.
- Anunciante: aceite dos Termos e desta Política (versão, data e hora), para provar o que foi aceito.
- Terceiros: endereço do imóvel (no mapa, aproximado por padrão) e pessoas que apareçam em fotos, para divulgar o anúncio. Base legal: legítimo interesse do anunciante. Guarda: até o anúncio sair do ar e 90 dias depois.
- Patrocinadores de publicidade: nome da empresa e contato, para vender e cobrar a campanha. Base legal: contrato.
- Equipe do site: dados de conta, códigos de acesso temporários e tentativas de login com erro, para proteger o painel administrativo.

## 3. O que não fazemos
- Não vendemos nem alugamos dados pessoais.
- Não usamos anúncios do Google nem rastreadores de publicidade; a publicidade do site é vendida direto a empresas da região e não usa seus dados.
- Não guardamos as conversas entre visitantes e anunciantes: elas acontecem no WhatsApp.
- Não pedimos a placa completa de veículos nem mostramos CPF de ninguém.
- Removemos a localização (dados EXIF/GPS) de todas as fotos enviadas.

## 4. Com quem compartilhamos
Só com empresas que nos ajudam a operar o site (operadores), que tratam os dados conforme nossas instruções:
- Hospedagem do site e do banco de dados (servidor VPS; provedor a definir antes do lançamento).
- Armazenamento de fotos e comprovantes: Cloudflare R2 (comprovantes em área privada).
- Envio de e-mails do sistema (códigos de acesso, avisos, faturas): Brevo ou Amazon SES (a definir).
- Monitoramento de erros: ferramenta configurada para não receber dados pessoais.

Também podemos fornecer dados a autoridades quando a lei ou uma ordem judicial exigir. Alguns provedores podem manter servidores fora do Brasil; nesse caso a transferência segue o art. 33 da LGPD.

## 5. Como protegemos
Conexão sempre criptografada (HTTPS), senhas guardadas com Argon2, acesso da equipe com endereço secreto, bloqueio após tentativas erradas e código de confirmação em navegador novo, comprovantes fora da área pública, backups criptografados e acesso restrito por perfil de trabalho.

## 6. Seus direitos
Pela LGPD (art. 18) você pode pedir: confirmação de que tratamos seus dados e acesso a eles; correção; anonimização, bloqueio ou eliminação do que for desnecessário; portabilidade; informação sobre com quem compartilhamos; e revogação de consentimento, quando ele for a base legal.

Anunciantes podem baixar uma cópia dos dados e excluir a conta direto no painel, em "Meus dados". Para qualquer pessoa, basta escrever para {email_privacidade}. Se não ficar satisfeito, você pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).

Alguns dados precisam ser mantidos mesmo após um pedido de exclusão, quando a lei exige (por exemplo, faturas e comprovantes por 5 anos).

## 7. Crianças e adolescentes
O site não é direcionado a menores de 18 anos. Anunciantes precisam ser corretores habilitados ou empresas.

## 8. Incidentes de segurança
Se acontecer um incidente que possa trazer risco ou dano relevante, comunicaremos a ANPD e as pessoas afetadas nos prazos da regulamentação.

## 9. Mudanças nesta política
Quando esta política mudar, a nova versão é publicada aqui, com o número e a data. Anunciantes veem o resumo das mudanças e aceitam a versão nova no próximo acesso ao painel."""

AJUDA = {
    "meus_dados": (
        "Painel › Meus dados",
        [
            "Veja o que o site guarda sobre você e baixe uma cópia completa (JSON) depois de confirmar a senha.",
            "Para corrigir dados, use as telas do painel (Página da loja, anúncios) ou escreva para o e-mail de privacidade.",
            "Excluir a conta apaga seus dados de contato e tira a loja e os anúncios do ar; faturas ficam pela guarda fiscal.",
        ],
    ),
    "excluir_conta": (
        "Painel › Meus dados › Excluir minha conta",
        [
            "A exclusão não pode ser desfeita: confirme a senha e digite EXCLUIR.",
            "Fatura em aberto não impede a exclusão, mas o que já é devido continua devido.",
            "A confirmação vai para o e-mail que você usa hoje.",
        ],
    ),
    "aceitar_termos": (
        "Termos atualizados",
        [
            "Mudamos os Termos de Uso ou a Política de Privacidade. Veja o resumo e, se quiser, o texto completo.",
            "Para continuar usando o painel, marque o aceite. Sem aceitar, você ainda pode baixar seus dados ou excluir a conta.",
        ],
    ),
}

# Só o Administrador cuida dos documentos legais e dos pedidos de titulares (ADMINISTRACAO.md).
PERMISSOES = {
    "Administrador": [
        "view_documentolegal",
        "add_documentolegal",
        "change_documentolegal",
        "view_pedidotitular",
        "add_pedidotitular",
        "change_pedidotitular",
    ]
}


def criar(apps, schema_editor):
    """Documentos v1, permissões e textos de ajuda, sem sobrescrever o que já existe."""
    DocumentoLegal = apps.get_model("privacidade", "DocumentoLegal")
    for tipo, texto in (("termos", TERMOS), ("privacidade", PRIVACIDADE)):
        DocumentoLegal.objects.get_or_create(
            tipo=tipo,
            versao=VERSAO,
            defaults={
                "vigencia": datetime.date(2026, 10, 1),
                "texto": texto,
                "resumo": "Primeira versão (rascunho, antes da revisão jurídica).",
                "publicado": True,
                "revisao_juridica_pendente": True,
            },
        )

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("privacidade")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="privacidade", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in AJUDA.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("privacidade", "0001_initial"),
        ("core", "0016_configuracao_encarregado_nome_and_more"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
