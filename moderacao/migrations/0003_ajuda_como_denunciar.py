"""Texto de "Sobre esta tela" da página "Como denunciar" (link do rodapé). Idempotente."""

from django.db import migrations

AJUDA = (
    "Como denunciar (rodapé)",
    [
        'A denúncia é feita pelo botão "Denunciar" dentro de cada anúncio: assim já vai junto o anúncio certo.',
        "A equipe analisa e pode pausar ou remover o anúncio. Quem denunciou nunca é revelado ao anunciante.",
    ],
)


def criar(apps, schema_editor):
    """Cria o texto se ainda não existe."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    descricao, itens = AJUDA
    TextoAjuda.objects.get_or_create(chave="como_denunciar", defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [("moderacao", "0002_dados_iniciais")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
