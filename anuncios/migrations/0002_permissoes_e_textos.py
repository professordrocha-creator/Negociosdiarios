"""Permissões dos grupos nos anúncios e textos de ajuda das telas novas. Idempotente.

Moderar (aprovar/recusar na fila) é do Administrador e do Moderador; Financeiro e Comercial
só consultam. Ninguém cria nem apaga anúncio pelo admin (nascem no painel; exclusão é lógica).
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

_VER = ["view_anuncio", "view_detalheimovel"]
_MODERAR = _VER + ["view_historicalanuncio", "view_anuncioemmoderacao", "change_anuncioemmoderacao"]
PERMISSOES = {"Administrador": _MODERAR, "Moderador": _MODERAR, "Financeiro": _VER, "Comercial": _VER}

TEXTOS = {
    "anuncio_editar": (
        "Painel › Anúncio › Dados",
        [
            "Etapa 1 de 4: o que é o imóvel, o preço e a descrição.",
            "Título curto e direto: tipo, quartos e o principal diferencial.",
            "Na descrição, conte o que a foto não mostra. Não coloque telefone nem link.",
            "Você pode salvar e continuar depois: o anúncio fica como rascunho.",
        ],
    ),
    "anuncio_localizacao": (
        "Painel › Anúncio › Localização",
        [
            "Etapa 2 de 4: cidade, bairro e o ponto no mapa (toque no mapa para marcar).",
            "O endereço é privado: só a equipe vê.",
            "Recomendado: mostrar a localização aproximada (um círculo de cerca de 300 m).",
        ],
    ),
    "anuncio_fotos": (
        "Painel › Anúncio › Fotos",
        [
            "Etapa 3 de 4: envie várias fotos de uma vez. A primeira é a capa.",
            "Arraste para mudar a ordem (ou use as setas).",
            "As fotos são otimizadas e os dados de localização do celular são removidos.",
            "Não fotografe pessoas, documentos nem placas de carro.",
        ],
    ),
    "anuncio_revisao": (
        "Painel › Anúncio › Revisão",
        [
            "Etapa 4 de 4: confira tudo e envie para publicação.",
            "O primeiro anúncio da loja passa pela equipe antes de ir ao ar.",
            "O anúncio fica no ar pelo prazo do site e pode ser renovado com um clique.",
        ],
    ),
    "escolher_anuncios": (
        "Painel › Meu plano › Escolher anúncios",
        [
            "O plano novo permite menos anúncios do que você tem hoje.",
            "Marque os que continuam no ar. Os outros ficam pausados (nada é apagado).",
            "A troca vale quando a equipe aprovar o pedido.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Cria as permissões do app, liga aos grupos e cria os textos que ainda não existem."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("anuncios")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="anuncios", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0001_initial"),
        ("contas", "0002_grupos_permissao"),
        ("core", "0009_configuracao_aviso_expiracao_dias_and_more"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
