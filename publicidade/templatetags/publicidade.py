"""Tag {% publicidade "posicao" %}: mostra a peça sorteada (rodízio) da posição e conta a impressão.

Uso: `{% load publicidade %}{% publicidade "home_topo" %}`;
com cidade: `{% publicidade "busca_topo" cidade %}`.
A escolha e a contagem ficam em `publicidade.services`; aqui só se monta o contexto do parcial.
"""

from django import template

from publicidade import services
from publicidade.models import FORMATO_DA_POSICAO, Formato, Posicao

register = template.Library()

VAGAS = {Posicao.RODAPE_CARD: 3}  # o rodapé da home tem 3 cards; as outras posições, 1 peça


@register.inclusion_tag("publicidade/_espaco.html", takes_context=True)
def publicidade(context, posicao: str, cidade=None) -> dict:
    """Peça(s) da posição, com o rótulo "Publicidade", e +1 impressão para cada uma (sem robôs, sem HTMX)."""
    request = context.get("request")
    pecas = services.escolher(posicao, cidade, quantos=VAGAS.get(posicao, 1))
    for peca in pecas:
        services.registrar(peca, services.IMPRESSOES, request)
    t = services.tamanhos()
    return {
        "pecas": pecas,
        "posicao": posicao,
        "formato": FORMATO_DA_POSICAO[posicao],
        "BANNER": Formato.BANNER,
        "CARD": Formato.CARD,
        "tamanho": t["banner"],
        "tamanho_celular": t["banner_celular"],
        "tamanho_card": t["card"],
    }
