"""Fatura de campanha de publicidade (Sprint 7A): assinatura opcional, campanha, token do link público
(preenchido com um UUID diferente para cada fatura que já existe, depois único)."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def preencher_tokens(apps, schema_editor):
    """Um token aleatório por fatura existente (o default só vale para as novas)."""
    Fatura = apps.get_model("pagamentos", "Fatura")
    for fatura in Fatura.objects.filter(token__isnull=True).only("pk"):
        Fatura.objects.filter(pk=fatura.pk).update(token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('pagamentos', '0002_dados_iniciais'),
        ('planos', '0003_pedidotrocaplano_anuncios_manter'),
        ('publicidade', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='fatura',
            name='campanha',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='faturas', to='publicidade.campanha', verbose_name='campanha de publicidade'),
        ),
        migrations.AddField(
            model_name='fatura',
            name='token',
            field=models.UUIDField(editable=False, null=True, verbose_name='token do link de pagamento'),
        ),
        migrations.AddField(
            model_name='historicalfatura',
            name='campanha',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='publicidade.campanha', verbose_name='campanha de publicidade'),
        ),
        migrations.AddField(
            model_name='historicalfatura',
            name='token',
            field=models.UUIDField(editable=False, null=True, verbose_name='token do link de pagamento'),
        ),
        migrations.AlterField(
            model_name='fatura',
            name='assinatura',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='faturas', to='planos.assinatura', verbose_name='assinatura'),
        ),
        migrations.RunPython(preencher_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='fatura',
            name='token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='token do link de pagamento'),
        ),
        migrations.AlterField(
            model_name='historicalfatura',
            name='token',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, verbose_name='token do link de pagamento'),
        ),
        migrations.AddConstraint(
            model_name='fatura',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('assinatura__isnull', False), ('campanha__isnull', True)), models.Q(('assinatura__isnull', True), ('campanha__isnull', False)), _connector='OR'), name='fatura_de_assinatura_ou_campanha'),
        ),
    ]
