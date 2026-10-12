"""Dados iniciais da cobrança: textos dos e-mails (editáveis no admin), permissões dos grupos e o texto de
"Sobre esta tela" das Faturas. Idempotente (não sobrescreve o que o admin editou)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

ASSINATURA = "\n\nEquipe {site}"

EMAILS = {
    "fatura_disponivel": (
        "Sua fatura {codigo} está disponível",
        "Olá, {loja}!\n\nA fatura do seu plano no {site} está disponível.\n\n"
        "Valor: {valor}\nVencimento: {vencimento}\nPeríodo: {competencia}\nFatura: {codigo}\n\n"
        "Pague pelo Pix (copia e cola ou QR Code) e envie o comprovante em:\n{link}" + ASSINATURA,
    ),
    "lembrete_3_dias": (
        "Sua fatura {codigo} vence em 3 dias",
        "Olá, {loja}!\n\nLembrete: a fatura {codigo}, de {valor}, vence em {vencimento}.\n\n"
        "O Pix copia e cola e o QR Code estão em:\n{link}\n\n"
        "Se já pagou, envie o comprovante pelo botão \"Já paguei\"." + ASSINATURA,
    ),
    "vence_hoje": (
        "Sua fatura {codigo} vence hoje",
        "Olá, {loja}!\n\nA fatura {codigo}, de {valor}, vence hoje ({vencimento}).\n\n"
        "Pague pelo Pix e envie o comprovante em:\n{link}" + ASSINATURA,
    ),
    "vencida_1_dia": (
        "Sua fatura {codigo} venceu ontem",
        "Olá, {loja}!\n\nNão identificamos o pagamento da fatura {codigo}, de {valor}, que venceu em "
        "{vencimento}.\n\nPague pelo Pix e envie o comprovante em:\n{link}\n\n"
        "Passada a carência, os anúncios ficam pausados (nada é apagado) até o pagamento ser confirmado."
        + ASSINATURA,
    ),
    "vencida_3_dias": (
        "Fatura {codigo} em aberto há 3 dias",
        "Olá, {loja}!\n\nA fatura {codigo}, de {valor}, venceu em {vencimento} e continua em aberto.\n\n"
        "Para seus anúncios não serem pausados, pague pelo Pix e envie o comprovante em:\n{link}\n\n"
        "Se já pagou, desconsidere este aviso depois de enviar o comprovante." + ASSINATURA,
    ),
    "pagamento_confirmado": (
        "Pagamento confirmado: fatura {codigo}",
        "Olá, {loja}!\n\nConfirmamos o pagamento de {valor} da fatura {codigo} (período {competencia}).\n\n"
        "Obrigado! Seus anúncios seguem no ar. Histórico em:\n{link}" + ASSINATURA,
    ),
    "comprovante_recusado": (
        "Não confirmamos o pagamento da fatura {codigo}",
        "Olá, {loja}!\n\nNão conseguimos confirmar o pagamento da fatura {codigo}, de {valor}.\n\n"
        "Motivo: {motivo}\n\nConfira e envie outro comprovante em:\n{link}" + ASSINATURA,
    ),
}

# Financeiro e Administrador cuidam da cobrança; Moderador e Comercial não veem faturas (ADMINISTRACAO.md).
_TUDO = [
    "view_fatura",
    "change_fatura",
    "view_modeloemailcobranca",
    "change_modeloemailcobranca",
]
PERMISSOES = {"Administrador": _TUDO, "Financeiro": _TUDO}

TEXTO_AJUDA = (
    "Painel › Faturas",
    [
        "A fatura do próximo período aparece aqui (e chega por e-mail) alguns dias antes do vencimento.",
        "Pague pelo Pix: copie o código \"copia e cola\" ou leia o QR Code no app do banco; o valor já vem preenchido.",
        "Depois de pagar, toque em \"Já paguei\" e envie o comprovante (PDF ou foto). A equipe confere e avisa por e-mail.",
        "Fatura vencida além da carência pausa os anúncios (nada é apagado); eles voltam quando o pagamento é confirmado.",
    ],
)


def criar(apps, schema_editor):
    """Textos dos e-mails, permissões e ajuda, sem sobrescrever o que já existe."""
    ModeloEmailCobranca = apps.get_model("pagamentos", "ModeloEmailCobranca")
    for chave, (assunto, corpo) in EMAILS.items():
        ModeloEmailCobranca.objects.get_or_create(chave=chave, defaults={"assunto": assunto, "corpo": corpo})

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_config = apps.get_app_config("pagamentos")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    for nome, codenames in PERMISSOES.items():
        permissoes = list(Permission.objects.filter(content_type__app_label="pagamentos", codename__in=codenames))
        if len(permissoes) != len(codenames):
            raise RuntimeError(f"Permissões faltando para o grupo {nome}: {codenames}")
        Group.objects.get(name=nome).permissions.add(*permissoes)

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    descricao, itens = TEXTO_AJUDA
    TextoAjuda.objects.get_or_create(chave="faturas", defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("pagamentos", "0001_initial"),
        ("core", "0012_configuracao_fatura_antecedencia_dias_and_more"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
