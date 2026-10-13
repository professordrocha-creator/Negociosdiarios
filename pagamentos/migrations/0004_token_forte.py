"""Token do link público de pagamento mais forte: 32 bytes do `secrets` em vez do UUID4. Toda fatura ganha
um token novo (os links antigos de UUID deixam de abrir)."""

import pagamentos.models
from django.db import migrations, models


def novos_tokens(apps, schema_editor):
    """Troca o token de cada fatura por um de 32 bytes aleatórios."""
    import secrets

    Fatura = apps.get_model("pagamentos", "Fatura")
    for pk in Fatura.objects.values_list("pk", flat=True):
        Fatura.objects.filter(pk=pk).update(token=secrets.token_urlsafe(32))


class Migration(migrations.Migration):

    dependencies = [
        ('pagamentos', '0003_fatura_campanha_fatura_token_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fatura',
            name='token',
            field=models.CharField(default=pagamentos.models.gerar_token, editable=False, max_length=64, unique=True, verbose_name='token do link de pagamento'),
        ),
        migrations.AlterField(
            model_name='historicalfatura',
            name='token',
            field=models.CharField(db_index=True, default=pagamentos.models.gerar_token, editable=False, max_length=64, verbose_name='token do link de pagamento'),
        ),
        migrations.RunPython(novos_tokens, migrations.RunPython.noop),
    ]
