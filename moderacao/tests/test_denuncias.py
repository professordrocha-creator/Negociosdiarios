"""Testes das denúncias de anúncio (Sprint 7B parte 2): formulário sem login, honeypot, limite por dia sem IP,
pausa automática por golpe de origens diferentes, fila no admin (aceitar pausando/removendo, descartar) com
histórico, anunciante nunca sabe quem denunciou, guarda do contato e demonstração."""

from datetime import timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from anunciantes.tests.conftest import SENHA
from anuncios import services as anuncios
from anuncios.models import Anuncio
from contas.models import Usuario
from core.services import configuracao
from moderacao import services
from moderacao.models import Denuncia

pytestmark = pytest.mark.django_db

Situacao = Anuncio.Situacao


def navegador(n: int = 1) -> dict:
    """Cabeçalhos de um visitante (n muda o IP: origem diferente)."""
    return {"HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": f"10.0.0.{n}"}


def enviar(client, anuncio, motivo="golpe", n=1, **extra):
    """Envia o formulário de denúncia como o visitante n."""
    dados = {"anuncio": anuncio.codigo, "motivo": motivo, "texto": "", "email": "", **extra}
    return client.post(reverse("moderacao:denunciar"), dados, **navegador(n))


@pytest.fixture
def anuncio(loja, publicado):
    """Anúncio publicado de uma loja."""
    return publicado(loja())


@pytest.fixture
def moderador(db):
    """Membro do grupo Moderador."""
    usuario = Usuario.objects.create_user(email="mod@exemplo.com", password=SENHA, nome="Mod", is_staff=True)
    usuario.groups.add(Group.objects.get(name="Moderador"))
    return usuario


# --- Formulário público ----------------------------------------------------------------------------


def test_botao_do_anuncio_leva_ao_formulario_ja_preenchido(client, anuncio):
    """Sem login: a página do anúncio tem o link e o formulário vem com o código e os motivos."""
    link = reverse("moderacao:denunciar") + f"?anuncio={anuncio.codigo}"
    assert link in client.get(anuncios.url_publica(anuncio), **navegador()).content.decode()

    html = client.get(link, **navegador()).content.decode()
    assert f'value="{anuncio.codigo}"' in html and anuncio.titulo in html
    for rotulo in (
        "Golpe ou fraude",
        "Já foi vendido",
        "Preço ou dados falsos",
        "Conteúdo impróprio",
        "dados de terceiros",
        "Outro",
    ):
        assert rotulo in html
    assert "nd-armadilha" in html and "Sobre esta tela" in html


def test_envio_grava_e_volta_ao_anuncio_sem_ip(client, anuncio):
    """Texto e e-mail opcionais; volta ao anúncio com aviso; nenhum IP gravado (só o resumo do dia)."""
    resposta = enviar(client, anuncio, "vendido", texto="Já vendeu", email="eu@exemplo.com")

    assert resposta.status_code == 302 and resposta["Location"] == anuncios.url_publica(anuncio)
    denuncia = Denuncia.objects.get()
    assert (denuncia.motivo, denuncia.texto, denuncia.email) == ("vendido", "Já vendeu", "eu@exemplo.com")
    assert len(denuncia.origem) == 32 and "10.0.0.1" not in denuncia.origem
    assert not any("ip" in campo.name for campo in Denuncia._meta.get_fields())


def test_honeypot_finge_sucesso_e_nao_grava(client, anuncio):
    """Robô que preenche o campo-armadilha vê sucesso, mas nada é gravado."""
    resposta = enviar(client, anuncio, site_empresa="https://spam.exemplo.com")
    assert resposta.status_code == 302 and not Denuncia.objects.exists()


def test_anuncio_inexistente_ou_fora_do_ar(client, anuncio):
    """Código que não está no ar: erro no formulário, nada gravado."""
    Anuncio.objects.filter(pk=anuncio.pk).update(situacao=Situacao.PAUSADO)
    resposta = enviar(client, anuncio)
    assert resposta.status_code == 400 and "Não achamos este anúncio" in resposta.content.decode()
    assert not Denuncia.objects.exists()


