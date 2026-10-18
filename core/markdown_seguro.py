"""Conversor de Markdown simples e SEGURO para o manual da equipe (docs/MANUAL_ADMIN.md em /painel/ajuda/).

Por que próprio (e não uma biblioteca): o manual usa só um pedaço do Markdown (títulos, parágrafos, listas
com um nível de sublista, tabelas, citação, linha, negrito, código e links) e nenhuma biblioteca de Markdown
está instalada. Regra de segurança: TODO texto do arquivo passa por `escape` antes de qualquer marcação;
HTML escrito no arquivo aparece como texto (nunca é interpretado). Links só para "#", "/", http(s) e mailto.
"""

import re
import unicodedata

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

LISTA = re.compile(r"^(?P<recuo> *)(?P<marca>-|\d+\.) (?P<texto>.*)$")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
DESTINOS_PERMITIDOS = ("#", "/", "https://", "http://", "mailto:")


def ancora(titulo: str) -> str:
    """ "9. LGPD: pedidos, exclusão" → "9-lgpd-pedidos-exclusao" (o mesmo formato dos links do sumário)."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", titulo) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def _inline(texto: str) -> str:
    """Escapa o texto e só então aplica `código`, **negrito** e [links](destino seguro)."""
    partes = re.split(r"(`[^`]+`)", texto)  # dentro do código nada mais é interpretado
    saida = []
    for parte in partes:
        if parte.startswith("`") and parte.endswith("`") and len(parte) > 1:
            saida.append(f"<code>{escape(parte[1:-1])}</code>")
            continue
        html = escape(parte)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

        def _link(achado: re.Match) -> str:
            rotulo, destino = achado.group(1), achado.group(2)
            if not destino.startswith(DESTINOS_PERMITIDOS):
                return achado.group(0)  # destino estranho (javascript:...): fica como texto
            return f'<a href="{destino}">{rotulo}</a>'  # já escapados acima

        saida.append(LINK.sub(_link, html))
    return "".join(saida)


def _tabela(linhas: list[str]) -> str:
    """| a | b | (cabeçalho, separador, linhas) → <table> com rolagem no celular."""
    celulas = [[c.strip() for c in linha.strip().strip("|").split("|")] for linha in linhas]
    cabecalho, corpo = celulas[0], [c for c in celulas[2:] if c]
    html = ['<div class="table-responsive"><table class="table table-sm align-top"><thead><tr>']
    html += [f'<th scope="col">{_inline(c)}</th>' for c in cabecalho]
    html.append("</tr></thead><tbody>")
    for linha in corpo:
        html.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in linha) + "</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def _lista(linhas: list[str]) -> str:
    """Lista numerada ou com marcadores, com um nível de sublista (itens recuados) e linhas de continuação."""
    itens: list[dict] = []
    for linha in linhas:
        achado = LISTA.match(linha)
        if achado and len(achado["recuo"]) >= 2 and itens:
            itens[-1]["sub"].append({"texto": achado["texto"], "ordenada": achado["marca"] != "-"})
        elif achado:
            itens.append({"texto": achado["texto"], "ordenada": achado["marca"] != "-", "sub": []})
        elif itens:  # continuação: vai para o último item (ou subitem)
            alvo = itens[-1]["sub"][-1] if itens[-1]["sub"] else itens[-1]
            alvo["texto"] += " " + linha.strip()
    etiqueta = "ol" if itens and itens[0]["ordenada"] else "ul"
    html = [f"<{etiqueta}>"]
    for item in itens:
        html.append(f"<li>{_inline(item['texto'])}")
        if item["sub"]:
            sub = "ol" if item["sub"][0]["ordenada"] else "ul"
            html.append(
                f"<{sub}>" + "".join(f"<li>{_inline(s['texto'])}</li>" for s in item["sub"]) + f"</{sub}>"
            )
        html.append("</li>")
    html.append(f"</{etiqueta}>")
    return "".join(html)


def markdown_para_html(texto: str) -> SafeString:
    """Converte o Markdown do manual em HTML seguro (ver a docstring do módulo). Títulos ganham âncora."""
    linhas = texto.replace("\r\n", "\n").split("\n")
    html: list[str] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip():
            i += 1
            continue
        titulo = re.match(r"^(#{1,4}) (.+)$", linha)
        if titulo:
            nivel, conteudo = len(titulo.group(1)), titulo.group(2).strip()
            html.append(f'<h{nivel} id="{ancora(conteudo)}">{_inline(conteudo)}</h{nivel}>')
            i += 1
        elif linha.strip() == "---":
            html.append("<hr>")
            i += 1
        elif linha.startswith("|"):
            bloco = []
            while i < len(linhas) and linhas[i].startswith("|"):
                bloco.append(linhas[i])
                i += 1
            html.append(_tabela(bloco))
        elif linha.startswith(">"):
            bloco = []
            while i < len(linhas) and linhas[i].startswith(">"):
                bloco.append(linhas[i].lstrip(">").strip())
                i += 1
            html.append(f'<blockquote class="nd-ajuda-nota">{_inline(" ".join(bloco))}</blockquote>')
        elif LISTA.match(linha):
            bloco = []
            while (
                i < len(linhas)
                and linhas[i].strip()
                and (LISTA.match(linhas[i]) or linhas[i].startswith(" "))
            ):
                bloco.append(linhas[i])
                i += 1
            html.append(_lista(bloco))
        else:
            bloco = []
            while i < len(linhas) and linhas[i].strip() and not re.match(r"^(#{1,4} |\||>|---$)", linhas[i]):
                if LISTA.match(linhas[i]):
                    break
                bloco.append(linhas[i].strip())
                i += 1
            html.append(f"<p>{_inline(' '.join(bloco))}</p>")
    # Seguro: cada pedaço de texto do arquivo passou por escape() em _inline; a marcação é só a gerada acima.
    return mark_safe("\n".join(html))  # noqa: S308
