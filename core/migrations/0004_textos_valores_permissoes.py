"""Dados iniciais da Sprint 1 (parte 3) e permissões dos grupos nos modelos novos do core.

- Textos de ajuda ("Sobre esta tela") que antes ficavam fixos no código.
- Valores da empresa da página Sobre (antes fixos no template).
- Permissões: Administrador edita identidade, valores, textos, regiões e bairros; os
  demais grupos só consultam regiões e bairros. Ninguém apaga (exclusão é lógica).
Idempotente: não sobrescreve o que já tiver sido editado no admin.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

TEXTOS_AJUDA = {
    "planos": (
        "Página de planos",
        [
            "Os planos diferem só na quantidade de anúncios ativos ao mesmo tempo.",
            "No plano anual você paga o equivalente a 10 mensalidades e usa 12 meses.",
            "Todo anunciante passa pela verificação de CRECI (corretores) ou CNPJ (empresas).",
        ],
    ),
    "anuncie": (
        "Mídia kit (Anuncie sua marca)",
        [
            "A publicidade é vendida direto para empresas da região, sem anúncios do Google.",
            'Toda peça leva o rótulo "Publicidade" e pode ser segmentada por cidade e por seção.',
            "Imobiliárias, corretores e revendas só compram publicidade se forem assinantes.",
        ],
    ),
    "contato": (
        "Fale com a gente",
        [
            "Atendimento em horário comercial (horário de Mato Grosso).",
            "Para assuntos de dados pessoais (LGPD), use o e-mail de privacidade.",
        ],
    ),
    "entrar": (
        "Login do anunciante (/entrar/)",
        [
            "Área do anunciante: entre com o e-mail e a senha da sua loja.",
            "Só lojas aprovadas (CRECI ou CNPJ conferido) entram. Cadastro em análise ainda não entra.",
            "5 senhas erradas seguidas bloqueiam o acesso por 1 hora.",
        ],
    ),
    "painel": (
        "Painel do anunciante",
        [
            "Aqui você acompanha os dados da sua loja e os seus anúncios.",
            "Anúncios no plano: publicados + em análise. Pausados não contam no limite.",
            'Plano, estatísticas e faturas chegam nas próximas etapas (marcados como "em breve").',
        ],
    ),
    "cadastro": (
        "Cadastro de anunciante",
        [
            "Corretor autônomo se cadastra com o CRECI; imobiliárias, revendas e garagens com o CNPJ.",
            "Sua cidade ainda não é atendida? Cadastre mesmo assim: avaliamos a liberação.",
            "Depois de enviar, confirme o e-mail pelo link que mandamos (vale 48 horas).",
            "Com o e-mail confirmado, a equipe confere o documento e avisa por e-mail quando aprovar.",
        ],
    ),
    "em_breve": (
        'Páginas "Em breve"',
        ["Esta parte do site ainda está em construção; o link já existe para você saber o que vem aí."],
    ),
}

VALORES = [
    ("verificado", "Confiança", "Só anunciam corretores com CRECI e empresas com CNPJ verificados."),
    ("pin", "Proximidade", "Feito em Mato Grosso, por gente que conhece as cidades e os bairros."),
    ("olho", "Transparência", "Preço à vista no anúncio e contato direto com quem vende, sem intermediário."),
    ("alerta", "Respeito aos seus dados", "Coletamos o mínimo e seguimos a LGPD. Visitante não precisa de cadastro."),
    ("lista", "Simplicidade", "Encontrar, comparar e chamar no WhatsApp em poucos toques."),
]

PERMISSOES = {
    "Administrador": {
        "core": [
            "view_configuracao",
            "change_configuracao",
            "view_valorempresa",
            "add_valorempresa",
            "change_valorempresa",
            "view_textoajuda",
            "add_textoajuda",
            "change_textoajuda",
            "view_regiao",
            "add_regiao",
            "change_regiao",
            "view_bairro",
            "add_bairro",
            "change_bairro",
        ],
    },
    "Moderador": {"core": ["view_regiao", "view_bairro"]},
    "Financeiro": {"core": ["view_regiao", "view_bairro"]},
    "Comercial": {"core": ["view_regiao", "view_bairro"]},
}


def carregar(apps, schema_editor):
    """Cria textos e valores (se ainda não existem) e liga as permissões aos grupos."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    ValorEmpresa = apps.get_model("core", "ValorEmpresa")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for chave, (descricao, itens) in TEXTOS_AJUDA.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})
    if not ValorEmpresa.objects.exists():
        for ordem, (icone, titulo, texto) in enumerate(VALORES, start=1):
            ValorEmpresa.objects.create(ordem=ordem * 10, icone=icone, titulo=titulo, texto=texto)

    app_config = apps.get_app_config("core")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, por_app in PERMISSOES.items():
        grupo = Group.objects.get(name=nome)
        for app, codenames in por_app.items():
            permissoes = list(Permission.objects.filter(content_type__app_label=app, codename__in=codenames))
            if len(permissoes) != len(codenames):
                raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
            grupo.permissions.add(*permissoes)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_configuracao_textoajuda_valorempresa_regiao_bairro"),
        ("contas", "0002_grupos_permissao"),
    ]

    # Desfazer não apaga textos nem valores (podem ter sido editados no admin).
    operations = [migrations.RunPython(carregar, migrations.RunPython.noop)]
