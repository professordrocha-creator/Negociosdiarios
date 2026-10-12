"""Textos de "Sobre esta tela" da busca de imóveis e de veículos. Idempotente (não sobrescreve o admin)."""

from django.db import migrations

TEXTOS = {
    "busca_imoveis": (
        "Busca de imóveis",
        [
            "Escolha a cidade e use os filtros: a lista se atualiza sozinha.",
            "Busque por palavras, com ou sem acento: \"apartamento centro\", \"chacara\".",
            "Toque no ✕ de um filtro para tirá-lo, ou em \"Limpar tudo\".",
            "Só aparecem imóveis de corretores e imobiliárias verificados.",
        ],
    ),
    "busca_veiculos": (
        "Busca de veículos",
        [
            "Escolha a cidade e use os filtros: a lista se atualiza sozinha.",
            "Escolha a marca para ver os modelos dela. Busque por palavras: \"hilux diesel\".",
            "Toque no ✕ de um filtro para tirá-lo, ou em \"Limpar tudo\".",
            "Só aparecem veículos de lojas com CNPJ verificado.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Cria os textos se ainda não existem."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [("core", "0009_configuracao_aviso_expiracao_dias_and_more")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
