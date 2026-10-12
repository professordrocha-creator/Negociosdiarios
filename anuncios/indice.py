"""Índice de busca do anúncio (Sprint 4B): o que a busca por texto enxerga.

`busca` (SearchVectorField, config pt_unaccent: português sem acento) recebe o título com peso A e o
resto (descrição, cidade, bairro, tipo, negócio; no veículo, marca, modelo, versão, cor e combustível)
com peso B. `texto_busca` guarda o mesmo conteúdo curto sem acento e em minúsculas, para a busca por
semelhança (pg_trgm) pegar erros de digitação e começo de palavra.

Recalculado a cada gravação do anúncio ou da ficha (`anuncios.receptores`) com UPDATE direto (sem
disparar sinais nem histórico).
"""

from __future__ import annotations

import unicodedata

from django.contrib.postgres.search import SearchVector
from django.db.models import TextField, Value

CONFIG = "pt_unaccent"


def sem_acento(texto: str) -> str:
    """ "Tangará da Serra" → "tangara da serra"."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def partes_do_anuncio(anuncio) -> tuple[str, str, str]:
    """(título, resto para o vetor, texto curto para o trigram)."""
    extras = [anuncio.cidade.nome, anuncio.bairro.nome if anuncio.bairro_id else ""]
    curtos = [anuncio.titulo, *extras]
    if anuncio.categoria == "veiculo":
        veiculo = getattr(anuncio, "veiculo", None)
        if veiculo is not None:
            versao = veiculo.versao
            modelo = versao.modelo
            identificacao = [modelo.marca.nome, modelo.nome, versao.nome, modelo.get_tipo_display()]
            extras += [*identificacao, veiculo.get_cor_display(), veiculo.get_combustivel_display()]
            curtos += identificacao[:3]
    else:
        imovel = getattr(anuncio, "imovel", None)
        if imovel is not None:
            extras += [imovel.get_tipo_display(), imovel.get_modalidade_display()]
            curtos += [imovel.get_tipo_display()]
    resto = " ".join(filter(None, [anuncio.descricao or "", *extras]))
    return anuncio.titulo, resto, sem_acento(" ".join(filter(None, curtos)))


def atualizar(anuncio) -> None:
    """Grava `busca` e `texto_busca` do anúncio (UPDATE direto)."""
    titulo, resto, curto = partes_do_anuncio(anuncio)
    vetor = SearchVector(Value(titulo, output_field=TextField()), config=CONFIG, weight="A") + SearchVector(
        Value(resto, output_field=TextField()), config=CONFIG, weight="B"
    )
    type(anuncio)._default_manager.filter(pk=anuncio.pk).update(busca=vetor, texto_busca=curto)


def reindexar_todos() -> int:
    """Recalcula o índice de todos os anúncios (comando `reindexar_busca`). Devolve quantos."""
    from anuncios.models import Anuncio

    total = 0
    consulta = Anuncio.objects.select_related(
        "cidade", "bairro", "imovel", "veiculo__versao__modelo__marca"
    ).iterator(chunk_size=500)
    for anuncio in consulta:
        atualizar(anuncio)
        total += 1
    return total