def test_limite_por_dia_e_repeticao_do_mesmo_anuncio(client, loja, publicado):
    """Mesma origem e mesmo anúncio no dia: uma só. Passou do limite do dia (Configuracao): recusado."""
    config = configuracao()
    config.denuncias_por_dia = 2
    config.save()
    alfa = loja()
    a, b, c = (publicado(alfa, f"Casa número {n} no centro") for n in range(3))

    enviar(client, a, "vendido")
    enviar(client, a, "vendido")
    enviar(client, b, "vendido")
    resposta = enviar(client, c, "vendido")

    assert Denuncia.objects.count() == 2
    assert resposta.status_code == 400 and "muitas denúncias hoje" in resposta.content.decode()
    assert enviar(client, c, "vendido", n=2).status_code == 302  # outro visitante pode


# --- Pausa automática por golpe ---------------------------------------------------------------------


def test_tres_golpes_de_origens_diferentes_pausam_e_avisam(client, anuncio):
    """3 origens diferentes (padrão): sai do ar "em revisão", avisa a equipe e o anunciante (sem quem
    denunciou); o anunciante não consegue reativar. A mesma origem repetida não conta."""
    enviar(client, anuncio, n=1, email="segredo@exemplo.com", texto="texto secreto")
    enviar(client, anuncio, n=1)
    enviar(client, anuncio, n=2)
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO

    mail.outbox.clear()
    enviar(client, anuncio, n=3)
    anuncio.refresh_from_db()
    assert (anuncio.situacao, anuncio.pausado_por) == (Situacao.PAUSADO, Anuncio.PausadoPor.DENUNCIA)
    equipe, dono = sorted(mail.outbox, key=lambda m: m.to[0] == anuncio.anunciante.usuario.email)
    assert anuncio.codigo in equipe.subject
    assert dono.to == [anuncio.anunciante.usuario.email]
    assert (
        "segredo@exemplo.com" not in dono.body
        and "texto secreto" not in dono.body
        and "10.0.0" not in dono.body
    )
    with pytest.raises(ValueError, match="em revisão"):
        anuncios.reativar(anuncio)


def test_limite_de_golpe_vem_da_configuracao_e_outros_motivos_nao_pausam(client, anuncio):
    """Com o limite 2 no admin, duas origens pausam; "já vendido" não conta para a pausa."""
    config = configuracao()
    config.denuncias_golpe_para_pausar = 2
    config.save()
    enviar(client, anuncio, "vendido", n=1)
    enviar(client, anuncio, "vendido", n=2)
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO

    enviar(client, anuncio, "golpe", n=3)
    enviar(client, anuncio, "golpe", n=4)
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PAUSADO


# --- Decisão da equipe ---------------------------------------------------------------------------------


def denuncia_de(anuncio, motivo="golpe", origem="a") -> Denuncia:
    """Denúncia pendente direto no banco."""
    return Denuncia.objects.create(anuncio=anuncio, motivo=motivo, origem=origem, email="quem@exemplo.com")


def test_aceitar_pausando_avisa_sem_dizer_quem_e_o_anunciante_reativa(anuncio, moderador):
    """Pausa por moderação (o anunciante corrige e reativa), e-mail com o motivo e sem quem denunciou;
    todas as pendentes do anúncio ficam aceitas, com histórico."""
    primeira, segunda = denuncia_de(anuncio, origem="a"), denuncia_de(anuncio, "falso", origem="b")
    mail.outbox.clear()

    services.aceitar(primeira, moderador, "pausar", "Preço não confere com o imóvel.")

    anuncio.refresh_from_db()
    assert (anuncio.situacao, anuncio.pausado_por) == (Situacao.PAUSADO, Anuncio.PausadoPor.MODERACAO)
    assert set(Denuncia.objects.values_list("situacao", flat=True)) == {"aceita"}
    assert segunda.history.order_by("-history_id").first().history_user == moderador
    (email,) = mail.outbox
    assert "Preço não confere" in email.body and "quem@exemplo.com" not in email.body
    anuncios.reativar(anuncio)  # cabe no plano: volta ao ar
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO


