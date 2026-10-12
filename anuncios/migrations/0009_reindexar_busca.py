"""Preenche o índice de busca dos anúncios que já existem (os novos são indexados ao gravar)."""

from django.db import migrations


def reindexar(apps, schema_editor):
    """Usa o código atual do índice (`anuncios.indice`): a regra é a mesma do dia a dia."""
    from anuncios import indice

    indice.reindexar_todos()


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0008_busca_e_indices")]

    operations = [migrations.RunPython(reindexar, migrations.RunPython.noop)]
