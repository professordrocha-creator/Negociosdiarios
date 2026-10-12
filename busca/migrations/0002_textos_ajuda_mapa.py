"""Sprint 5: acrescenta o mapa aos textos de "Sobre esta tela" da busca. Não sobrescreve o que o admin
editou: só acrescenta a linha se o texto ainda não fala do mapa."""

from django.db import migrations

LINHAS = {
    "busca_imoveis": (
        'No celular, toque em "Mapa"; no computador, o mapa fica ao lado. Mova o mapa e toque em '
        '"Buscar nesta área". Localização aproximada aparece deslocada, para proteger o endereço.'
    ),
    "busca_veiculos": (
        'No celular, toque em "Mapa"; no computador, o mapa fica ao lado. O mapa mostra as lojas que '
        'divulgam o endereço; mova o mapa e toque em "Buscar nesta área".'
    ),
}


def acrescentar(apps, schema_editor):
    """Acrescenta a linha do mapa onde ainda não há menção ao mapa."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, linha in LINHAS.items():
        texto = TextoAjuda.objects.filter(chave=chave).first()
        if texto is not None and "mapa" not in texto.texto.lower():
            texto.texto = texto.texto.rstrip("\n") + "\n" + linha
            texto.save(update_fields=["texto"])


class Migration(migrations.Migration):
    dependencies = [("busca", "0001_textos_ajuda")]

    operations = [migrations.RunPython(acrescentar, migrations.RunPython.noop)]
