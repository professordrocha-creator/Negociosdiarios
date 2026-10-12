"""Permissões da publicidade e os textos de "Sobre esta tela" (painel do admin e página pública da fatura).
Idempotente (não sobrescreve o que o admin editou)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

# Comercial vende e cadastra; Administrador também; Financeiro só consulta (cobra pela fatura); Moderador nada.
_TUDO = [
    "view_patrocinador",
    "add_patrocinador",
    "change_patrocinador",
    "view_campanha",
    "add_campanha",
    "change_campanha",
    "view_banner",
    "add_banner",
    "change_banner",
]
_VER = ["view_patrocinador", "view_campanha"]
PERMISSOES = {"Administrador": _TUDO, "Comercial": _TUDO, "Financeiro": _VER}

TEXTOS = {
    "admin_publicidade": (
        "Admin › Publicidade › Painel",
        [
            "Campanhas no ar hoje, as que terminam em breve (aviso por e-mail X dias antes, na Identidade do site) e "
            "os números do período escolhido.",
            "Impressões e cliques são contados por dia, sem IP e sem cookie; robôs não contam. CTR = cliques ÷ impressões.",
            "Exportar CSV abre no Excel (separador ponto e vírgula). Use no relatório mensal do patrocinador.",
            "Para cobrar: na lista de campanhas, selecione e use \"Gerar fatura (Pix)\"; o patrocinador recebe o link "
            "de pagamento por e-mail e a confirmação é feita em Cobrança › Faturas.",
        ],
    ),
    "fatura_publica": (
        "Fatura de publicidade (link enviado ao patrocinador)",
        [
            "Pague pelo Pix: copie o código \"copia e cola\" ou leia o QR Code no app do banco; o valor já vem preenchido.",
            "Depois de pagar, toque em \"Já paguei\" e envie o comprovante (PDF ou foto). A equipe confere e avisa por e-mail.",
            "Este link é pessoal: não compartilhe.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Permissões dos grupos e textos de ajuda, sem sobrescrever o que já existe."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("publicidade")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="publicidade", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in TEXTOS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("publicidade", "0001_initial"),
        ("core", "0015_configuracao_banner_altura_px_and_more"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
