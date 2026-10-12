"""Pix estático "copia e cola" (BR Code) e QR Code, sem API externa (Sprint 6).

Segue o Manual de Padrões para Iniciação do Pix do Banco Central (EMV QRCPS-MPM): cada campo é
ID (2 dígitos) + tamanho (2 dígitos) + valor, e o código termina com o CRC16-CCITT (polinômio 0x1021,
valor inicial 0xFFFF) de tudo, incluindo o "6304" do próprio campo do CRC.

A chave, o nome e a cidade do recebedor vêm do .env (PIX_CHAVE, PIX_NOME, PIX_CIDADE). O valor e o
identificador da fatura (campo 62-05, "txid") vão no código: o banco do anunciante já preenche o valor
e o identificador aparece no extrato de quem recebe, para conferir o pagamento.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

import segno

GUI_PIX = "br.gov.bcb.pix"
TXID_SEM_IDENTIFICADOR = "***"


class PixNaoConfigurado(Exception):
    """PIX_CHAVE, PIX_NOME ou PIX_CIDADE vazios no .env."""


def campo(identificador: str, valor: str) -> str:
    """Um campo EMV: ID + tamanho com 2 dígitos + valor (no máximo 99 caracteres)."""
    if len(valor) > 99:
        raise ValueError(f"Campo {identificador} com mais de 99 caracteres.")
    return f"{identificador}{len(valor):02d}{valor}"


def crc16(dados: str) -> str:
    """CRC16-CCITT-FALSE (0x1021, início 0xFFFF) em 4 dígitos hexadecimais maiúsculos."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def texto_ascii(texto: str, limite: int) -> str:
    """Sem acentos e só caracteres comuns (os apps de banco leem melhor), cortado no limite do campo."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9 .,\-/]", "", sem_acento).strip()[:limite]


def txid(identificador: str) -> str:
    """Identificador da cobrança no campo 62-05: só letras e números, até 25 (ou "***" sem identificador)."""
    limpo = re.sub(r"[^A-Za-z0-9]", "", identificador)[:25]
    return limpo or TXID_SEM_IDENTIFICADOR


def br_code(chave: str, nome: str, cidade: str, valor: Decimal | None = None, identificador: str = "") -> str:
    """O "Pix copia e cola" estático.

    `valor` None ou zero = o pagador digita o valor. `nome` vira ASCII com até 25 caracteres e
    `cidade`, até 15 (limites do manual do Banco Central).
    """
    chave, nome, cidade = chave.strip(), texto_ascii(nome, 25), texto_ascii(cidade, 15)
    if not (chave and nome and cidade):
        raise PixNaoConfigurado("Configure PIX_CHAVE, PIX_NOME e PIX_CIDADE no .env.")
    conta = campo("00", GUI_PIX) + campo("01", chave)
    partes = [
        campo("00", "01"),  # versão do payload
        campo("26", conta),  # conta do recebedor (Pix)
        campo("52", "0000"),  # categoria do comerciante (não informada)
        campo("53", "986"),  # moeda: real
    ]
    if valor:
        partes.append(campo("54", f"{Decimal(valor).quantize(Decimal('0.01'))}"))
    partes += [
        campo("58", "BR"),
        campo("59", nome),
        campo("60", cidade),
        campo("62", campo("05", txid(identificador))),
    ]
    sem_crc = "".join(partes) + "6304"
    return sem_crc + crc16(sem_crc)


def qr_code_svg(codigo: str) -> str:
    """QR Code do código em SVG como data URI (para `<img src>`: a CSP libera `data:` em imagens)."""
    return segno.make(codigo, error="m").svg_data_uri(scale=6, border=2)
