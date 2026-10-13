"""Testes do cadastro público (/cadastro/): válido, inválido, duplicado, honeypot e limite por IP."""

import pytest
from django.core import mail
from django.urls import reverse

from anunciantes.models import Anunciante
from contas.models import AceiteDocumento, Usuario

pytestmark = pytest.mark.django_db

SENHA_NOVA = "Senha-Nova-Forte-2026"


@pytest.fixture
def dados(tangara):
    """Cadastro válido de uma revenda."""
    return {
        "nome": "Maria Souza",
        "email": "Maria@Revenda.example",
        "senha": SENHA_NOVA,
        "senha_confirmacao": SENHA_NOVA,
        "tipo": "revenda",
        "nome_publico": "Revenda da Maria",
        "documento": "90.000.001/0001-29",
        "whatsapp": "(65) 99999-1234",
        "cidade": tangara.pk,
        "aceite": "on",
        "site_empresa": "",
    }


def cadastrar(client, dados, ip: str = "127.0.0.1"):
    """Envia o formulário de /cadastro/."""
    return client.post(reverse("anunciantes:cadastro"), dados, REMOTE_ADDR=ip)


# --- Tela ---------------------------------------------------------------------------------


def test_tela_de_cadastro_tem_campos_aceite_e_armadilha_escondida(client, tangara):
    """Campos da conta e da loja, links dos documentos e o honeypot fora da tela."""
    html = client.get(reverse("anunciantes:cadastro")).content.decode()

    for campo in [
        "nome",
        "email",
        "senha",
        "tipo",
        "nome_publico",
        "documento",
        "whatsapp",
        "cidade",
        "aceite",
    ]:
        assert f'name="{campo}"' in html, campo
    assert 'class="nd-armadilha" aria-hidden="true"' in html and 'name="site_empresa"' in html
    assert reverse("core:termos") in html and reverse("core:privacidade") in html
    assert "Tangará da Serra" in html


# --- Cadastro válido ---------------------------------------------------------------------


def test_cadastro_valido_cria_loja_pendente_aceites_e_emails(client, dados):
    """Conta + loja pendente + aceites (data e versão) + e-mails "confirme" e "recebemos"."""
    resposta = cadastrar(client, dados)

    assert resposta["Location"] == reverse("anunciantes:cadastro_obrigado")
    usuario = Usuario.objects.get(email="maria@revenda.example")  # normalizado
    assert usuario.check_password(SENHA_NOVA) and not usuario.is_staff
    assert usuario.email_confirmado_em is None
    loja = usuario.anunciante
    assert loja.status == Anunciante.Status.PENDENTE
    assert (loja.documento_tipo, loja.documento_numero) == ("cnpj", "90000001000129")
    assert loja.whatsapp == "+5565999991234" and loja.slug == "revenda-da-maria"
    aceites = {(a.documento, a.versao) for a in AceiteDocumento.objects.filter(usuario=usuario)}
    from privacidade.services import documento_vigente

    vigentes = {(tipo, documento_vigente(tipo).versao) for tipo in ("termos", "privacidade")}
    assert aceites == vigentes
    assert all(a.aceito_em for a in AceiteDocumento.objects.filter(usuario=usuario))
    assuntos = sorted(m.subject for m in mail.outbox)
    assert len(assuntos) == 2
    assert assuntos[0].startswith("Confirme seu e-mail") and assuntos[1].startswith("Recebemos seu cadastro")
    assert all(m.to == ["maria@revenda.example"] for m in mail.outbox)


def test_corretor_se_cadastra_com_creci(client, dados):
    """Corretor autônomo: CRECI normalizado."""
    dados.update(tipo="corretor_autonomo", documento="creci mt 4321 f", nome_publico="João Corretor")

    cadastrar(client, dados)

    loja = Anunciante.objects.get()
    assert (loja.documento_tipo, loja.documento_numero) == ("creci", "CRECI/MT 4321-F")


def test_obrigado_explica_os_proximos_passos(client, db):
    """A tela de obrigado fala de confirmar o e-mail e da análise."""
    html = client.get(reverse("anunciantes:cadastro_obrigado")).content.decode()

    assert "Confirme seu e-mail" in html and "48 horas" in html and "análise" in html.lower()


def test_slug_repetido_ganha_sufixo(client, dados, criar_anunciante):
    """Nome de loja igual a outra: o endereço ganha -2."""
    criar_anunciante("outra@exemplo.com", "Revenda da Maria")
    dados["documento"] = "90000005000107"  # outro CNPJ válido (a fábrica usou o primeiro)

    cadastrar(client, dados)

    assert Anunciante.objects.get(usuario__email="maria@revenda.example").slug == "revenda-da-maria-2"


