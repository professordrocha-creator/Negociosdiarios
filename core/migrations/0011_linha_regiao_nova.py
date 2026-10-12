"""Linha da região padrão nova: "Imóveis, veículos e serviços de MT" (marca final, 2026-10-12).

Só troca se ainda for o texto padrão antigo; o que foi editado no admin fica como está.
"""

from django.db import migrations

ANTIGA = "Imóveis e veículos de Mato Grosso"
NOVA = "Imóveis, veículos e serviços de MT"


def trocar(apps, schema_editor):
    """Antiga → nova."""
    apps.get_model("core", "Configuracao").objects.filter(linha_regiao=ANTIGA).update(linha_regiao=NOVA)


def desfazer(apps, schema_editor):
    """Nova → antiga."""
    apps.get_model("core", "Configuracao").objects.filter(linha_regiao=NOVA).update(linha_regiao=ANTIGA)


class Migration(migrations.Migration):
    dependencies = [("core", "0010_logo_completo")]

    operations = [migrations.RunPython(trocar, desfazer)]
