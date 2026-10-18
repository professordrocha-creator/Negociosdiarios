"""Dados iniciais do guia: grupo "Guia" e permissões (Administrador, Moderador), primeira versão do termo
(RASCUNHO jurídico, docs/GUIA_LGPD_E_TERMO.md §3) e os textos de "Sobre esta tela". Idempotente.

Financeiro e Comercial não recebem nenhuma permissão do guia (docs/GUIA.md §10).
"""

import datetime

from django.contrib.auth.management import create_permissions
from django.db import migrations

VER_CATEGORIAS = ["view_grupocategoria", "view_categoriaservico"]
PERMISSOES = {
    "Guia": [
        *VER_CATEGORIAS,
        "view_perfilguia",
        "add_perfilguia",
        "change_perfilguia",
        "view_termoguia",
        "view_aceitepublicacao",
        "view_conviteaceite",
    ],
    "Moderador": ["view_perfilguia", "view_pedidodoperfil", "change_pedidodoperfil"],
    "Administrador": [
        *VER_CATEGORIAS,
        "add_grupocategoria",
        "change_grupocategoria",
        "delete_grupocategoria",
        "add_categoriaservico",
        "change_categoriaservico",
        "delete_categoriaservico",
        "view_perfilguia",
        "add_perfilguia",
        "change_perfilguia",
        "view_termoguia",
        "add_termoguia",
        "change_termoguia",
        "view_aceitepublicacao",
        "view_conviteaceite",
        "view_pedidodoperfil",
        "change_pedidodoperfil",
        "view_configuracaoguia",
        "change_configuracaoguia",
    ],
}

TERMO = """## 1. Quem somos
O {nome_guia} é um serviço gratuito do Negócios Diários, mantido por {empresa} ({documento}), em {cidade_sede}. Contato do Encarregado de dados: {email_encarregado}.

## 2. O que será publicado
Com a sua autorização, publicaremos no site: nome público, categoria(s), telefone e WhatsApp de contato, endereço comercial ou área de atendimento, horário de funcionamento, logomarca e frase de apresentação, exatamente como mostrado na prévia desta página. Se for profissional de área regulamentada, também o número de registro.

## 3. O que NÃO será publicado
Seu CPF, seu endereço residencial (se atender em casa) e qualquer outro dado que não esteja na prévia.

## 4. Gratuidade
A publicação é gratuita. Não há cobrança nem obrigação de contratar outro serviço. Podemos, no futuro, oferecer recursos pagos opcionais; nenhum será ativado sem o seu pedido.

## 5. Seus direitos
Você pode, a qualquer momento, pedir alteração ou remoção da publicação, ou revogar esta autorização, pelo link "Esta é minha empresa" na sua ficha ou pelo e-mail do Encarregado. Atendemos o pedido o mais rápido possível e, no máximo, em 15 dias. Revogar não gera multa nem prejuízo.

## 6. Seus dados no nosso sistema
Guardamos o registro desta autorização (nome digitado, data, hora e versão) pelo tempo necessário para comprovar que você autorizou. Os demais dados são apagados quando a publicação for removida.

## 7. Responsabilidade
Você declara ser o responsável pelo negócio ou profissional indicado e que as informações são verdadeiras. Você é responsável pelo conteúdo informado. Podemos pausar ou remover fichas com informações falsas ou que violem a lei.

## 8. Alterações deste termo
Se mudarmos o termo, pediremos uma nova autorização. Sem ela, a ficha poderá ser pausada."""

AJUDAS = {
    "guia_aceite": (
        "Guia de Negócios: autorizar publicação (link enviado pela equipe)",
        [
            "Confira a prévia: é exatamente o que vai aparecer no site. Seu CPF e endereço de casa nunca aparecem.",
            "Leia o termo, digite seu nome completo e marque \"Autorizo\". A publicação é gratuita.",
            "Você pode pedir alteração, remoção ou revogar a autorização quando quiser, sem custo.",
        ],
    ),
    "guia_cadastro": (
        "Admin do guia: cadastro assistido de empresa ou profissional",
        [
            "Preencha na ordem: quem é, contato, onde atende e horário. Salve: o perfil fica como rascunho.",
            "Quem atende em casa ou na casa do cliente: \"a domicílio\" com a área de atendimento (nunca o endereço de casa).",
            "Profissão regulamentada (categoria com *): sem frase; informe o registro do conselho.",
            "Com o cadastro completo, toque em \"Enviar por WhatsApp\": o responsável confere a prévia e autoriza; aí publica sozinho.",
            "Sem internet do responsável? Use \"Aceite em papel\": foto do termo assinado (fica em área privada).",
            "CPF não é guardado: fica só um resumo para achar cadastro repetido. Aviso de repetido não bloqueia: você decide.",
        ],
    ),
}


def criar(apps, schema_editor):
    """Grupo, permissões, termo inicial e textos de ajuda, sem sobrescrever o que já existe."""
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
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupo.permissions.add(*permissoes)

    TermoGuia = apps.get_model("guia", "TermoGuia")
    if not TermoGuia.objects.exists():
        TermoGuia.objects.create(
            versao="2026-10", texto=TERMO, vigente_desde=datetime.date(2026, 10, 18), rascunho_juridico=True
        )

    TextoAjuda = apps.get_model("core", "TextoAjuda")
    for chave, (descricao, itens) in AJUDAS.items():
        TextoAjuda.objects.get_or_create(chave=chave, defaults={"descricao": descricao, "texto": "\n".join(itens)})


class Migration(migrations.Migration):
    dependencies = [
        ("guia", "0001_inicial"),
        ("core", "0018_frase_rodape_e_cnpj"),
        ("contas", "0002_grupos_permissao"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