# --- Cadastro inválido -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mudanca", "campo", "trecho"),
    [
        ({"senha_confirmacao": "Outra-Senha-2026"}, "senha_confirmacao", "não são iguais"),
        ({"senha": "12345678", "senha_confirmacao": "12345678"}, "senha", ""),
        ({"documento": "90.000.001/0001-28"}, "documento", "verificadores"),
        ({"tipo": "corretor_autonomo"}, "documento", "CRECI inválido"),  # corretor com CNPJ
        ({"whatsapp": "1234"}, "whatsapp", "WhatsApp inválido"),
        ({"aceite": ""}, "aceite", "aceitar os Termos"),
        ({"cidade": ""}, "cidade", ""),
        ({"email": "sem-arroba"}, "email", ""),
    ],
)
def test_cadastro_invalido_mostra_o_erro_e_nao_cria_nada(client, dados, mudanca, campo, trecho):
    """Cada problema volta ao formulário com mensagem no campo; nada é gravado nem enviado."""
    dados.update(mudanca)

    resposta = cadastrar(client, dados)

    assert resposta.status_code == 200
    assert campo in resposta.context["form"].errors
    if trecho:
        assert trecho in " ".join(resposta.context["form"].errors[campo])
    assert not Usuario.objects.exists() and not mail.outbox


def test_cidade_nao_atendida_e_aceita_e_gera_solicitacao(client, dados, tangara):
    """Cidade ainda não liberada: o cadastro passa e vira uma SolicitacaoCidade pendente."""
    from anunciantes.models import SolicitacaoCidade

    tangara.liberada = False
    tangara.save()

    resposta = cadastrar(client, dados)

    assert resposta["Location"] == reverse("anunciantes:cadastro_obrigado")
    solicitacao = SolicitacaoCidade.objects.get()
    assert solicitacao.cidade == tangara and solicitacao.status == "pendente"
    assert solicitacao.anunciante.usuario.email == "maria@revenda.example"


def test_cidade_de_estado_nao_liberado_nao_aparece(client, dados, tangara):
    """Estado desligado: as cidades dele nem aparecem nas opções."""
    tangara.uf.liberado = False
    tangara.uf.save()

    resposta = cadastrar(client, dados)

    assert "cidade" in resposta.context["form"].errors


def test_cadastro_lista_cidades_atendidas_primeiro_e_marca_as_outras(client, tangara):
    """Atendidas primeiro; as demais do estado com "ainda não atendida"."""
    from django.contrib.gis.geos import Point

    from core.models import Cidade

    Cidade.objects.create(
        codigo_ibge=5107909, nome="Sinop", slug="sinop", uf=tangara.uf, ponto=Point(-55, -11)
    )

    html = client.get(reverse("anunciantes:cadastro")).content.decode()

    assert "Sinop — ainda não atendida" in html
    assert html.index("Tangará da Serra") < html.index("Sinop — ainda não atendida")


def test_email_ja_cadastrado(client, dados, criar_anunciante):
    """E-mail repetido (em qualquer caixa): sugere "Esqueci minha senha"."""
    criar_anunciante("maria@revenda.example", "Outra Loja")

    resposta = cadastrar(client, dados)

    assert "Esqueci minha senha" in resposta.context["form"].errors["email"][0]


def test_cnpj_duplicado(client, dados, criar_anunciante):
    """CNPJ de uma loja existente (mesmo com outra pontuação) é recusado."""
    criar_anunciante("outra@exemplo.com", "Outra Loja")  # usa 90000001000129

    resposta = cadastrar(client, dados)

    assert "Já existe uma loja com este CNPJ" in resposta.context["form"].errors["documento"][0]
    assert Anunciante.objects.count() == 1


def test_creci_duplicado(client, dados, criar_anunciante):
    """CRECI de outro corretor é recusado, mesmo escrito de outro jeito."""
    criar_anunciante("outro@exemplo.com", "Outro Corretor", corretor=True)  # CRECI/MT 12345-F
    dados.update(tipo="corretor_autonomo", documento="12345F")

    resposta = cadastrar(client, dados)

    assert "Já existe uma loja com este CRECI" in resposta.context["form"].errors["documento"][0]


# --- Proteção contra robô ----------------------------------------------------------------


def test_honeypot_preenchido_finge_sucesso_e_nao_cria_nada(client, dados):
    """Robô que preenche o campo-armadilha vê a tela de sucesso, mas nada é criado nem enviado."""
    dados["site_empresa"] = "http://spam.example"

    resposta = cadastrar(client, dados)

    assert resposta["Location"] == reverse("anunciantes:cadastro_obrigado")
    assert not Usuario.objects.exists() and not mail.outbox


def test_limite_por_ip(client, dados, settings):
    """Depois do limite de envios por hora, o mesmo IP recebe 429; outro IP continua livre."""
    settings.LIMITE_CADASTROS_POR_HORA = 3
    invalido = {**dados, "aceite": ""}
    for _ in range(3):
        assert cadastrar(client, invalido).status_code == 200

    bloqueado = cadastrar(client, dados)

    assert bloqueado.status_code == 429
    assert "Muitas tentativas" in bloqueado.content.decode()
    assert not Usuario.objects.exists()
    assert cadastrar(client, dados, ip="203.0.113.50").status_code == 302


def test_anunciante_logado_vai_para_o_painel(client, criar_anunciante):
    """Quem já tem loja e está logado não vê o cadastro."""
    client.force_login(criar_anunciante("a@exemplo.com", "Loja A").usuario)

    assert client.get(reverse("anunciantes:cadastro"))["Location"] == reverse("anunciantes:painel")
