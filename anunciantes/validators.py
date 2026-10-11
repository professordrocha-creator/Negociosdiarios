"""Validação e normalização dos documentos do anunciante (CNPJ e CRECI) e do WhatsApp.

Funções puras (sem banco), usadas pelo modelo, pelos formulários e pelos serviços.
Regra de dados do projeto: CPF/CNPJ só dígitos; telefone em E.164.
"""

import re

from django.core.exceptions import ValidationError

UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}  # fmt: skip

_PESOS_CNPJ_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_2 = [6, *_PESOS_CNPJ_1]

# "CRECI/MT 08765-F", "CRECI-MT 8765 F", "MT 8765-F", "8765F" (UF opcional, sufixo F ou J).
_CRECI = re.compile(r"^(?:CRECI)?[\s/\-]*(?:([A-Z]{2})[\s/\-]*)?(\d{3,6})[\s\-]*([FJ])$")


def _digito_cnpj(base: str, pesos: list[int]) -> str:
    """Dígito verificador do CNPJ (módulo 11)."""
    resto = sum(int(n) * p for n, p in zip(base, pesos, strict=True)) % 11
    return "0" if resto < 2 else str(11 - resto)


def cnpj_valido(digitos: str) -> bool:
    """Diz se um CNPJ (só dígitos) tem 14 dígitos e os dois verificadores certos."""
    if not re.fullmatch(r"\d{14}", digitos) or len(set(digitos)) == 1:
        return False
    d1 = _digito_cnpj(digitos[:12], _PESOS_CNPJ_1)
    d2 = _digito_cnpj(digitos[:12] + d1, _PESOS_CNPJ_2)
    return digitos[12:] == d1 + d2


def normalizar_cnpj(texto: str) -> str:
    """Tira pontos, barra e traço e valida. "12.345.678/0001-90" → "12345678000190".

    Levanta ValidationError com mensagem que diz o que fazer.
    """
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) != 14:
        raise ValidationError("O CNPJ tem 14 dígitos. Confira o número (pontos e traços são opcionais).")
    if not cnpj_valido(digitos):
        raise ValidationError("CNPJ inválido: os dígitos verificadores não conferem. Confira o número.")
    return digitos


def normalizar_creci(texto: str, uf_padrao: str = "MT") -> str:
    """Valida e padroniza o CRECI: "creci mt 8765-f" → "CRECI/MT 8765-F".

    Aceita com ou sem a UF (usa `uf_padrao`, a do conselho regional da cidade). O
    sufixo é F (pessoa física, corretor) ou J (pessoa jurídica, imobiliária).
    """
    achado = _CRECI.match((texto or "").strip().upper())
    if not achado:
        raise ValidationError("CRECI inválido. Use o formato do conselho, ex.: CRECI/MT 12345-F.")
    uf = achado.group(1) or uf_padrao
    if uf not in UFS:
        raise ValidationError(f"UF do CRECI inválida: {uf}.")
    return f"CRECI/{uf} {achado.group(2)}-{achado.group(3)}"


def normalizar_whatsapp(texto: str) -> str:
    """WhatsApp brasileiro em E.164: "(65) 99999-0001" → "+5565999990001".

    Aceita com ou sem +55. Celular: DDD + 9 dígitos começando com 9; fixo: DDD + 8.
    """
    digitos = re.sub(r"\D", "", texto or "")
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) not in (10, 11) or digitos[0] == "0" or (len(digitos) == 11 and digitos[2] != "9"):
        raise ValidationError("WhatsApp inválido. Informe DDD e número, ex.: (65) 99999-0000.")
    return f"+55{digitos}"
