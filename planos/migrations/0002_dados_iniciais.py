"""Dados iniciais do app planos: os 3 planos (valores que estavam no settings),
permissões dos grupos e o texto de ajuda da tela "Meu plano". Idempotente.

Depois desta migration, preços e limites só mudam pelo admin (nunca no código).
"""

from decimal import Decimal

from django.contrib.auth.management import create_permissions
from django.db import migrations

PLANOS = [
    ("basico", "Básico", 10, "49.90", "499.00", 1),
    ("profissional", "Profissional", 25, "99.90", "999.00", 2),
    ("premium", "Premium", 50, "149.90", "1499.00", 3),
]

# Financeiro cuida de preços, assinaturas e pedidos; Administrador também; os demais só consultam.
_TUDO = [
    "view_plano",
    "add_plano",
    "change_plano",
    "view_assinatura",
    "add_assinatura",
    "change_assinatura",
    "view_pedidotrocaplano",
    "change_pedidotrocaplano",
]
_VER = ["view_plano", "view_assinatura", "view_pedidotrocaplano"]
PERMISSOES = {"Administrador": _TUDO, "Financeiro": _TUDO, "Moderador": _VER, "Comercial": _VER}

TEXTO_AJUDA = (
    "Painel › Meu plano",
    [
        "Aqui você vê seu plano, quantos anúncios já usou e o próximo vencimento.",
        "Para trocar de plano, escolha o novo plano e a forma de pagamento e envie o pedido."
        " A equipe analisa e avisa por e-mail.",
        "Se o pagamento atrasar além da carência, seus anúncios ficam pausados (nunca apagados)"
        " e voltam assim que o pagamento for registrado.",
        "Ao mudar para um plano menor, você escolhe quais anúncios manter; os demais ficam pausados.",
    ],
)


def criar(apps, schema_editor):
    """Cria planos, permissões e texto de ajuda sem sobrescrever o que já existe."""
    Plano = apps.get_model("planos", "Plano")
    for slug, nome, limite, mensal, anual, ordem in PLANOS:
        Plano.objects.get_or_create(
            slug=slug,
            defaults={
                "nome": nome,
                "limite_anuncios": limite,
                "preco_mensal": Decimal(mensal),
                "preco_anual": Decimal(anual),
                "ordem": ordem,
                "ativo": True,
            },
        )

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("planos")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="planos", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    descricao, itens = TEXTO_AJUDA
    TextoAjuda.objects.get_or_create(chave="meu_plano", defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("planos", "0001_initial"),
        ("core", "0008_configuracao_carencia_dias"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
