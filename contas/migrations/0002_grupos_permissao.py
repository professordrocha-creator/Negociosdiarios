"""Cria os grupos de permissão da equipe (docs/ADMINISTRACAO.md).

Só com permissões de modelos que já existem. Quando um modelo novo surgir
(anunciante, anúncio, fatura...), a migration dele acrescenta as permissões
ao grupo certo. Idempotente: rodar de novo não duplica nada.

De propósito, nenhum grupo recebe:
- `delete_usuario`: ninguém é apagado de verdade (exclusão lógica);
- permissões dos códigos de acesso (`otp_email`, `otp_static`): quem mexe no
  código de outra pessoa consegue entrar como ela. Só o superusuário gerencia.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

# grupo -> lista de (app, modelo, ações)
GRUPOS = {
    "Administrador": [
        ("contas", "usuario", ["view", "add", "change"]),
        ("auth", "group", ["view"]),
        ("core", "estado", ["view", "change"]),
        ("core", "cidade", ["view", "change"]),
        ("axes", "accessattempt", ["view", "delete"]),  # ver e apagar = desbloquear login pelo admin
        ("admin", "logentry", ["view"]),  # histórico de ações no admin
    ],
    # Os três abaixo só consultam as cidades por enquanto; o trabalho deles chega com os
    # modelos de anunciante/anúncio (Moderador), fatura (Financeiro) e publicidade (Comercial).
    "Moderador": [
        ("core", "estado", ["view"]),
        ("core", "cidade", ["view"]),
    ],
    "Financeiro": [
        ("core", "estado", ["view"]),
        ("core", "cidade", ["view"]),
    ],
    "Comercial": [
        ("core", "estado", ["view"]),
        ("core", "cidade", ["view"]),
    ],
}


def criar_grupos(apps, schema_editor):
    """Cria os grupos e liga as permissões. Falha se alguma permissão esperada não existir."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    # Em banco novo as permissões só nascem no fim do migrate (sinal post_migrate).
    # Criá-las aqui garante que existam quando os grupos forem montados.
    for rotulo in {app for regras in GRUPOS.values() for app, _, _ in regras}:
        app_config = apps.get_app_config(rotulo)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    for nome, regras in GRUPOS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        for app, modelo, acoes in regras:
            codenames = [f"{acao}_{modelo}" for acao in acoes]
            permissoes = list(
                Permission.objects.filter(
                    content_type__app_label=app, content_type__model=modelo, codename__in=codenames
                )
            )
            if len(permissoes) != len(codenames):
                raise RuntimeError(f"Permissões faltando para {app}.{modelo}: {codenames}")
            grupo.permissions.add(*permissoes)


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0001_initial"),
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("axes", "0010_accessattemptexpiration"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    # Desfazer não apaga os grupos: podem já ter pessoas e permissões ajustadas no admin.
    operations = [migrations.RunPython(criar_grupos, migrations.RunPython.noop)]
