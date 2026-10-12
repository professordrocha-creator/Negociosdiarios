"""Permissões dos grupos no catálogo de veículos. Idempotente.

Administrador pode esconder/mostrar marcas, modelos e versões ("ativo"); os demais só consultam.
Ninguém cria nem apaga (a carga da FIPE é que cria).
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

_VER = ["view_marca", "view_modelo", "view_versao"]
PERMISSOES = {
    "Administrador": _VER + ["change_marca", "change_modelo", "change_versao"],
    "Moderador": _VER,
    "Financeiro": _VER,
    "Comercial": _VER,
}


def dar_permissoes(apps, schema_editor):
    """Cria as permissões do app (banco novo) e liga cada uma ao grupo."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("catalogo")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="catalogo", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial"), ("contas", "0002_grupos_permissao")]

    operations = [migrations.RunPython(dar_permissoes, migrations.RunPython.noop)]
