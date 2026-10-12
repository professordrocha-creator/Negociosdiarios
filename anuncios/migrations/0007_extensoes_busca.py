"""Extensões do PostgreSQL para a busca (Sprint 4B) e a configuração de texto "pt_unaccent".

- unaccent: "tangara" acha "Tangará" (e vice-versa);
- pg_trgm: semelhança de palavras (erros de digitação, "hilu" acha "Hilux");
- pt_unaccent: português (radicais: "casas" acha "casa") sem acento.

Em produção, o usuário do banco precisa poder criar extensões (ou um admin cria antes: docs/RUNBOOK.md).
"""

from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations

CRIAR = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'pt_unaccent') THEN
        CREATE TEXT SEARCH CONFIGURATION pt_unaccent (COPY = portuguese);
        ALTER TEXT SEARCH CONFIGURATION pt_unaccent
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, portuguese_stem;
    END IF;
END
$$;
"""
APAGAR = "DROP TEXT SEARCH CONFIGURATION IF EXISTS pt_unaccent;"


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0006_veiculo_permissoes_e_textos")]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
        migrations.RunSQL(CRIAR, APAGAR),
    ]
