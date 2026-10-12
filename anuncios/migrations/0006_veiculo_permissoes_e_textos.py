"""Ficha do veículo: permissão de consulta para quem já vê anúncios, e o texto de ajuda da escolha
da categoria ("Novo anúncio"). Idempotente."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GRUPOS = ["Administrador", "Moderador", "Financeiro", "Comercial"]

TEXTOS = {
    "anuncio_categoria": (
        "Painel › Novo anúncio",
        [
            "Escolha o que vai anunciar: imóvel ou veículo.",
            "Veículo usa o catálogo da Tabela FIPE (marca, modelo e versão), sem mapa.",
            "Imóvel tem uma etapa de localização com mapa.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Permissão view_detalheveiculo nos grupos e textos novos (sem sobrescrever edições do admin)."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("anuncios")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    permissao = Permission.objects.get(content_type__app_label="anuncios", codename="view_detalheveiculo")
    for nome in GRUPOS:
        Group.objects.get(name=nome).permissions.add(permissao)
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0005_detalheveiculo_historicaldetalheveiculo"),
        ("contas", "0002_grupos_permissao"),
        ("core", "0009_configuracao_aviso_expiracao_dias_and_more"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
