"""Testes do Pix estático (BR Code / EMV do Banco Central) e do QR Code."""

from decimal import Decimal

import pytest

from pagamentos import pix

# Exemplo do Manual de Padrões para Iniciação do Pix (Banco Central): chave aleatória, sem valor.
EXEMPLO_BCB = (
    "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-426655440000"
    "5204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D"
)


def campos(codigo: str) -> dict[str, str]:
    """Lê os campos EMV (ID + tamanho + valor) do código; falha se o tamanho de algum não bate."""
    lidos, posicao = {}, 0
    while posicao < len(codigo):
        identificador, tamanho = codigo[posicao : posicao + 2], int(codigo[posicao + 2 : posicao + 4])
        valor = codigo[posicao + 4 : posicao + 4 + tamanho]
        assert len(valor) == tamanho, f"campo {identificador} cortado"
        lidos[identificador] = valor
        posicao += 4 + tamanho
    return lidos


def test_reproduz_o_exemplo_do_banco_central():
    """Mesma chave, nome e cidade do manual: o código sai idêntico, CRC 1D3D incluído."""
    assert pix.crc16(EXEMPLO_BCB[:-4]) == "1D3D"
    assert pix.br_code("123e4567-e12b-12d1-a456-426655440000", "Fulano de Tal", "BRASILIA") == EXEMPLO_BCB


def test_crc16_valor_de_conferencia():
    """CRC-16/CCITT-FALSE de "123456789" é 29B1 (valor de conferência do algoritmo)."""
    assert pix.crc16("123456789") == "29B1"


def test_com_valor_e_identificador_da_fatura():
    """Valor com 2 casas no campo 54, identificador no 62-05 e CRC certo no fim."""
    codigo = pix.br_code("12345678000195", "Negocios Diarios", "Tangara", Decimal("99.9"), "ND-FT-00012")
    lidos = campos(codigo)

    assert lidos["00"] == "01"
    assert campos(lidos["26"]) == {"00": "br.gov.bcb.pix", "01": "12345678000195"}
    assert (lidos["52"], lidos["53"], lidos["54"], lidos["58"]) == ("0000", "986", "99.90", "BR")
    assert campos(lidos["62"]) == {"05": "NDFT00012"}
    assert codigo[-8:-4] == "6304" and codigo[-4:] == pix.crc16(codigo[:-4])


def test_nome_e_cidade_sem_acento_e_no_limite():
    """Nome até 25 e cidade até 15 caracteres, sem acento (os apps de banco leem melhor)."""
    lidos = campos(
        pix.br_code("chave@exemplo.com", "Negócios Diários Classificados Ltda", "Tangará da Serra")
    )

    assert lidos["59"] == "Negocios Diarios Classifi"
    assert lidos["60"] == "Tangara da Serr"
    assert "54" not in lidos  # sem valor: o pagador digita
    assert campos(lidos["62"]) == {"05": "***"}


@pytest.mark.parametrize("faltando", ["chave", "nome", "cidade"])
def test_sem_configuracao_avisa(faltando):
    """Sem chave, nome ou cidade no .env não há código (a tela mostra "Pix não disponível")."""
    dados = {"chave": "123", "nome": "Loja", "cidade": "Cuiaba", faltando: "  "}
    with pytest.raises(pix.PixNaoConfigurado):
        pix.br_code(**dados)


def test_identificador_so_letras_e_numeros_ate_25():
    """txid do Pix: alfanumérico, no máximo 25."""
    assert pix.txid("ND-FT-00012") == "NDFT00012"
    assert pix.txid("a" * 30) == "a" * 25
    assert pix.txid("--") == "***"


def test_qr_code_em_svg_data_uri():
    """QR Code como imagem SVG embutida (a CSP libera data: em imagens; nada de script)."""
    uri = pix.qr_code_svg(EXEMPLO_BCB)

    assert uri.startswith("data:image/svg+xml")
    assert "script" not in uri.lower()
