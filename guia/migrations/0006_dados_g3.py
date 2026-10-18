"""Dados da etapa G3: estabelecimentos regulados (mostram horário), permissões da lista de convites e textos
de "Sobre esta tela". Idempotente; não sobrescreve textos já editados."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

ESTABELECIMENTOS = ["farmacia", "clinica-e-laboratorio", "hospital-e-pronto-atendimento", "veterinario"]
CONVITES = ["view_contatoconvite", "add_contatoconvite", "change_contatoconvite"]
PERMISSOES = {
    "Guia": CONVITES,
    "Administrador": [*CONVITES, "add_pedidodoperfil"],
    "Moderador": ["add_pedidodoperfil"],  # pedido que chega por e-mail ou WhatsApp, registrado pela equipe
}

ITEM_ANTIGO_EMPRESA = "É o dono? Para alterar ou remover a ficha, escreva para o e-mail de privacidade do site."
ITEM_NOVO_EMPRESA = 'É o dono? Use o link "Esta é minha empresa" para pedir alteração ou remoção da ficha.'

AJUDAS = {
    "guia_pedido": (
        "Guia de Negócios: pedido do titular (\"Esta é minha empresa\")",
        [
            "Peça para alterar dados, remover a ficha ou outro assunto. Não precisa de cadastro.",
            "Informe um contato para a resposta (e-mail ou telefone). Ele só é usado para responder este pedido.",
            "Respondemos em até 15 dias. Pedidos de remoção feitos pelo contato cadastrado podem ser atendidos na hora.",
        ],
    ),
    "guia_termo_pendentes": (
        "Admin do guia: quem ainda não aceitou o termo vigente",
        [
            "Perfis publicados que ainda não aceitaram a versão em vigor do termo, com os dias que faltam.",
            "Abra o perfil e use \"Enviar por WhatsApp\" para mandar o link. Passado o prazo, a rotina diária pausa o perfil.",
        ],
    ),
    "guia_importar": (
        "Admin do guia: importar lista de convites",
        [
            "CSV com as colunas nome, whatsapp, cidade, categoria (categoria pode ficar vazia).",
            "Primeiro vem a prévia com os erros por linha; só as linhas certas são importadas.",
            "Números que recusaram ou pediram para não ser contatados ficam de fora.",
        ],
    ),
    "guia_estatisticas": (
        "Admin do guia: estatísticas",
        [
            "Visualizações das fichas e cliques no WhatsApp e no telefone, sem dado pessoal (robôs não contam).",
            "Troque o período entre 7 e 30 dias. Exportar CSV baixa a mesma tabela.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Marca os estabelecimentos, dá as permissões e cria os textos que faltam."""
    CategoriaServico = apps.get_model("guia", "CategoriaServico")
    CategoriaServico.objects.filter(slug__in=ESTABELECIMENTOS).update(estabelecimento=True)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("guia")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="guia", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    # A ficha passou a ter o link "Esta é minha empresa": troca o item provisório da G2 (só se não foi editado).
    for ajuda in TextoAjuda.objects.filter(chave="guia_empresa"):
        ajuda.texto = ajuda.texto.replace(ITEM_ANTIGO_EMPRESA, ITEM_NOVO_EMPRESA)
        ajuda.save(update_fields=["texto"])
    for chave, (descricao, itens) in AJUDAS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [("guia", "0005_g3_operacao")]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
