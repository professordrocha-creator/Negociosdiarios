"""Pix estático "copia e cola" (BR Code) e QR Code, sem API externa (Sprint 6).

Segue o Manual de Padrões para Iniciação do Pix do Banco Central (EMV QRCPS-MPM): cada campo é
ID (2 dígitos) + tamanho (2 dígitos) + valor, e o código termina com o CRC16-CCITT (polinômio 0x1021,
valor inicial 0xFFFF) de tudo, incluindo o "6304" do próprio campo do CRC.

A chave, o nome e a cidade do recebedor vêm da "Configuração do Pix" no admin (lote 3B; só Administrador
e Financeiro) e, se lá estiver vazio, do .env (PIX_CHAVE, PIX_NOME, PIX_CIDADE). O valor e o
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
    """Chave, nome ou cidade do recebedor vazios (Configuração do Pix e .env)."""


# Formatos de chave do Pix (Manual do DICT do Banco Central): e-mail até 77, CPF e CNPJ só dígitos, celular em
# E.164 (+55 + DDD + número) e chave aleatória (UUID com hífens, 36 caracteres).
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_ALEATORIA = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CELULAR = re.compile(r"^\+55[1-9]{2}9?\d{8}$")


def cpf_valido(digitos: str) -> bool:
    """CPF com 11 dígitos e os dois verificadores certos (módulo 11)."""
    if not re.fullmatch(r"\d{11}", digitos) or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(
            int(n) * peso for n, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1), strict=True)
        )
        if digitos[tamanho] != str(soma * 10 % 11 % 10):
            return False
    return True


def validar_chave(texto: str) -> tuple[str, str]:
    """Confere a chave Pix e devolve (tipo, chave normalizada): e-mail (minúsculo), CPF/CNPJ (só dígitos),
    celular (+55DDDNÚMERO) ou aleatória (minúscula). Levanta ValueError dizendo o que corrigir.

    Celular sem +55 (só DDD e número) também é aceito; 11 dígitos sem "+" são lidos como CPF (o Banco Central
    exige o celular com +55, então quem digitar o celular sem ele deve pôr o +55).
    """
    from anunciantes.validators import cnpj_valido  # import local: este módulo não depende de apps

    chave = (texto or "").strip()
    if not chave:
        raise ValueError("Informe a chave Pix.")
    if "@" in chave:
        if len(chave) > 77 or not _EMAIL.fullmatch(chave):
            raise ValueError("E-mail inválido para chave Pix. Confira o endereço (até 77 caracteres).")
        return "email", chave.lower()
    if _ALEATORIA.fullmatch(chave.lower()):
        return "aleatoria", chave.lower()
    digitos = re.sub(r"\D", "", chave)
    if chave.startswith("+"):
        celular = "+" + digitos
        if not _CELULAR.fullmatch(celular):
            raise ValueError("Celular inválido: use +55, o DDD e o número. Ex.: +5565999990001.")
        return "celular", celular
    if len(digitos) == 11 and cpf_valido(digitos):
        return "cpf", digitos
    if len(digitos) == 14 and cnpj_valido(digitos):
        return "cnpj", digitos
    parece_documento = "." in chave or "/" in chave  # máscara de CPF/CNPJ: nunca é lido como telefone
    if not parece_documento and len(digitos) in (10, 11) and _CELULAR.fullmatch("+55" + digitos):
        return "celular", "+55" + digitos
    raise ValueError(
        "Chave Pix inválida. Use um e-mail, CPF ou CNPJ (com dígitos verificadores certos), celular com +55 "
        "e DDD, ou a chave aleatória (36 caracteres, com hífens)."
    )


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
        raise PixNaoConfigurado("Preencha a Configuração do Pix no admin.")
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
