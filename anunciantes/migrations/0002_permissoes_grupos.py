"""Dá aos grupos as permissões do modelo Anunciante (docs/ADMINISTRACAO.md).

Moderador aprova e suspende anunciantes (precisa de "change"); Administrador também
cadastra; Financeiro e Comercial só consultam. Ninguém apaga (exclusão é lógica).
Idempotente.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMISSOES = {
    "Administrador": ["view_anunciante", "add_anunciante", "change_anunciante", "view_historicalanunciante"],
    "Moderador": ["view_anunciante", "change_anunciante", "view_historicalanunciante"],
    "Financeiro": ["view_anunciante"],
    "Comercial": ["view_anunciante"],
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
        grupo = Group.objects.get(name=nome)
        permissoes = list(Permission.objects.filter(content_type__app_label="anunciantes", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        grupo.permissions.add(*permissoes)


class Migration(migrations.Migration):
    dependencies = [
        ("anunciantes", "0001_initial"),
        ("contas", "0002_grupos_permissao"),
    ]

    # Desfazer não mexe nos grupos (podem ter sido ajustados no admin).
    operations = [migrations.RunPython(dar_permissoes, migrations.RunPython.noop)]
