"""Permissões dos grupos no modelo SolicitacaoCidade.

Liberar ou recusar cidade é decisão do Administrador (muda o que o site atende);
Moderador só consulta (vê de onde vêm os cadastros). Ninguém apaga. Idempotente.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMISSOES = {
    "Administrador": ["view_solicitacaocidade", "change_solicitacaocidade"],
    "Moderador": ["view_solicitacaocidade"],
}


def dar_permissoes(apps, schema_editor):
    """Cria as permissões do app (banco novo) e liga cada uma ao grupo."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    app_config = apps.get_app_config("anunciantes")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="anunciantes", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)


class Migration(migrations.Migration):
    dependencies = [
        ("anunciantes", "0003_alter_anunciante_cidade_and_more"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(dar_permissoes, migrations.RunPython.noop)]
