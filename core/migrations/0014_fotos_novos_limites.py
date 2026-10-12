"""Fotos de anúncio mais fáceis: a Configuracao que ainda tem os padrões antigos passa aos novos.

Antes: mínimo 800×600 recusado e limite de 8 MB. Agora: mínimo aceito 200×150 (só recusa ícone), aviso
abaixo de 800×600 e 15 MB de rede de segurança (o navegador reduz antes de enviar). Valor mudado no admin
não é tocado.
"""

from django.db import migrations

ANTIGOS = {"limite_foto_anuncio_kb": 8192, "foto_min_largura_px": 800, "foto_min_altura_px": 600}
NOVOS = {"limite_foto_anuncio_kb": 15360, "foto_min_largura_px": 200, "foto_min_altura_px": 150}


def atualizar(apps, schema_editor):
    """Troca campo a campo, só onde ainda está o padrão antigo."""
    Configuracao = apps.get_model("core", "Configuracao")
    for campo, antigo in ANTIGOS.items():
        Configuracao.objects.filter(**{campo: antigo}).update(**{campo: NOVOS[campo]})


class Migration(migrations.Migration):
    dependencies = [("core", "0013_configuracao_foto_aviso_altura_px_and_more")]

    operations = [migrations.RunPython(atualizar, migrations.RunPython.noop)]
