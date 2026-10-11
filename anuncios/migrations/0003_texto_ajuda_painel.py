"""Atualiza o "Sobre esta tela" do painel para os anúncios de verdade (Sprint 3).

Só troca se o texto ainda for o original da migration core/0004: edição feita no admin é mantida.
"""

from django.db import migrations

ORIGINAL = "\n".join(
    [
        "Aqui você acompanha os dados da sua loja e os seus anúncios.",
        "Anúncios no plano: publicados + em análise. Pausados não contam no limite.",
        'Plano, estatísticas e faturas chegam nas próximas etapas (marcados como "em breve").',
    ]
)
NOVO = "\n".join(
    [
        "Aqui você acompanha o seu plano, os seus anúncios e os dados da loja.",
        "Anúncios no plano: publicados + em análise. Pausados e rascunhos não contam no limite.",
        "Anúncios expiram no prazo do site. Quando aparecer \"Expira em X dias\", clique em Renovar (sem custo).",
        "Excluir tira o anúncio do site e do painel. Estatísticas e faturas chegam nas próximas etapas.",
    ]
)


def atualizar(apps, schema_editor):
    """Troca o texto do painel se ninguém o editou."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    TextoAjuda.objects.filter(chave="painel", texto=ORIGINAL).update(texto=NOVO)


def voltar(apps, schema_editor):
    """Desfaz a troca (só se o texto ainda for o desta migration)."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    TextoAjuda.objects.filter(chave="painel", texto=NOVO).update(texto=ORIGINAL)


class Migration(migrations.Migration):
    dependencies = [("anuncios", "0002_permissoes_e_textos"), ("core", "0004_textos_valores_permissoes")]

    operations = [migrations.RunPython(atualizar, voltar)]
