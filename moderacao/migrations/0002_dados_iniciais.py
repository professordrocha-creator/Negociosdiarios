"""Permissões das denúncias (Moderador e Administrador decidem; os outros grupos não veem) e o texto de
"Sobre esta tela" do formulário público. Idempotente."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMISSOES = {"Administrador": ["view_denuncia", "change_denuncia"], "Moderador": ["view_denuncia", "change_denuncia"]}

AJUDA = (
    "Denunciar anúncio",
    [
        "Viu golpe, anúncio já vendido, preço ou dados falsos, conteúdo impróprio ou dados de outras pessoas? Avise aqui.",
        "Não precisa de cadastro. O e-mail é opcional (só para dar retorno) e o anunciante nunca sabe quem denunciou.",
        "A equipe analisa cada denúncia. Várias denúncias de golpe tiram o anúncio do ar até a revisão.",
    ],
)


def criar(apps, schema_editor):
    """Permissões e texto de ajuda, sem sobrescrever o que já existe."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("moderacao")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="moderacao", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    descricao, itens = AJUDA
    TextoAjuda.objects.get_or_create(chave="denunciar", defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("moderacao", "0001_initial"),
        ("core", "0017_configuracao_denuncias_golpe_para_pausar_and_more"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
