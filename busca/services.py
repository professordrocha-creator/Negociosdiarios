"""Regras da busca (ARQUITETURA §6): quais anúncios aparecem para os filtros, a busca por texto,
a ordem, os textos de SEO, os "chips" dos filtros ativos e as URLs (canônica e do sitemap).

Só entram anúncios visíveis (`anuncios.services.anuncios_visiveis`: publicados, de loja ativa, em
cidade liberada). A busca por texto usa o índice `Anuncio.busca` (PostgreSQL, português sem acento)
e, para erros de digitação, a semelhança de palavras (pg_trgm) em `Anuncio.texto_busca`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Count, F, Q, QuerySet
from django.urls import reverse

from anuncios.indice import CONFIG, sem_acento
from anuncios.models import Anuncio, DetalheImovel, DetalheVeiculo
from anuncios.services import anuncios_visiveis
from busca.forms import SO_APRESENTACAO
from catalogo.models import TipoVeiculo
from core.models import Bairro, Cidade, Estado

POR_PAGINA = 24
CATEGORIA = {"imoveis": Anuncio.Categoria.IMOVEL, "veiculos": Anuncio.Categoria.VEICULO}
ORDENACAO = {
    "recentes": ("-publicado_em", "-pk"),
    "menor_preco": ("preco", "-publicado_em"),
    "maior_preco": ("-preco", "-publicado_em"),
}
# Mais filtros de conteúdo que isto (ou busca por texto): página boa para quem busca, ruim para o Google.
MAXIMO_FILTROS_INDEXAVEIS = 2

PLURAL_IMOVEL = {
    "casa": "Casas",
    "apartamento": "Apartamentos",
    "kitnet": "Kitnets",
    "terreno": "Terrenos",
    "chacara": "Chácaras",
    "sitio": "Sítios",
    "fazenda": "Fazendas",
    "sala_comercial": "Salas comerciais",
    "barracao": "Barracões",
}
PLURAL_VEICULO = {"carro": "Carros", "caminhonete": "Caminhonetes", "moto": "Motos", "caminhao": "Caminhões"}


# --- Cidades ----------------------------------------------------------------------------------


def cidades_liberadas() -> QuerySet[Cidade]:
    """Cidades que podem aparecer na busca (liberadas, de estado liberado)."""
    return Cidade.objects.filter(liberada=True, uf__liberado=True).select_related("uf").order_by("nome")


def cidade_da_url(uf: str, slug: str) -> Cidade | None:
    """A cidade de /imoveis/<uf>/<cidade>/ (None se não existe ou não está liberada)."""
    return cidades_liberadas().filter(uf_id=uf.upper(), slug=slug).first()


def cidade_escolhida(valor: str) -> Cidade | None:
    """Valor do seletor de cidade ("mt/tangara-da-serra"; vazio = todas)."""
    if valor.count("/") != 1:
        return None
    uf, slug = valor.split("/")
    return cidade_da_url(uf, slug)


def caminho(categoria: str, cidade: Cidade | None) -> str:
    """/imoveis/ ou /imoveis/mt/tangara-da-serra/."""
    if cidade is None:
        return reverse(f"busca:{categoria}")
    return reverse(f"busca:{categoria}_cidade", args=[cidade.uf_id.lower(), cidade.slug])


# --- Opções que dependem dos anúncios no ar ---------------------------------------------------


def _base(categoria: str, cidade: Cidade | None) -> QuerySet[Anuncio]:
    """Anúncios visíveis da categoria (e da cidade)."""
    anuncios = anuncios_visiveis().filter(categoria=CATEGORIA[categoria])
    return anuncios.filter(cidade=cidade) if cidade else anuncios


def opcoes(categoria: str, cidade: Cidade | None, marca: str = "") -> dict[str, list[tuple[str, str]]]:
    """Escolhas dos selects que dependem do banco: bairros (com anúncio), marcas e modelos (com anúncio)."""
    base = _base(categoria, cidade)
    if categoria == "imoveis":
        bairros = (
            Bairro.objects.filter(anuncios__in=base).distinct().order_by("nome").values_list("slug", "nome")
            if cidade
            else []
        )
        return {"bairro": list(bairros)}
    marcas = (
        base.values_list("veiculo__versao__modelo__marca__slug", "veiculo__versao__modelo__marca__nome")
        .distinct()
        .order_by("veiculo__versao__modelo__marca__nome")
    )
    modelos = []
    if marca:
        modelos = (
            base.filter(veiculo__versao__modelo__marca__slug=marca)
            .values_list("veiculo__versao__modelo__slug", "veiculo__versao__modelo__nome")
            .distinct()
            .order_by("veiculo__versao__modelo__nome")
        )
    return {"marca": list(marcas), "modelo": list(modelos)}


# --- Consulta ---------------------------------------------------------------------------------


def _filtrar_texto(anuncios: QuerySet[Anuncio], termo: str) -> QuerySet[Anuncio]:
    """Texto: busca completa em português sem acento OU palavra parecida (erros de digitação)."""
    consulta = SearchQuery(termo, config=CONFIG, search_type="websearch")
    return anuncios.filter(
        Q(busca=consulta) | Q(texto_busca__trigram_word_similar=sem_acento(termo))
    ).annotate(relevancia=SearchRank(F("busca"), consulta))


def buscar(categoria: str, cidade: Cidade | None, filtros: dict) -> QuerySet[Anuncio]:
    """Anúncios visíveis que atendem aos filtros, na ordem pedida (texto sem ordem = mais relevantes)."""
    anuncios = _base(categoria, cidade)
    if termo := filtros.get("q"):
        anuncios = _filtrar_texto(anuncios, termo)
    if "preco_min" in filtros:
        anuncios = anuncios.filter(preco__gte=filtros["preco_min"])
    if "preco_max" in filtros:
        anuncios = anuncios.filter(preco__lte=filtros["preco_max"])
    if categoria == "imoveis":
        anuncios = _filtros_imovel(anuncios, filtros)
    else:
        anuncios = _filtros_veiculo(anuncios, filtros)
    if "ordem" not in filtros and "q" in filtros:
        return anuncios.order_by("-relevancia", "-publicado_em")
    return anuncios.order_by(*ORDENACAO[filtros.get("ordem", "recentes")])


def _filtros_imovel(anuncios: QuerySet[Anuncio], filtros: dict) -> QuerySet[Anuncio]:
    """Negócio, tipo, bairro, quartos, vagas e área."""
    if "modalidade" in filtros:
        anuncios = anuncios.filter(imovel__modalidade=filtros["modalidade"])
    if "tipo" in filtros:
        anuncios = anuncios.filter(imovel__tipo__in=filtros["tipo"])
    if "bairro" in filtros:
        anuncios = anuncios.filter(bairro__slug=filtros["bairro"])
    if "quartos" in filtros:
        anuncios = anuncios.filter(imovel__quartos__gte=int(filtros["quartos"]))
    if "vagas" in filtros:
        anuncios = anuncios.filter(imovel__vagas__gte=int(filtros["vagas"]))
    if "area_min" in filtros:
        anuncios = anuncios.filter(imovel__area_total__gte=filtros["area_min"])
    if "area_max" in filtros:
        anuncios = anuncios.filter(imovel__area_total__lte=filtros["area_max"])
    return anuncios


def _filtros_veiculo(anuncios: QuerySet[Anuncio], filtros: dict) -> QuerySet[Anuncio]:
    """Tipo, marca, modelo, ano, km, câmbio e combustível."""
    if "tipo" in filtros:
        anuncios = anuncios.filter(veiculo__versao__modelo__tipo__in=filtros["tipo"])
    if "marca" in filtros:
        anuncios = anuncios.filter(veiculo__versao__modelo__marca__slug=filtros["marca"])
    if "modelo" in filtros:
        anuncios = anuncios.filter(veiculo__versao__modelo__slug=filtros["modelo"])
    if "ano_min" in filtros:
        anuncios = anuncios.filter(veiculo__ano_modelo__gte=filtros["ano_min"])
    if "ano_max" in filtros:
        anuncios = anuncios.filter(veiculo__ano_modelo__lte=filtros["ano_max"])
    if "km_max" in filtros:
        anuncios = anuncios.filter(veiculo__quilometragem__lte=filtros["km_max"])
    if "cambio" in filtros:
        anuncios = anuncios.filter(veiculo__cambio__in=filtros["cambio"])
    if "combustivel" in filtros:
        anuncios = anuncios.filter(veiculo__combustivel__in=filtros["combustivel"])
    return anuncios


# --- URLs, SEO e chips ------------------------------------------------------------------------


def querystring(filtros: dict, sem: set[str] | None = None) -> str:
    """Parâmetros na ordem dos campos (listas viram o parâmetro repetido). `sem` tira chaves."""
    pares = []
    for nome, valor in filtros.items():
        if sem and nome in sem:
            continue
        for item in valor if isinstance(valor, list) else [valor]:
            pares.append((nome, str(item)))
    return urlencode(pares)


def url(categoria: str, cidade: Cidade | None, filtros: dict, sem: set[str] | None = None) -> str:
    """Caminho + parâmetros."""
    parametros = querystring(filtros, sem)
    return caminho(categoria, cidade) + (f"?{parametros}" if parametros else "")


def url_canonica(categoria: str, cidade: Cidade | None, filtros: dict) -> str:
    """Sem ordem nem página (são a mesma lista, só apresentada de outro jeito)."""
    return url(categoria, cidade, filtros, sem=SO_APRESENTACAO)


def indexavel(filtros: dict) -> bool:
    """Indexar só combinações simples: sem texto e no máximo 2 filtros de conteúdo."""
    if "q" in filtros:
        return False
    conteudo = [v for k, v in filtros.items() if k not in SO_APRESENTACAO]
    total = sum(len(v) if isinstance(v, list) else 1 for v in conteudo)
    return total <= MAXIMO_FILTROS_INDEXAVEIS


def _um_so(filtros: dict, chave: str) -> str | None:
    """O valor do filtro se for exatamente um (para o título)."""
    valor = filtros.get(chave)
    if isinstance(valor, list):
        return valor[0] if len(valor) == 1 else None
    return valor


def local(cidade: Cidade | None) -> str:
    """ "em Tangará da Serra – MT", "em Mato Grosso" (um estado só) ou vazio."""
    if cidade:
        return f" em {cidade.nome} – {cidade.uf_id}"
    estados = list(Estado.objects.filter(liberado=True).values_list("nome", flat=True)[:2])
    return f" em {estados[0]}" if len(estados) == 1 else ""


def titulo(categoria: str, cidade: Cidade | None, filtros: dict, rotulos: dict) -> str:
    """Ex.: "Casas à venda em Tangará da Serra – MT", "Caminhonetes Toyota Hilux à venda em Mato Grosso"."""
    tipo = _um_so(filtros, "tipo")
    if categoria == "imoveis":
        base = PLURAL_IMOVEL.get(tipo, "Imóveis")
        negocio = {"venda": " à venda", "aluguel": " para alugar"}.get(filtros.get("modalidade", ""), "")
        return f"{base}{negocio}{local(cidade)}"
    base = PLURAL_VEICULO.get(tipo, "Veículos")
    for chave in ("marca", "modelo"):
        if chave in filtros:
            base += f" {rotulos.get(chave, {}).get(filtros[chave], '')}".rstrip()
    return f"{base} à venda{local(cidade)}"


def descricao(categoria: str, titulo_pagina: str, total: int) -> str:
    """Meta description: quantidade e a promessa do site (lojas verificadas, WhatsApp direto)."""
    coisa = "imóveis" if categoria == "imoveis" else "veículos"
    quantidade = f"{total} anúncio{'s' if total != 1 else ''}" if total else "Anúncios"
    return (
        f"{titulo_pagina}: {quantidade} de {coisa} de corretores e lojas verificados. "
        "Veja fotos e fale direto com o anunciante pelo WhatsApp."
    )


@dataclass(frozen=True)
class Chip:
    """Um filtro ativo: o rótulo e a URL sem ele (o "x")."""

    rotulo: str
    url_sem: str


def chips(categoria: str, cidade: Cidade | None, filtros: dict, rotulos: dict) -> list[Chip]:
    """Filtros ativos com o link para tirar cada um (valor por valor nas listas). A cidade também."""
    resultado = []
    sem_pagina = {k: v for k, v in filtros.items() if k != "pagina"}
    if cidade:
        resultado.append(Chip(cidade.nome, url(categoria, None, sem_pagina)))
    for nome, valor in sem_pagina.items():
        if nome == "ordem":
            continue
        for item in valor if isinstance(valor, list) else [valor]:
            restante = dict(sem_pagina)
            if isinstance(valor, list):
                restante[nome] = [v for v in valor if v != item]
                if not restante[nome]:
                    restante.pop(nome)
            else:
                restante.pop(nome)
            resultado.append(Chip(_rotulo_chip(nome, item, rotulos), url(categoria, cidade, restante)))
    return resultado


def _rotulo_chip(nome: str, valor, rotulos: dict) -> str:
    """Texto do chip (ex.: "Casa", "2+ quartos", "Até R$ 500.000", "“hilux”")."""
    from core.templatetags.nd import area, km, moeda

    formatos = {
        "quartos": lambda: f"{valor}+ quartos",
        "vagas": lambda: f"{valor}+ vagas",
        "preco_min": lambda: f"A partir de {moeda(valor)}",
        "preco_max": lambda: f"Até {moeda(valor)}",
        "area_min": lambda: f"A partir de {area(valor)}",
        "area_max": lambda: f"Até {area(valor)}",
        "ano_min": lambda: f"De {valor}",
        "ano_max": lambda: f"Até {valor}",
        "km_max": lambda: f"Até {km(valor)}",
        "q": lambda: f"“{valor}”",
    }
    if nome in formatos:
        return formatos[nome]()
    return rotulos.get(nome, {}).get(str(valor), str(valor))


def rotulos(categoria: str, opcoes_banco: dict) -> dict[str, dict[str, str]]:
    """Valor → texto de cada filtro de escolha (para chips e título)."""
    if categoria == "imoveis":
        fixos = {
            "modalidade": dict(DetalheImovel.Modalidade.choices),
            "tipo": dict(DetalheImovel.Tipo.choices),
        }
    else:
        fixos = {
            "tipo": dict(TipoVeiculo.choices),
            "cambio": dict(DetalheVeiculo.Cambio.choices),
            "combustivel": dict(DetalheVeiculo.Combustivel.choices),
        }
    return {**fixos, **{nome: dict(escolhas) for nome, escolhas in opcoes_banco.items()}}


# --- Sitemap ----------------------------------------------------------------------------------


def paginas_do_sitemap() -> list[str]:
    """Páginas de busca com anúncio: todas as cidades, cada cidade e cidade + tipo (+ negócio no imóvel)."""
    paginas = []
    for categoria in CATEGORIA:
        base = _base(categoria, None)
        if not base.exists():
            continue
        paginas.append(caminho(categoria, None))
        cidades = {c.pk: c for c in cidades_liberadas()}
        por_cidade = base.values("cidade").annotate(total=Count("pk")).order_by("cidade")
        for linha in por_cidade:
            paginas.append(caminho(categoria, cidades[linha["cidade"]]))
        if categoria == "imoveis":
            combinacoes = base.values_list("cidade", "imovel__modalidade", "imovel__tipo").distinct()
            for cidade_id, modalidade, tipo in sorted(combinacoes):
                paginas.append(url(categoria, cidades[cidade_id], {"modalidade": modalidade, "tipo": [tipo]}))
        else:
            combinacoes = base.values_list("cidade", "veiculo__versao__modelo__tipo").distinct()
            for cidade_id, tipo in sorted(combinacoes):
                paginas.append(url(categoria, cidades[cidade_id], {"tipo": [tipo]}))
    return paginas
