"""Textos de "Sobre esta tela" das páginas públicas do guia (etapa G2). Idempotente: não sobrescreve."""

from django.db import migrations

AJUDAS = {
    "guia_inicio": (
        "Guia de Negócios: escolher a cidade e buscar",
        [
            "Escolha a cidade para ver os tipos de serviço, ou busque pelo nome ou pelo serviço (ex.: eletricista).",
            "A busca entende palavras sem acento e pequenos erros de digitação.",
            "O guia é gratuito para quem procura e para quem aparece nele.",
        ],
    ),
    "guia_cidade": (
        "Guia de Negócios: serviços de uma cidade",
        [
            "Os serviços estão agrupados por área. O número é quantas empresas e profissionais há em cada um.",
            "Toque no serviço para ver a lista e o mapa.",
        ],
    ),
    "guia_categoria": (
        "Guia de Negócios: lista e mapa de um serviço",
        [
            "A ordem muda todo dia, por sorteio: ninguém paga para aparecer primeiro.",
            "\"Aberto agora\" usa o horário informado por cada empresa, no fuso da cidade.",
            "No mapa só aparece quem tem endereço comercial; quem atende a domicílio está na lista.",
            "Fale direto pelo WhatsApp ou veja o telefone. O guia não intermedia o serviço.",
        ],
    ),
    "guia_empresa": (
        "Guia de Negócios: ficha da empresa ou do profissional",
        [
            "Os dados foram autorizados pelo responsável. O guia não intermedia o serviço nem garante preços.",
            "Profissões regulamentadas (saúde, advocacia, contabilidade...) mostram só nome, especialidade, registro e contato.",
            "É o dono? Para alterar ou remover a ficha, escreva para o e-mail de privacidade do site.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Cria os textos que ainda não existem."""
    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in AJUDAS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [("guia", "0003_contatos_por_hora")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
