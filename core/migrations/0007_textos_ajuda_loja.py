"""Textos de ajuda das telas da Sprint 2, parte A: Painel › Página da loja e /lojas/. Idempotente."""

from django.db import migrations

TEXTOS = {
    "painel_loja": (
        "Painel › Página da loja",
        [
            "Esta é a vitrine da sua empresa no site. Tudo aqui aparece para os visitantes.",
            "Logo: quadrado (recortamos pelo centro), em PNG, JPG ou WebP. Aparece na loja e nas listas.",
            "Capa: proporção 4:1 (ideal 1600×400). Evite texto nas bordas: no celular elas são cortadas.",
            "As imagens são convertidas e otimizadas; dados de localização das fotos são removidos.",
            "CRECI e CNPJ não podem ser alterados aqui porque passaram por verificação.",
        ],
    ),
    "lojas": (
        "Lista de lojas (/lojas/)",
        [
            "Só aparecem lojas aprovadas, com CRECI ou CNPJ conferido pela equipe.",
            "Filtre por tipo de loja e por cidade.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Cria os textos se ainda não existem (não sobrescreve edições do admin)."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [("core", "0006_pagina_da_loja")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
