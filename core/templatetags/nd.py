"""Tags de template do site (carregar com `{% load nd %}`)."""

import json
from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.html import _json_script_escapes, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def moeda(valor: Decimal | int | str | None) -> str:
    """Preço em reais no padrão brasileiro: 420000 → "R$ 420.000"; 1234.5 → "R$ 1.234,50".

    Sem centavos quando o valor é inteiro (como nos classificados). Vazio para None.
    Feito à mão (e não com o locale do servidor) para não depender da máquina.
    """
    if valor is None or valor == "":
        return ""
    numero = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, centavos = divmod(abs(numero), 1)
    texto = f"{int(inteiro):,}".replace(",", ".")
    if centavos:
        texto += "," + f"{centavos:.2f}"[2:]
    return f"{'-' if numero < 0 else ''}R$ {texto}"


@register.filter
def telefone(e164: str | None) -> str:
    """Telefone legível: "+5565999990000" → "(65) 99999-0000". Outros formatos voltam como vieram."""
    digitos = "".join(c for c in (e164 or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) in (12, 13):
        ddd, numero = digitos[2:4], digitos[4:]
        return f"({ddd}) {numero[:-4]}-{numero[-4:]}"
    return e164 or ""


@register.filter
def link_whatsapp(e164: str | None) -> str:
    """Link de conversa no WhatsApp: "+5565999990000" → "https://wa.me/5565999990000"."""
    digitos = "".join(c for c in (e164 or "") if c.isdigit())
    return f"https://wa.me/{digitos}" if digitos else ""


@register.filter
def cnpj(digitos: str | None) -> str:
    """CNPJ formatado: "12345678000190" → "12.345.678/0001-90"."""
    d = "".join(c for c in (digitos or "") if c.isdigit())
    if len(d) != 14:
        return digitos or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


@register.filter
def area(valor: Decimal | int | str | None) -> str:
    """Área em m² no padrão brasileiro; a partir de 10.000 m², em hectares.

    180 → "180 m²"; 1200 → "1.200 m²"; 120.5 → "120,5 m²"; 20000 → "2 ha"; 25000 → "2,5 ha".
    """
    if valor is None or valor == "":
        return ""
    numero = Decimal(str(valor))
    if numero >= 10000:
        return f"{numero / 10000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " ha"
    inteiro, fracao = divmod(numero, 1)
    texto = f"{int(inteiro):,}".replace(",", ".")
    if fracao:
        texto += "," + f"{fracao:.2f}"[2:].rstrip("0")
    return f"{texto} m²"


@register.simple_tag
def icone(nome: str, classe: str = "ico") -> str:
    """Ícone do sprite SVG (`templates/_icones.html`), ex.: `{% icone "casa" %}`.

    Usa `format_html`, que escapa os argumentos: seguro mesmo se um dia o nome
    vier de uma variável.
    """
    return format_html('<svg class="{}" aria-hidden="true"><use href="#i-{}"></use></svg>', classe, nome)


@register.filter
def json_ld(dados: dict) -> str:
    """Bloco <script type="application/ld+json"> (schema.org) seguro para dados digitados pelo usuário.

    Usa a mesma tabela de escape do `json_script` do Django: <, > e & viram \u003c etc., então
    nenhum texto (ex.: "sobre" da loja) consegue fechar o <script>. O mark_safe é sobre o JSON
    JÁ escapado para esse contexto (é o que o próprio json_script faz); o tipo ld+json é o que os
    buscadores leem, e o json_script do Django só gera "application/json".
    """
    texto = json.dumps(dados, cls=DjangoJSONEncoder, ensure_ascii=False).translate(_json_script_escapes)
    return format_html('<script type="application/ld+json">{}</script>', mark_safe(texto))  # noqa: S308
