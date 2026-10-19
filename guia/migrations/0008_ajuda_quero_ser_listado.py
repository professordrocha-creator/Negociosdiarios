"""Texto de "Sobre esta tela" da página "Quero ser listado" (/guia/quero-ser-listado/). Idempotente."""

from django.db import migrations

ITENS = [
    "Mande os dados da sua empresa ou serviço. Nada é publicado agora.",
    "A equipe entra em contato pelo WhatsApp informado, monta a ficha e manda um link para você conferir.",
    "A ficha só vai ao ar depois que você autorizar pelo link. Estar no guia é grátis.",
    "Não pedimos CPF nem endereço de casa.",
]


def criar(apps, schema_editor):
    """Cria o texto se ainda não existe (não sobrescreve o que foi editado no admin)."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    TextoAjuda.objects.get_or_create(
        chave="guia_quero_ser_listado",
        defaults={"descricao": "Guia de Negócios: Quero ser listado", "texto": "\n".join(ITENS)},
    )


class Migration(migrations.Migration):
    dependencies = [("guia", "0007_quero_ser_listado")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
