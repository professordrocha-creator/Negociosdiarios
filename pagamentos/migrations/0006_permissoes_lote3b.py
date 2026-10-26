"""Lote 3B: permissões das telas "Cadastros aguardando" (Administrador, Financeiro e Comercial) e "Configuração do
Pix" (só Administrador e Financeiro) e os textos "Sobre esta tela" de Escolher plano e Pagar. Idempotente (não
sobrescreve o que o admin editou)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

_PEDIDOS = ["view_pedidoaguardando", "change_pedidoaguardando"]
_PIX = ["view_configuracaopix", "change_configuracaopix"]
PERMISSOES = {
    "Administrador": _PEDIDOS + _PIX,
    "Financeiro": _PEDIDOS + _PIX,
    "Comercial": _PEDIDOS,
}

TEXTOS_AJUDA = {
    "assinar": (
        "Painel › Escolher plano",
        [
            "Escolha o plano (quantos anúncios ficam no ar ao mesmo tempo) e se paga por mês ou por ano.",
            "Confira o nome da loja e o WhatsApp: é assim que os clientes vão ver você.",
            "Depois vem a tela Pagar, com o Pix. O acesso é liberado assim que a equipe conferir o pagamento.",
        ],
    ),
    "pagar": (
        "Painel › Pagar",
        [
            "Pague pelo app do seu banco: leia o QR Code ou use o Pix copia e cola. O valor já vem preenchido.",
            "Depois de pagar, toque em \"Já paguei\". Se quiser, anexe o comprovante: ajuda a conferir mais rápido.",
            "A equipe confere o pagamento no banco e libera o acesso. Você recebe um e-mail quando estiver tudo certo.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Permissões dos proxies nos grupos e os textos de ajuda."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("pagamentos")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="pagamentos", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS_AJUDA.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("pagamentos", "0005_lote3b"),
        ("core", "0021_lote3b"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
