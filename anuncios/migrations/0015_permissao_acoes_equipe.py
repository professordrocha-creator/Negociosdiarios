"""Administrador e Moderador passam a alterar anúncios pelo admin: só o "destaque até" e as ações Pausar,
Reativar e Remover (o conteúdo continua só leitura). Financeiro e Comercial seguem só consultando. Idempotente."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GRUPOS = ["Administrador", "Moderador"]


def criar(apps, schema_editor):
    """Dá a permissão change_anuncio aos dois grupos."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("anuncios")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    permissao = Permission.objects.get(content_type__app_label="anuncios", codename="change_anuncio")
    for nome in GRUPOS:
        Group.objects.get(name=nome).permissions.add(permissao)


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0014_ajustes_admin"), ("contas", "0002_grupos_permissao")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
