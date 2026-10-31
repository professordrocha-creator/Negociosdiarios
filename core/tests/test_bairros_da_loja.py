"""Parte 4, etapa 3: bairro criado pela loja ("Outro bairro" no anúncio). Padronização, recusa de links e
lixo, sem duplicar por acento ou maiúscula, limite por dia, vale na hora para a cidade, marcador "criado por
loja" e a ação do admin que junta duplicados."""

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse

from anunciantes.tests.conftest import SENHA
from contas.models import Usuario
from core.models import Bairro
from core.services import bairro_informado, configuracao, juntar_bairros, normalizar_nome_bairro

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("  jardim   DAS flores ", "Jardim das Flores"),
        ("vila <b>nova</b>", "Vila Nova"),
        ("residencial são joão 2", "Residencial São João 2"),
    ],
)
def test_nome_padronizado(texto, esperado):
    """Espaços, maiúsculas (de/da/do em minúscula) e sem HTML."""
    assert normalizar_nome_bairro(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["ab", "x" * 61, "www.spam.com.br", "http://a.b", "zap 65999990000", "##$$!!", "12345"]
)
def test_lixo_links_e_telefones_sao_recusados(texto):
    """Curto, longo, link, telefone, só símbolos ou só números: recusado com mensagem."""
    with pytest.raises(ValidationError):
        normalizar_nome_bairro(texto)


def test_nao_duplica_por_acento_ou_maiuscula_e_respeita_o_inativo(tangara, loja):
    """O mesmo nome com outra grafia devolve o bairro que já existe; bairro desativado pela equipe não
    volta."""
    anunciante = loja()
    existente = Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")

    assert bairro_informado(tangara, "JARDIM  európa", anunciante, criar=True) == existente
    existente.ativo = False
    existente.save()
    with pytest.raises(ValidationError, match="não está disponível"):
        bairro_informado(tangara, "jardim europa", anunciante, criar=True)


def test_limite_de_bairros_novos_por_dia(tangara, loja):
    """Passou do limite da Configuração: recusa o próximo bairro novo (o existente continua valendo)."""
    config = configuracao()
    config.bairros_novos_por_dia = 2
    config.save()
    anunciante = loja()
    bairro_informado(tangara, "Bairro Um", anunciante, criar=True)
    bairro_informado(tangara, "Bairro Dois", anunciante, criar=True)

    with pytest.raises(ValidationError, match="máximo de bairros novos"):
        bairro_informado(tangara, "Bairro Três", anunciante, criar=True)
    assert bairro_informado(tangara, "bairro um", anunciante, criar=True).nome == "Bairro Um"


def test_outro_bairro_no_anuncio_cria_e_vale_para_a_cidade(client, loja, imovel, tangara):
    """ "Outro bairro" no anúncio cria o bairro na cidade (marcado com a loja) e ele aparece para outra
    loja."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    url = reverse("anuncios:localizacao", args=[anuncio.codigo])
    assert 'value="outro"' in client.get(url).content.decode()

    resposta = client.post(
        url,
        {
            "cidade": tangara.pk,
            "bairro": "outro",
            "bairro_novo": "  parque   DAS águas ",
            "endereco": "",
            "latitude": "-14.1",
            "longitude": "-57.2",
            "exibir_localizacao": "aproximada",
        },
    )

    assert resposta["Location"] == reverse("anuncios:fotos", args=[anuncio.codigo])
    bairro = Bairro.objects.get(cidade=tangara, slug="parque-das-aguas")
    anuncio.refresh_from_db()
    assert anuncio.bairro == bairro and bairro.nome == "Parque das Águas" and bairro.criado_por == anunciante

    outra = loja("outra@exemplo.com", "Loja Outra")
    client.force_login(outra.usuario)
    pagina = client.get(reverse("anuncios:localizacao", args=[imovel(outra, completo=False).codigo]))
    assert f'value="{bairro.pk}" data-cidade="{tangara.pk}"' in pagina.content.decode()


def test_outro_bairro_sem_nome_ou_com_link_da_erro(client, loja, imovel, tangara):
    """ "Outro bairro" exige um nome válido; nada é criado."""
    anunciante = loja()
    anuncio = imovel(anunciante, completo=False)
    client.force_login(anunciante.usuario)
    base = {
        "cidade": tangara.pk,
        "bairro": "outro",
        "endereco": "",
        "latitude": "-14.1",
        "longitude": "-57.2",
        "exibir_localizacao": "aproximada",
    }
    url = reverse("anuncios:localizacao", args=[anuncio.codigo])

    assert "Escreva o nome do bairro" in client.post(url, {**base, "bairro_novo": ""}).content.decode()
    assert "sem links" in client.post(url, {**base, "bairro_novo": "www.x.com"}).content.decode()
    assert not Bairro.objects.filter(criado_por=anunciante).exists()


def test_admin_filtra_criado_por_loja_e_junta_duplicados(entrar_no_admin, loja, imovel, tangara):
    """Filtro "criado por loja" e a ação que junta: o anúncio passa para o bairro que fica; o outro fica
    inativo."""
    anunciante = loja()
    certo = Bairro.objects.create(cidade=tangara, nome="Jardim Europa", slug="jardim-europa")
    repetido = Bairro.objects.create(
        cidade=tangara, nome="Jd Europa", slug="jd-europa", criado_por=anunciante
    )
    anuncio = imovel(anunciante, completo=False)
    anuncio.bairro = repetido
    anuncio.save()
    usuario = Usuario.objects.create_user(email="adm@exemplo.com", password=SENHA, nome="Adm", is_staff=True)
    usuario.groups.add(Group.objects.get(name="Administrador"))
    cliente = entrar_no_admin(usuario)
    lista = reverse("admin:core_bairro_changelist")

    filtrada = cliente.get(lista + "?criado_por_loja=sim").content.decode()
    assert "Jd Europa" in filtrada and "Loja Alfa" in filtrada and ">Jardim Europa<" not in filtrada

    tela = cliente.post(
        lista, {"action": "juntar_duplicados", ACTION_CHECKBOX_NAME: [certo.pk, repetido.pk]}
    ).content.decode()
    assert "Escolha o nome que fica" in tela
    cliente.post(
        lista,
        {
            "action": "juntar_duplicados",
            ACTION_CHECKBOX_NAME: [certo.pk, repetido.pk],
            "manter": certo.pk,
            "aplicar": "1",
        },
    )

    anuncio.refresh_from_db()
    repetido.refresh_from_db()
    assert anuncio.bairro == certo and not repetido.ativo


def test_nao_junta_bairros_de_cidades_diferentes(tangara):
    """Juntar só dentro da mesma cidade."""
    from core.models import Cidade

    outra = Cidade.objects.create(
        codigo_ibge=5107909, nome="Sinop", slug="sinop", uf=tangara.uf, liberada=True, ponto=tangara.ponto
    )
    a = Bairro.objects.create(cidade=tangara, nome="Centro", slug="centro")
    b = Bairro.objects.create(cidade=outra, nome="Centro", slug="centro")
    with pytest.raises(ValidationError):
        juntar_bairros(a, [a, b], None)
