"""Testes da captação do guia: cartão da home logo abaixo da busca, faixa "Quero ser listado" nas páginas do
guia, o formulário /guia/quero-ser-listado/ (não publica nada; honeypot, CSRF, limite por hora, telefone
validado, "não contatar"), a fila no admin (criar ficha, marcar contatado, contador nas pendências) e a
limpeza dos interessados que não viraram ficha depois de 180 dias."""

from datetime import timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from guia import services
from guia.models import ContatoConvite, PerfilGuia

pytestmark = pytest.mark.django_db

PESSOA = {"HTTP_USER_AGENT": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile Safari/537.36"}
URL = "/guia/quero-ser-listado/"


def dados(tangara, categorias, **extra) -> dict:
    """Envio válido do "Quero ser listado"."""
    return {
        "nome": "Vidraçaria Nova Era",
        "categoria": categorias["vidraceiro-e-vidracaria"].pk,
        "cidade": tangara.pk,
        "whatsapp": "(65) 99999-0707",
        "responsavel_nome": "Marta Souza",
        "autorizo": "on",
        "site_empresa": "",
        **extra,
    }


# --- Home e faixa -----------------------------------------------------------------------------------------


def test_cartao_da_home_abaixo_da_busca_com_atalhos(client, guia_ligado, categorias, perfil_publicado):
    """Guia no ar: cartão logo depois da caixa de busca (antes dos atalhos de imóveis), com o botão e 4
    atalhos; a categoria com mais fichas vem primeiro e as outras completam com as padrão."""
    perfil_publicado()  # eletricista
    pagina = client.get("/", **PESSOA).content.decode()

    busca, cartao, atalhos = (
        pagina.index('class="nd-busca'),
        pagina.index("nd-cartao-guia-home"),
        pagina.index('class="nd-atalhos"'),
    )
    assert busca < cartao < atalhos
    assert "Encontre serviços e comércios da sua cidade. Grátis." in pagina
    trecho = pagina[cartao:atalhos]
    assert trecho.count('class="nd-atalho"') == 4
    assert trecho.index("Eletricista") < trecho.index("Farmácia")
    assert "/guia/?q=Eletricista" in trecho


def test_sem_guia_no_ar_nao_ha_cartao(client, categorias):
    """Guia desligado: nada na home."""
    assert "nd-cartao-guia-home" not in client.get("/", **PESSOA).content.decode()


def test_atalhos_padrao_sem_fichas(categorias, guia_ligado):
    """Sem fichas publicadas: farmácia, eletricista, mecânica e salão."""
    assert [c.slug for c in services.categorias_populares()] == services.CATEGORIAS_PADRAO_HOME


def test_faixa_quero_ser_listado_nas_paginas_do_guia(client, guia_ligado, tangara, categorias):
    """Início, cidade e categoria vazia têm a faixa (texto editável) com o botão; nunca "Anuncie"."""
    guia_ligado.texto_quero_ser_listado = "Texto da faixa editado."
    guia_ligado.save()
    for url in ("/guia/", "/guia/mt/tangara-da-serra/", "/guia/mt/tangara-da-serra/eletricista/"):
        pagina = client.get(url, **PESSOA).content.decode()
        assert "Texto da faixa editado." in pagina and f'href="{URL}"' in pagina, url
        assert pagina.count("nd-faixa-listado") == 1, url
        assert "Anuncie" not in pagina.split("nd-faixa-listado")[1].split("</aside>")[0]


# --- Formulário -------------------------------------------------------------------------------------------


def test_pedido_entra_na_fila_sem_publicar_nada(client, guia_ligado, tangara, categorias):
    """Vira contato de convite (formulário do site, novo, com a data da autorização); nenhum perfil nasce."""
    pagina = client.get(URL, **PESSOA).content.decode()
    assert "Agora nada é publicado" in pagina and "autoriza" in pagina

    resposta = client.post(URL, dados(tangara, categorias), **PESSOA)

    assert resposta.status_code == 200 and "Recebemos o seu pedido" in resposta.content.decode()
    contato = ContatoConvite.objects.get()
    assert contato.origem == "formulario" and contato.situacao == "novo"
    assert contato.whatsapp == "+5565999990707" and contato.responsavel_nome == "Marta Souza"
    assert contato.autorizou_contato_em is not None
    assert not PerfilGuia.objects.exists()


def test_validacoes_autorizo_telefone_honeypot_csrf(client, guia_ligado, tangara, categorias):
    """Sem a caixa de autorização ou com telefone inválido: 400. Robô: sucesso sem gravar. Sem CSRF: 403."""
    assert client.post(URL, dados(tangara, categorias, autorizo=""), **PESSOA).status_code == 400
    invalido = client.post(URL, dados(tangara, categorias, whatsapp="123"), **PESSOA)
    assert invalido.status_code == 400 and "WhatsApp inválido" in invalido.content.decode()
    assert client.post(URL, dados(tangara, categorias, site_empresa="x"), **PESSOA).status_code == 200
    assert Client(enforce_csrf_checks=True).post(URL, dados(tangara, categorias)).status_code == 403
    assert not ContatoConvite.objects.exists()


def test_limite_por_hora_sem_ip(client, guia_ligado, tangara, categorias):
    """Passou do limite da configuração: 429 (contador pelo resumo anônimo do visitante)."""
    guia_ligado.interessados_por_hora = 2
    guia_ligado.save()
    codigos = [
        client.post(URL, dados(tangara, categorias, whatsapp=f"(65) 99999-07{i:02d}"), **PESSOA).status_code
        for i in range(3)
    ]
    assert codigos == [200, 200, 429] and ContatoConvite.objects.count() == 2


def test_guia_desligado_da_404(client, tangara, categorias):
    """Com o guia fora do ar, a página não existe para o público."""
    assert client.get(URL, **PESSOA).status_code == 404


def test_numero_nao_contatar_registra_sem_acao_e_avisa(client, guia_ligado, tangara, categorias, membro):
    """Número na lista "não contatar": o pedido fica registrado com o alerta, a equipe recebe e-mail e o
    convite e a ficha continuam bloqueados."""
    membro("Guia")
    ContatoConvite.objects.create(
        nome="Antigo",
        whatsapp="+5565999990707",
        cidade=tangara,
        situacao=ContatoConvite.Situacao.NAO_CONTATAR,
    )
    mail.outbox.clear()

    client.post(URL, dados(tangara, categorias), **PESSOA)

    novo = ContatoConvite.objects.get(origem="formulario")
    assert "não contatar" in novo.observacao
    assert mail.outbox and "bloqueado" in mail.outbox[0].subject and mail.outbox[0].to == ["guia@exemplo.com"]
    with pytest.raises(ValueError):
        services.criar_perfil_do_contato(novo)


# --- Admin ----------------------------------------------------------------------------------------------


def test_admin_cria_ficha_preenchida_e_marca_contatado(admin_guia, guia_ligado, tangara, categorias):
    """ "Criar ficha a partir deste contato" abre o cadastro assistido já preenchido (rascunho, cadastro
    assistido); "Marcar como contatado" grava a situação e a data."""
    contato = services.registrar_interessado(
        "Vidraçaria Nova Era", categorias["vidraceiro-e-vidracaria"], tangara, "+5565999990707", "Marta Souza"
    )
    lista = reverse("admin:guia_contatoconvite_changelist")

    admin_guia.post(lista, {"action": "marcar_contatado", ACTION_CHECKBOX_NAME: [contato.pk]})
    contato.refresh_from_db()
    assert contato.situacao == "contatado" and contato.convidado_em

    resposta = admin_guia.post(lista, {"action": "criar_ficha", ACTION_CHECKBOX_NAME: [contato.pk]})
    contato.refresh_from_db()
    perfil = contato.perfil
    assert resposta.status_code == 302 and resposta["Location"].endswith(f"/{perfil.pk}/change/")
    assert perfil.status == "rascunho" and perfil.origem == "cadastro_assistido"
    assert perfil.responsavel_nome == "Marta Souza" and perfil.whatsapp == "+5565999990707"
    assert list(perfil.categorias.values_list("slug", flat=True)) == ["vidraceiro-e-vidracaria"]


def test_contador_interessados_no_painel(entrar_no_admin, membro, tangara, categorias):
    """O grupo Guia vê "Interessados no Guia" com o número dos novos; o Financeiro não vê."""
    services.registrar_interessado("A", None, tangara, "+5565999990701", "Ana")
    pagina = entrar_no_admin(membro("Guia")).get(reverse("admin:index")).content.decode()
    assert '<b class="nd-pendencia-numero">1</b> Interessados no Guia' in pagina
    assert "origem__exact=formulario" in pagina


# --- LGPD: 180 dias ---------------------------------------------------------------------------------------


def test_interessados_sem_ficha_saem_depois_de_180_dias(tangara, categorias, perfil_publicado):
    """Rotina diária: some o interessado antigo sem ficha (e o histórico); ficam o que virou ficha, o
    bloqueado, o recente e os da lista antiga."""
    antigo = timezone.now() - timedelta(days=181)
    velho = services.registrar_interessado("Velho", None, tangara, "+5565999990711", "V")
    com_ficha = services.registrar_interessado("Ficha", None, tangara, "+5565999990712", "F")
    bloqueado = services.registrar_interessado("Bloq", None, tangara, "+5565999990713", "B")
    services.marcar_contato(bloqueado, ContatoConvite.Situacao.NAO_CONTATAR)
    lista = ContatoConvite.objects.create(nome="Lista", whatsapp="+5565999990714", cidade=tangara)
    recente = services.registrar_interessado("Recente", None, tangara, "+5565999990715", "R")
    perfil = perfil_publicado(whatsapp="+5565999990799")
    ContatoConvite.objects.filter(pk=com_ficha.pk).update(perfil=perfil)
    ContatoConvite.objects.exclude(pk=recente.pk).update(criado_em=antigo)

    resumo = services.rotina_do_guia()

    assert resumo["interessados_apagados"] == 1
    restantes = set(ContatoConvite.objects.values_list("pk", flat=True))
    assert restantes == {com_ficha.pk, bloqueado.pk, lista.pk, recente.pk}
    assert not ContatoConvite.history.filter(id=velho.pk).exists()