def test_aceitar_removendo_e_motivo_obrigatorio(anuncio, moderador):
    """Remover = exclusão lógica; sem motivo não decide."""
    denuncia = denuncia_de(anuncio)
    with pytest.raises(ValueError, match="motivo"):
        services.aceitar(denuncia, moderador, "remover", " ")
    services.aceitar(denuncia, moderador, "remover", "Golpe confirmado.")
    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.REMOVIDO and anuncio.removido_em


def test_descartar_devolve_o_anuncio_em_revisao(client, anuncio, moderador):
    """Descartadas as denúncias, o anúncio que estava em revisão volta ao ar."""
    for n in (1, 2, 3):
        enviar(client, anuncio, n=n)
    services.descartar(Denuncia.objects.first(), moderador, "Era concorrente.")

    anuncio.refresh_from_db()
    assert anuncio.situacao == Situacao.PUBLICADO and anuncio.pausado_por == ""
    assert set(Denuncia.objects.values_list("situacao", flat=True)) == {"descartada"}


def test_fila_no_admin_aceitar_e_permissoes(entrar_no_admin, anuncio, moderador):
    """Moderador vê a fila (com o e-mail de quem denunciou, sem a origem) e aceita; Financeiro não vê."""
    denuncia = denuncia_de(anuncio, origem="origemsecreta123")
    client = entrar_no_admin(moderador)
    url = reverse("admin:moderacao_denuncia_changelist")
    assert anuncio.codigo in client.get(url).content.decode()
    ficha = client.get(reverse("admin:moderacao_denuncia_change", args=[denuncia.pk])).content.decode()
    assert "quem@exemplo.com" in ficha and denuncia.origem not in ficha

    dados = {"action": "aceitar_acao", ACTION_CHECKBOX_NAME: [denuncia.pk]}
    assert "O que fazer com o anúncio" in client.post(url, dados).content.decode()
    client.post(url, {**dados, "aplicar": "1", "acao": "pausar", "motivo": "Fotos de outro imóvel."})
    denuncia.refresh_from_db()
    assert (denuncia.situacao, denuncia.acao, denuncia.decidido_por) == ("aceita", "pausar", moderador)

    financeiro = Usuario.objects.create_user(
        email="fin@exemplo.com", password=SENHA, nome="Fin", is_staff=True
    )
    financeiro.groups.add(Group.objects.get(name="Financeiro"))
    assert entrar_no_admin(financeiro).get(url).status_code == 403


def test_anunciante_nao_ve_denuncias_no_painel(client, anuncio):
    """O painel do anunciante não mostra denúncia, e-mail nem detalhes de quem denunciou."""
    denuncia_de(anuncio)
    client.force_login(anuncio.anunciante.usuario)
    html = client.get(reverse("anunciantes:painel")).content.decode()
    assert "quem@exemplo.com" not in html and "denúncia" not in html.lower()


# --- Guarda e demonstração --------------------------------------------------------------------------


def test_guarda_apaga_email_e_detalhes_das_decididas_antigas(anuncio, moderador):
    """Decidida há mais que a guarda (365 dias): e-mail e detalhes apagados; pendente nunca."""
    antiga, pendente = denuncia_de(anuncio, origem="x"), denuncia_de(anuncio, "vendido", origem="y")
    Denuncia.objects.filter(pk=antiga.pk).update(
        situacao="descartada", decidido_em=timezone.now() - timedelta(days=400), texto="detalhe"
    )

    assert services.limpar_denuncias_antigas() == 1
    antiga.refresh_from_db()
    pendente.refresh_from_db()
    assert (antiga.email, antiga.texto) == ("", "") and pendente.email == "quem@exemplo.com"


def test_denuncias_demo(loja, publicado):
    """Duas denúncias fictícias pendentes em anúncios demo; apagar limpa."""
    alfa = loja()
    for n in range(2):
        publicado(alfa, f"Imóvel demo número {n}")
    Anuncio.objects.update(demo=True)

    assert services.criar_denuncias_demo() == 2
    assert Denuncia.objects.filter(demo=True, situacao="pendente").count() == 2
    services.apagar_denuncias_demo()
    assert not Denuncia.objects.exists()
