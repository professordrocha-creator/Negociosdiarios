"""Tags de template do site (carregar com `{% load nd %}`)."""

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.utils.html import format_html

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


@register.simple_tag
def icone(nome: str, classe: str = "ico") -> str:
    """Ícone do sprite SVG (`templates/_icones.html`), ex.: `{% icone "casa" %}`.

    Usa `format_html`, que escapa os argumentos: seguro mesmo se um dia o nome
    vier de uma variável.
    """
    return format_html('<svg class="{}" aria-hidden="true"><use href="#i-{}"></use></svg>', classe, nome)
