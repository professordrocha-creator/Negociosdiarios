"""Testes da validação de CNPJ, CRECI e WhatsApp e das regras do modelo Anunciante."""

import pytest
from django.core.exceptions import ValidationError

from anunciantes.models import Anunciante
from anunciantes.validators import cnpj_valido, normalizar_cnpj, normalizar_creci, normalizar_whatsapp

pytestmark = pytest.mark.django_db


# --- CNPJ --------------------------------------------------------------------------------


@pytest.mark.parametrize("entrada", ["90.000.001/0001-29", "90000001000129", " 90 000 001 0001 29 "])
def test_cnpj_valido_com_ou_sem_pontuacao(entrada):
    """Pontos, barra, traço e espaços são opcionais; guarda só os 14 dígitos."""
    assert normalizar_cnpj(entrada) == "90000001000129"


@pytest.mark.parametrize(
    ("entrada", "trecho"),
    [
        ("90000001000128", "verificadores"),  # último dígito errado
        ("90000001000139", "verificadores"),  # penúltimo dígito errado
        ("11111111111111", "verificadores"),  # todos iguais (passa no cálculo, mas não existe)
        ("9000000100012", "14 dígitos"),
        ("", "14 dígitos"),
    ],
)
def test_cnpj_invalido_explica_o_erro(entrada, trecho):
    """CNPJ errado é recusado com mensagem que diz o que conferir."""
    with pytest.raises(ValidationError, match=trecho):
        normalizar_cnpj(entrada)


def test_cnpj_valido_confere_os_dois_digitos():
    """Função pura usada também pelos testes do demo.json."""
    assert cnpj_valido("90000005000107")
    assert not cnpj_valido("90000005000108")


# --- CRECI -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("CRECI/MT 08765-F", "CRECI/MT 08765-F"),
        ("creci-mt 8765 f", "CRECI/MT 8765-F"),
        ("MT 8765-J", "CRECI/MT 8765-J"),
        ("8765F", "CRECI/MT 8765-F"),  # sem UF: usa a UF padrão (da cidade)
        ("CRECI/SP 123456-F", "CRECI/SP 123456-F"),
    ],
)
def test_creci_normalizado(entrada, esperado):
    """Aceita as formas comuns e guarda no padrão CRECI/UF número-sufixo."""
    assert normalizar_creci(entrada) == esperado


@pytest.mark.parametrize(
    "entrada", ["", "CRECI/MT 8765", "CRECI/MT 12-F", "CRECI/XX 8765-F", "8765-X", "abc"]
)
def test_creci_invalido(entrada):
    """Sem sufixo F/J, número curto ou UF inexistente: recusado."""
    with pytest.raises(ValidationError):
        normalizar_creci(entrada)


# --- WhatsApp ----------------------------------------------------------------------------


@pytest.mark.parametrize("entrada", ["(65) 99999-0001", "65999990001", "+55 65 99999-0001", "5565999990001"])
def test_whatsapp_vira_e164(entrada):
    """Guardado em E.164 (regra de dados do projeto)."""
    assert normalizar_whatsapp(entrada) == "+5565999990001"


@pytest.mark.parametrize("entrada", ["", "99999-0001", "(65) 89999-0001", "(00) 99999-0001", "123"])
def test_whatsapp_invalido(entrada):
    """Sem DDD, celular sem o 9 ou DDD inválido: recusado."""
    with pytest.raises(ValidationError):
        normalizar_whatsapp(entrada)


# --- Regras do modelo --------------------------------------------------------------------


def _novo(tangara, **campos) -> Anunciante:
    """Anunciante ainda não salvo, para testar o clean()."""
    from contas.models import Usuario

    usuario = Usuario.objects.create_user(
        email=f"{campos.get('slug', 'x')}@exemplo.com", password=None, nome="X"
    )
    dados = {
        "usuario": usuario,
        "tipo": Anunciante.Tipo.REVENDA,
        "nome_publico": "Loja X",
        "slug": "loja-x",
        "documento_tipo": "cnpj",
        "documento_numero": "90.000.001/0001-29",
        "whatsapp": "(65) 99999-0001",
        "cidade": tangara,
    }
    dados.update(campos)
    return Anunciante(**dados)


def test_clean_normaliza_documento_e_whatsapp(tangara):
    """O full_clean (admin/formulários) guarda CNPJ só dígitos e WhatsApp em E.164."""
    anunciante = _novo(tangara)

    anunciante.full_clean()

    assert anunciante.documento_numero == "90000001000129"
    assert anunciante.whatsapp == "+5565999990001"


def test_corretor_autonomo_exige_creci(tangara):
    """Corretor autônomo prova a profissão pelo CRECI, não pelo CNPJ."""
    anunciante = _novo(tangara, tipo=Anunciante.Tipo.CORRETOR_AUTONOMO, slug="corretor")

    with pytest.raises(ValidationError) as erro:
        anunciante.full_clean()
    assert "documento_tipo" in erro.value.message_dict


def test_revenda_exige_cnpj(tangara):
    """Revenda é empresa: CNPJ."""
    anunciante = _novo(tangara, documento_tipo="creci", documento_numero="CRECI/MT 8765-F", slug="revenda")

    with pytest.raises(ValidationError) as erro:
        anunciante.full_clean()
    assert "documento_tipo" in erro.value.message_dict


def test_cnpj_errado_no_modelo(tangara):
    """CNPJ com dígito errado não passa no cadastro."""
    anunciante = _novo(tangara, documento_numero="90.000.001/0001-28", slug="errado")

    with pytest.raises(ValidationError) as erro:
        anunciante.full_clean()
    assert "documento_numero" in erro.value.message_dict


def test_cidade_nao_liberada_e_recusada(tangara):
    """Só cidades liberadas no site podem ter lojas."""
    tangara.liberada = False
    tangara.save()

    with pytest.raises(ValidationError) as erro:
        _novo(tangara, slug="fora").full_clean()
    assert "cidade" in erro.value.message_dict


def test_documento_nao_se_repete(criar_anunciante, tangara):
    """O mesmo CNPJ não pode ter duas lojas."""
    primeira = criar_anunciante("a@exemplo.com", "Loja A")

    segunda = _novo(tangara, slug="loja-b", documento_numero=primeira.documento_numero)
    with pytest.raises(ValidationError):
        segunda.full_clean()


def test_iniciais_do_monograma(criar_anunciante):
    """Sem sigla, usa as iniciais das duas primeiras palavras."""
    assert criar_anunciante("a@exemplo.com", "Garagem Rota 358").iniciais == "GR"
    assert criar_anunciante("b@exemplo.com", "Loja Sigla", sigla="ls").iniciais == "LS"
