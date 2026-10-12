"""Calcula o ponto público dos imóveis que já existem (os novos calculam ao gravar)."""

from django.db import migrations


def calcular(apps, schema_editor):
    """Mesma regra do dia a dia (anuncios/localizacao.py), com os modelos históricos."""
    from anuncios.localizacao import ponto_publico

    DetalheImovel = apps.get_model("anuncios", "DetalheImovel")
    for imovel in DetalheImovel.objects.select_related("anuncio").exclude(ponto=None):
        imovel.ponto_publico = ponto_publico(imovel.anuncio.codigo, imovel.ponto, imovel.exibir_localizacao)
        imovel.save(update_fields=["ponto_publico"])


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0010_detalheimovel_ponto_publico")]

    operations = [migrations.RunPython(calcular, migrations.RunPython.noop)]
