"""Tags de template do site (carregar com `{% load nd %}`)."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icone(nome: str, classe: str = "ico") -> str:
    """Ícone do sprite SVG (`templates/_icones.html`), ex.: `{% icone "casa" %}`.

    Usa `format_html`, que escapa os argumentos: seguro mesmo se um dia o nome
    vier de uma variável.
    """
    return format_html('<svg class="{}" aria-hidden="true"><use href="#i-{}"></use></svg>', classe, nome)
