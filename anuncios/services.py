"""Regras do app anuncios (ARQUITETURA §5): publicar dentro do limite do plano, moderação,
expiração e renovação, pausa (pelo anunciante, por atraso ou por downgrade), exclusão lógica e fotos.

Views só orquestram: toda mudança de situação passa por aqui. Quem chama sempre entrega um
anúncio já filtrado pelo dono (`anuncios_do_dono`), nunca um id solto (sem IDOR).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import Max, Prefetch, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from anunciantes.models import Anunciante
from anuncios.localizacao import RAIO_APROXIMADO_M
from anuncios.models import Anuncio, DetalheImovel, DetalheVeiculo, Foto
from core import imagens
from core.models import Configuracao
from core.services import configuracao, enviar_email_modelo

if TYPE_CHECKING:
    from contas.models import Usuario

logger = logging.getLogger(__name__)

Situacao = Anuncio.Situacao
PausadoPor = Anuncio.PausadoPor

# Tamanhos gerados de cada foto (ARQUITETURA §8): nome do campo → largura em px.
SAIDAS_FOTO = {"imagem": 1600, "miniatura": 400}
# O navegador reduz fotos maiores que isto antes de enviar (static/js/reduzir-fotos.js): folga sobre os
# 1600 px gerados aqui, envio rápido no 4G. Parâmetro técnico (não é limite para o anunciante).
LADO_MAXIMO_NO_NAVEGADOR = 2560


class AnuncioIncompleto(Exception):
    """Falta algo para enviar o anúncio (a mensagem lista o quê)."""


# --- Consultas (sempre a partir do dono) --------------------------------------------------


def anuncios_do_dono(anunciante: Anunciante) -> QuerySet[Anuncio]:
    """Anúncios da loja que o dono pode ver e editar (os excluídos somem do painel)."""
    return (
        Anuncio.objects.filter(anunciante=anunciante)
        .exclude(situacao=Situacao.REMOVIDO)
        .select_related("cidade", "cidade__uf", "bairro", "imovel", "veiculo__versao__modelo__marca")
        .prefetch_related(Prefetch("fotos", queryset=Foto.objects.order_by("ordem", "pk")))
    )


def contar_no_plano(anunciante: Anunciante) -> int:
    """Quantos anúncios ocupam o plano: publicados + em análise (pausados e rascunhos não contam)."""
    return Anuncio.objects.filter(anunciante=anunciante, situacao__in=Anuncio.SITUACOES_NO_PLANO).count()


def ids_no_plano(anunciante: Anunciante) -> list[int]:
    """Ids dos anúncios que ocupam o plano (para a escolha do downgrade)."""
    return list(
        Anuncio.objects.filter(anunciante=anunciante, situacao__in=Anuncio.SITUACOES_NO_PLANO)
        .order_by("-publicado_em", "-criado_em")
        .values_list("pk", flat=True)
    )


def precisa_moderacao(anunciante: Anunciante) -> bool:
    """O envio vai para a fila de moderação? Regra em Configuracao.moderacao (padrão: só o primeiro).

    "Primeiro" = a loja nunca teve anúncio publicado (publicado_em fica gravado mesmo depois de
    pausar, expirar ou excluir, então excluir o primeiro não reabre a moderação).
    """
    regra = configuracao().moderacao
    if regra == Configuracao.Moderacao.TODOS:
        return True
    if regra == Configuracao.Moderacao.NENHUM:
        return False
    return not Anuncio.objects.filter(anunciante=anunciante, publicado_em__isnull=False).exists()


def pendencias(anuncio: Anuncio) -> list[str]:
    """O que falta para enviar para publicação (lista vazia = pode enviar)."""
    faltas = []
    detalhe = anuncio.detalhe
    if detalhe is None:
        faltas.append(
            "Preencha os dados do veículo." if anuncio.e_veiculo else "Preencha os dados do imóvel."
        )
        return faltas
    if not anuncio.descricao.strip():
        faltas.append("Escreva a descrição do anúncio.")
    if anuncio.e_veiculo:
        pass  # veículo não tem mapa: a cidade basta (o endereço exibido é o da loja, se ela permitir)
    elif detalhe.exibir_localizacao == DetalheImovel.ExibirLocalizacao.SO_BAIRRO:
        if not anuncio.bairro_id:
            faltas.append('Escolha o bairro (a localização no site é "só o bairro").')
    elif not detalhe.ponto:
        faltas.append('Marque o ponto no mapa ou escolha mostrar "só o bairro".')
    if not any(foto.imagem for foto in anuncio.fotos.all()):
        faltas.append("Envie pelo menos uma foto (e espere ela ficar pronta).")
    return faltas


# --- Criar e editar -----------------------------------------------------------------------

# O que cada tipo de loja anuncia: CRECI = imóveis; revenda, concessionária e garagem = veículos.
CATEGORIAS_POR_TIPO = {
    Anunciante.Tipo.CORRETOR_AUTONOMO: (Anuncio.Categoria.IMOVEL,),
    Anunciante.Tipo.IMOBILIARIA: (Anuncio.Categoria.IMOVEL,),
    Anunciante.Tipo.REVENDA: (Anuncio.Categoria.VEICULO,),
    Anunciante.Tipo.CONCESSIONARIA: (Anuncio.Categoria.VEICULO,),
    Anunciante.Tipo.GARAGEM: (Anuncio.Categoria.VEICULO,),
}


PLURAL_DA_CATEGORIA = {Anuncio.Categoria.IMOVEL: "imóveis", Anuncio.Categoria.VEICULO: "veículos"}


class CategoriaNaoPermitida(ValueError):
    """A loja tentou anunciar fora do seu ramo (ex.: corretor anunciando veículo)."""


def categorias_permitidas(anunciante: Anunciante) -> tuple[str, ...]:
    """O que a loja pode anunciar, pelo tipo dela (corretor/imobiliária: imóvel; revendas: veículo)."""
    return tuple(CATEGORIAS_POR_TIPO.get(anunciante.tipo, ()))


def conferir_categoria(anunciante: Anunciante, categoria: str) -> None:
    """CategoriaNaoPermitida se a categoria não é do ramo da loja (vale também para URL montada à mão)."""
    if categoria not in categorias_permitidas(anunciante):
        nomes = " e ".join(PLURAL_DA_CATEGORIA[c] for c in categorias_permitidas(anunciante))
        raise CategoriaNaoPermitida(
            f"{anunciante.get_tipo_display()} anuncia só {nomes or 'o que o plano permitir'}."
        )


def criar_anuncio_imovel(anunciante: Anunciante, dados: dict, ficha: dict) -> Anuncio:
    """Cria o rascunho do imóvel (cidade padrão = a da loja; muda na etapa de localização).

    `dados` tem os campos do Anuncio (titulo, descricao, preco); `ficha`, os do DetalheImovel.
    Anúncio de loja demo nasce demo (some no apagar_dados_demo). Só loja de imóveis (CRECI/imobiliária).
    """
    conferir_categoria(anunciante, Anuncio.Categoria.IMOVEL)
    with transaction.atomic():
        anuncio = Anuncio(
            anunciante=anunciante,
            categoria=Anuncio.Categoria.IMOVEL,
            cidade=anunciante.cidade,
            demo=anunciante.demo,
            **dados,
        )
        anuncio.slug = slugify(anuncio.titulo)[:140]
        anuncio._change_reason = "Rascunho criado pelo anunciante."
        anuncio.save()
        DetalheImovel.objects.create(anuncio=anuncio, **ficha)
    return anuncio


def titulo_do_veiculo(versao, ano_modelo: int) -> str:
    """Título sugerido quando o anunciante não escreve um: "Toyota Hilux CD SRV 4x4 2.8 Diesel Aut. 2020"."""
    return f"{versao.modelo.marca.nome} {versao.modelo.nome} {versao.nome} {ano_modelo}"[:120]


def criar_anuncio_veiculo(anunciante: Anunciante, dados: dict, ficha: dict) -> Anuncio:
    """Cria o rascunho do veículo (código ND-VE-...). Sem título, usa marca, modelo, versão e ano.

    `dados` tem os campos do Anuncio (titulo, descricao, preco, cidade); `ficha`, os do DetalheVeiculo.
    Só loja de veículos (revenda, concessionária, garagem).
    """
    conferir_categoria(anunciante, Anuncio.Categoria.VEICULO)
    with transaction.atomic():
        dados = {"cidade": anunciante.cidade, **dados}
        if not dados.get("titulo"):
            dados["titulo"] = titulo_do_veiculo(ficha["versao"], ficha["ano_modelo"])
        anuncio = Anuncio(
            anunciante=anunciante, categoria=Anuncio.Categoria.VEICULO, demo=anunciante.demo, **dados
        )
        anuncio.slug = slugify(anuncio.titulo)[:140]
        anuncio._change_reason = "Rascunho criado pelo anunciante."
        anuncio.save()
        DetalheVeiculo.objects.create(anuncio=anuncio, **ficha)
    return anuncio


def atualizar_anuncio(anuncio: Anuncio, dados: dict, ficha: dict | None = None, motivo: str = "") -> Anuncio:
    """Grava as mudanças do formulário (dados ou localização) no anúncio e na ficha.

    Com a moderação de "todos os anúncios", editar um anúncio publicado o devolve para a
    análise (o conteúdo mudou). Com "só o primeiro", a edição vale na hora.
    """
    with transaction.atomic():
        for campo, valor in dados.items():
            setattr(anuncio, campo, valor)
        if anuncio.e_veiculo and not anuncio.titulo and ficha:
            anuncio.titulo = titulo_do_veiculo(ficha["versao"], ficha["ano_modelo"])
        anuncio.slug = slugify(anuncio.titulo)[:140]
        if (
            anuncio.situacao == Situacao.PUBLICADO
            and configuracao().moderacao == Configuracao.Moderacao.TODOS
        ):
            anuncio.situacao = Situacao.EM_MODERACAO
        anuncio._change_reason = motivo or "Editado pelo anunciante."
        anuncio.save()
        if ficha:
            detalhe = anuncio.detalhe
            for campo, valor in ficha.items():
                setattr(detalhe, campo, valor)
            detalhe.save()
    return anuncio


def ponto(latitude: float | None, longitude: float | None) -> Point | None:
    """Point do PostGIS (x = longitude, y = latitude, WGS 84) ou None."""
    if latitude is None or longitude is None:
        return None
    return Point(longitude, latitude, srid=4326)


# --- Publicar, moderar, pausar, renovar, excluir ------------------------------------------


def _prazo(agora: datetime) -> datetime:
    """Data de expiração de um anúncio publicado agora (Configuracao.expiracao_dias, padrão 60)."""
    return agora + timedelta(days=configuracao().expiracao_dias)


def _publicar(anuncio: Anuncio, agora: datetime, motivo: str) -> None:
    """Põe no ar com novo prazo (publicado_em só na primeira vez: a "idade" do anúncio não muda)."""
    anuncio.situacao = Situacao.PUBLICADO
    anuncio.pausado_por = ""
    anuncio.publicado_em = anuncio.publicado_em or agora
    anuncio.expira_em = _prazo(agora)
    anuncio._change_reason = motivo
    anuncio.save()


def enviar_para_publicacao(anuncio: Anuncio, agora: datetime | None = None) -> str:
    """Rascunho → moderação ou publicado, só se couber no plano (trava da Sprint 2).

    Usa `planos.services.reservar_vaga`: a contagem e a mudança acontecem com a assinatura
    travada, então dois envios ao mesmo tempo nunca passam do limite. Levanta
    AnuncioIncompleto, SemAssinaturaAtiva ou LimiteDoPlano. Devolve a situação final.
    """
    from planos.services import reservar_vaga

    if anuncio.situacao != Situacao.RASCUNHO:
        raise ValueError("Só rascunhos são enviados para publicação.")
    faltas = pendencias(anuncio)
    if faltas:
        raise AnuncioIncompleto(" ".join(faltas))
    agora = agora or timezone.now()
    anunciante = anuncio.anunciante
    moderar = precisa_moderacao(anunciante)

    def gravar() -> str:
        if moderar:
            anuncio.situacao = Situacao.EM_MODERACAO
            anuncio.motivo_moderacao = ""
            anuncio._change_reason = "Enviado para análise."
            anuncio.save()
        else:
            _publicar(anuncio, agora, "Publicado pelo anunciante (sem moderação).")
        return anuncio.situacao

    situacao = reservar_vaga(
        anunciante, contar=lambda _assinatura: contar_no_plano(anunciante), publicar=gravar
    )
    if moderar:
        _avisar_moderacao(anuncio)
    return situacao


def _avisar_moderacao(anuncio: Anuncio) -> None:
    """E-mail para moderadores e superusuários: tem anúncio na fila."""
    from anunciantes.services import destinatarios_equipe

    enviar_email_modelo(
        "anuncio_moderacao_equipe",
        "Anúncio aguardando moderação",
        destinatarios_equipe(),
        {
            "anuncio": anuncio,
            "link_admin": settings.SITE_URL
            + reverse("admin:anuncios_anuncioemmoderacao_change", args=[anuncio.pk]),
        },
    )


def aprovar(anuncio: Anuncio, por: Usuario | None, agora: datetime | None = None) -> Anuncio:
    """Moderação aprovada: publica (ou deixa pausado, se a assinatura estiver em atraso) e avisa.

    O anúncio já ocupava a vaga desde o envio (em análise conta no plano).
    """
    from planos.services import assinatura_de

    if anuncio.situacao != Situacao.EM_MODERACAO:
        raise ValueError(f"{anuncio.codigo}: não está em análise.")
    agora = agora or timezone.now()
    anuncio.moderado_por = por
    anuncio.motivo_moderacao = ""
    anuncio._history_user = por
    assinatura = assinatura_de(anuncio.anunciante)
    if assinatura is None or assinatura.situacao != assinatura.Situacao.ATIVA:
        anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, PausadoPor.ATRASO
        anuncio.publicado_em = anuncio.publicado_em or agora  # já foi aprovado: não volta à fila
        anuncio._change_reason = "Aprovado na moderação; pausado porque a assinatura não está ativa."
        anuncio.save()
    else:
        _publicar(anuncio, agora, "Aprovado na moderação.")
    enviar_email_modelo(
        "anuncio_aprovado",
        "Seu anúncio foi aprovado",
        [anuncio.anunciante.usuario.email],
        {"anuncio": anuncio, "link_painel": settings.SITE_URL + reverse("anunciantes:painel")},
    )
    return anuncio


def recusar(anuncio: Anuncio, por: Usuario | None, motivo: str) -> Anuncio:
    """Moderação recusada: volta a rascunho com o motivo (o anunciante corrige e reenvia). Avisa."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da recusa (o anunciante vai ler).")
    if anuncio.situacao != Situacao.EM_MODERACAO:
        raise ValueError(f"{anuncio.codigo}: não está em análise.")
    anuncio.situacao = Situacao.RASCUNHO
    anuncio.motivo_moderacao = motivo.strip()
    anuncio.moderado_por = por
    anuncio._history_user = por
    anuncio._change_reason = f"Recusado na moderação: {motivo.strip()}"[:100]
    anuncio.save()
    enviar_email_modelo(
        "anuncio_recusado",
        "Seu anúncio precisa de ajustes",
        [anuncio.anunciante.usuario.email],
        {
            "anuncio": anuncio,
            "link_editar": settings.SITE_URL + reverse("anuncios:editar", args=[anuncio.codigo]),
        },
    )
    return anuncio


def pausar(anuncio: Anuncio, por: str = PausadoPor.CLIENTE) -> Anuncio:
    """Tira do ar sem perder nada; libera a vaga do plano. Só anúncio publicado."""
    if anuncio.situacao != Situacao.PUBLICADO:
        raise ValueError("Só anúncios publicados podem ser pausados.")
    anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, por
    anuncio._change_reason = f"Pausado ({PausadoPor(por).label.lower()})."
    anuncio.save()
    return anuncio


def reativar(anuncio: Anuncio, agora: datetime | None = None) -> Anuncio:
    """Pausado → publicado de novo, se couber no plano (mesma trava do envio).

    Pausa por atraso só sai com o pagamento (`reativar_apos_pagamento`). O prazo de 60 dias
    recomeça (o anúncio ficou fora do ar).
    """
    from planos.services import reservar_vaga

    if anuncio.situacao != Situacao.PAUSADO:
        raise ValueError("Só anúncios pausados podem ser reativados.")
    if anuncio.pausado_por == PausadoPor.ATRASO:
        raise ValueError("Este anúncio volta sozinho quando o pagamento for registrado.")
    if anuncio.pausado_por == PausadoPor.DENUNCIA:
        raise ValueError(
            "Este anúncio está em revisão pela equipe por causa de denúncias. Aguarde o resultado."
        )
    agora = agora or timezone.now()
    anunciante = anuncio.anunciante
    reservar_vaga(
        anunciante,
        contar=lambda _assinatura: contar_no_plano(anunciante),
        publicar=lambda: _publicar(anuncio, agora, "Reativado pelo anunciante."),
    )
    return anuncio


def pode_renovar(anuncio: Anuncio) -> bool:
    """Renovar aparece no expirado e no publicado perto de expirar (Configuracao.aviso_expiracao_dias)."""
    if anuncio.situacao == Situacao.EXPIRADO:
        return True
    dias = anuncio.dias_para_expirar
    return dias is not None and dias <= configuracao().aviso_expiracao_dias


def renovar(anuncio: Anuncio, agora: datetime | None = None) -> Anuncio:
    """Mais um prazo inteiro, sem custo. Expirado precisa de vaga no plano (não contava mais)."""
    from planos.services import reservar_vaga

    if not pode_renovar(anuncio):
        raise ValueError("A renovação fica disponível perto da data de expiração.")
    agora = agora or timezone.now()
    if anuncio.situacao == Situacao.PUBLICADO:
        anuncio.expira_em = _prazo(agora)
        anuncio._change_reason = "Renovado pelo anunciante."
        anuncio.save()
        return anuncio
    anunciante = anuncio.anunciante
    reservar_vaga(
        anunciante,
        contar=lambda _assinatura: contar_no_plano(anunciante),
        publicar=lambda: _publicar(anuncio, agora, "Renovado pelo anunciante (estava expirado)."),
    )
    return anuncio


def excluir(anuncio: Anuncio) -> Anuncio:
    """Exclusão lógica: sai do painel e do site, mas o registro e o histórico ficam (CLAUDE.md)."""
    if anuncio.situacao == Situacao.REMOVIDO:
        return anuncio
    anuncio.situacao = Situacao.REMOVIDO
    anuncio.removido_em = timezone.now()
    anuncio._change_reason = "Excluído pelo anunciante."
    anuncio.save()
    return anuncio


def expirar_vencidos(agora: datetime | None = None) -> int:
    """Tarefa diária: publicado com prazo vencido → expirado (nunca apagado) e e-mail por loja."""
    agora = agora or timezone.now()
    vencidos = list(
        Anuncio.objects.filter(situacao=Situacao.PUBLICADO, expira_em__lte=agora).select_related(
            "anunciante__usuario"
        )
    )
    por_loja: dict[int, list[Anuncio]] = {}
    for anuncio in vencidos:
        anuncio.situacao = Situacao.EXPIRADO
        anuncio._change_reason = "Expirou (prazo de publicação acabou)."
        anuncio.save(update_fields=["situacao", "atualizado_em"])
        por_loja.setdefault(anuncio.anunciante_id, []).append(anuncio)
    for anuncios in por_loja.values():
        enviar_email_modelo(
            "anuncios_expirados",
            "Anúncios expirados: renove com um clique",
            [anuncios[0].anunciante.usuario.email],
            {"anuncios": anuncios, "link_painel": settings.SITE_URL + reverse("anunciantes:painel")},
        )
    return len(vencidos)


# --- Ligações com o app planos (sinais e downgrade) ----------------------------------------


def pausar_por_atraso(anunciante: Anunciante) -> int:
    """Assinatura em atraso: todos os publicados ficam pausados (nunca apagados). Devolve quantos."""
    publicados = Anuncio.objects.filter(anunciante=anunciante, situacao=Situacao.PUBLICADO)
    total = 0
    for anuncio in publicados:
        anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, PausadoPor.ATRASO
        anuncio._change_reason = "Pausado: assinatura em atraso."
        anuncio.save(update_fields=["situacao", "pausado_por", "atualizado_em"])
        total += 1
    return total


def reativar_apos_pagamento(anunciante: Anunciante, agora: datetime | None = None) -> int:
    """Pagamento registrado: os pausados POR ATRASO voltam (os pausados pelo cliente, não).

    Quem já passou do prazo enquanto estava pausado volta como expirado (pede Renovar).
    """
    agora = agora or timezone.now()
    pausados = Anuncio.objects.filter(
        anunciante=anunciante, situacao=Situacao.PAUSADO, pausado_por=PausadoPor.ATRASO
    )
    total = 0
    for anuncio in pausados:
        vencido = anuncio.expira_em is not None and anuncio.expira_em <= agora
        anuncio.situacao = Situacao.EXPIRADO if vencido else Situacao.PUBLICADO
        anuncio.pausado_por = ""
        anuncio.expira_em = anuncio.expira_em or _prazo(agora)  # aprovado em atraso: ganha o prazo agora
        anuncio._change_reason = "Pagamento registrado: anúncio de volta."
        anuncio.save(update_fields=["situacao", "pausado_por", "expira_em", "atualizado_em"])
        total += 1
    return total


def pausar_por_downgrade(anunciante: Anunciante, ids: Iterable[int]) -> int:
    """Troca para plano menor: os não escolhidos saem do plano.

    Publicado → pausado (o anunciante reativa se couber); em análise → rascunho (reenviar depois).
    Só mexe em anúncios DESTA loja (ids de outra loja são ignorados).
    """
    total = 0
    for anuncio in Anuncio.objects.filter(anunciante=anunciante, pk__in=list(ids)):
        if anuncio.situacao == Situacao.PUBLICADO:
            anuncio.situacao, anuncio.pausado_por = Situacao.PAUSADO, PausadoPor.DOWNGRADE
        elif anuncio.situacao == Situacao.EM_MODERACAO:
            anuncio.situacao = Situacao.RASCUNHO
        else:
            continue
        anuncio._change_reason = "Fora do plano novo (troca para plano menor)."
        anuncio.save(update_fields=["situacao", "pausado_por", "atualizado_em"])
        total += 1
    return total


# --- Fotos --------------------------------------------------------------------------------


def vagas_de_foto(anuncio: Anuncio) -> int:
    """Quantas fotos ainda cabem (Configuracao.max_fotos_anuncio, padrão 10)."""
    return max(configuracao().max_fotos_anuncio - anuncio.fotos.count(), 0)


def adicionar_fotos(anuncio: Anuncio, arquivos: list) -> list[Foto]:
    """Guarda os envios (já validados pelo formulário) no fim da fila e devolve as fotos criadas.

    Quem chama agenda `anuncios.tasks.processar_foto` para cada uma (WebP fora da requisição).
    Recusa se passar do limite de fotos.
    """
    if len(arquivos) > vagas_de_foto(anuncio):
        raise ValueError(
            f"Cada anúncio tem no máximo {configuracao().max_fotos_anuncio} fotos. "
            f"Ainda cabem {vagas_de_foto(anuncio)}."
        )
    proxima = (anuncio.fotos.aggregate(maior=Max("ordem"))["maior"] or 0) + 1 if anuncio.fotos.exists() else 0
    fotos = []
    for indice, arquivo in enumerate(arquivos):
        foto = Foto(anuncio=anuncio, ordem=proxima + indice)
        foto.original.save(arquivo.name, arquivo, save=False)
        foto.save()
        fotos.append(foto)
    return fotos


def processar_foto(foto: Foto) -> bool:
    """Gera os WebP 1600 e 400 e o JPEG de compartilhamento (sem EXIF, na posição certa); apaga o envio.

    Roda no Celery. Se a imagem não abrir, a foto é descartada (o log não leva dados pessoais).
    """
    if not foto.original:
        return False
    try:
        with foto.original.open("rb") as arquivo:
            limpa = imagens.abrir_limpa(arquivo)
    except Exception:
        logger.exception("Foto de anúncio não pôde ser processada (foto id=%s).", foto.pk)
        foto.original.delete(save=False)
        foto.delete()
        return False
    foto.largura, foto.altura = limpa.size
    for campo, largura in SAIDAS_FOTO.items():
        getattr(foto, campo).save(f"{campo}.webp", imagens.webp(limpa, largura, campo), save=False)
    foto.compartilhamento.save(
        "compartilhamento.jpg", imagens.jpeg_compartilhamento(limpa, "compartilhamento"), save=False
    )
    foto.original.delete(save=False)  # o original nunca é servido (docs/SEGURANCA.md)
    foto.save()
    return True


def marcar_fotos_pequenas(fotos: list[Foto]) -> list[Foto]:
    """Liga `foto.pequena` abaixo de Configuracao.foto_aviso_* (aceita, mas pode aparecer borrada)."""
    config = configuracao()
    for foto in fotos:
        foto.pequena = bool(
            foto.largura
            and foto.altura
            and (foto.largura < config.foto_aviso_largura_px or foto.altura < config.foto_aviso_altura_px)
        )
    return fotos


def _renumerar(anuncio: Anuncio, ids_em_ordem: list[int]) -> None:
    """Grava ordem 0, 1, 2… seguindo a lista (a primeira vira a capa)."""
    for posicao, foto_id in enumerate(ids_em_ordem):
        Foto.objects.filter(anuncio=anuncio, pk=foto_id).update(ordem=posicao)


def reordenar_fotos(anuncio: Anuncio, ids: list[int]) -> None:
    """Nova ordem vinda do arrastar. Precisa ter exatamente as fotos deste anúncio."""
    atuais = list(anuncio.fotos.order_by("ordem", "pk").values_list("pk", flat=True))
    if sorted(ids) != sorted(atuais):
        raise ValueError("A lista de fotos mudou. Recarregue a página e tente de novo.")
    _renumerar(anuncio, ids)


def mover_foto(anuncio: Anuncio, foto_id: int, passo: int) -> None:
    """Sobe (-1) ou desce (+1) uma posição: alternativa ao arrastar (teclado, celular, sem JS)."""
    ids = list(anuncio.fotos.order_by("ordem", "pk").values_list("pk", flat=True))
    if foto_id not in ids:
        raise ValueError("Foto não encontrada neste anúncio.")
    atual = ids.index(foto_id)
    novo = min(max(atual + passo, 0), len(ids) - 1)
    ids.insert(novo, ids.pop(atual))
    _renumerar(anuncio, ids)


def excluir_foto(anuncio: Anuncio, foto_id: int) -> None:
    """Apaga a foto e os arquivos (foto removida pelo anunciante não fica guardada: LGPD §4)."""
    foto = anuncio.fotos.filter(pk=foto_id).first()
    if foto is None:
        raise ValueError("Foto não encontrada neste anúncio.")
    for campo in ("original", "imagem", "miniatura", "compartilhamento"):
        arquivo = getattr(foto, campo)
        if arquivo:
            arquivo.delete(save=False)
    foto.delete()
    _renumerar(anuncio, list(anuncio.fotos.order_by("ordem", "pk").values_list("pk", flat=True)))


# --- Demonstração ---------------------------------------------------------------------------


def apagar_anuncios_demo() -> int:
    """Apaga anúncios demo (e de lojas demo), fotos, arquivos e histórico. Devolve quantos eram.

    Chamado pelo `core.services.apagar_dados_demo` antes de apagar os anunciantes demo
    (Anuncio.anunciante é PROTECT).
    """
    with transaction.atomic():
        anuncios = Anuncio.objects.filter(anunciante__demo=True) | Anuncio.objects.filter(demo=True)
        for foto in Foto.objects.filter(anuncio__in=anuncios):
            for campo in ("original", "imagem", "miniatura", "compartilhamento"):
                arquivo = getattr(foto, campo)
                if arquivo:
                    arquivo.delete(save=False)
        ids = list(anuncios.values_list("pk", flat=True))
        Anuncio.objects.filter(pk__in=ids).delete()
        Anuncio.history.filter(id__in=ids).delete()
        DetalheImovel.history.filter(anuncio_id__in=ids).delete()
    return len(ids)


# --- Vitrine pública (Parte B) --------------------------------------------------------------


def anuncios_visiveis() -> QuerySet[Anuncio]:
    """O que o público vê: publicados, de loja visível (ativa, área atendida; demo só com MOSTRAR_DEMO)
    e em cidade liberada de estado liberado."""
    from anunciantes.services import lojas_visiveis

    return (
        Anuncio.objects.filter(
            situacao=Situacao.PUBLICADO,
            anunciante__in=lojas_visiveis(),
            cidade__liberada=True,
            cidade__uf__liberado=True,
        )
        .select_related(
            "anunciante",
            "anunciante__cidade",
            "cidade",
            "cidade__uf",
            "bairro",
            "imovel",
            "veiculo__versao__modelo__marca",
        )
        .prefetch_related(Prefetch("fotos", queryset=Foto.objects.order_by("ordem", "pk")))
    )


def visivel(anuncio: Anuncio) -> bool:
    """O anúncio aparece para o público agora?"""
    return anuncios_visiveis().filter(pk=anuncio.pk).exists()


def url_publica(anuncio: Anuncio) -> str:
    """Caminho canônico: /anuncio/<codigo>-<slug>/ (slug atual; o antigo redireciona para este)."""
    return reverse("anuncios:publico", kwargs={"codigo": anuncio.codigo, "slug": anuncio.slug})


def localizacao_publica(anuncio: Anuncio) -> dict | None:
    """O que vai para o mapa da página do anúncio, conforme `exibir_localizacao` (docs/LGPD.md §4).

    Usa o `ponto_publico` (anuncios/localizacao.py): exata → marcador no ponto; aproximada → círculo
    de ~300 m em volta do ponto já deslocado (o ponto real nunca vai para o HTML); só o bairro → None.
    """
    if anuncio.e_veiculo:
        return None  # veículo não tem mapa (a página mostra o endereço da loja, se ela permitir)
    imovel = getattr(anuncio, "imovel", None)
    if imovel is None or imovel.ponto_publico is None:
        return None
    publico = imovel.ponto_publico
    if imovel.exibir_localizacao == DetalheImovel.ExibirLocalizacao.EXATA:
        return {"tipo": "exata", "lat": publico.y, "lng": publico.x}
    return {"tipo": "aproximada", "lat": publico.y, "lng": publico.x, "raio": RAIO_APROXIMADO_M}


def mensagem_whatsapp(anuncio: Anuncio) -> str:
    """Mensagem pronta do botão: cita o código para o anunciante saber de qual anúncio se trata."""
    return (
        f"Olá! Vi no {configuracao().nome} o anúncio {anuncio.codigo} ({anuncio.titulo}) "
        "e quero mais informações."
    )


def link_whatsapp(anuncio: Anuncio) -> str:
    """wa.me com o número da loja e a mensagem pronta (só montado no redirecionamento, nunca no HTML)."""
    from urllib.parse import quote

    numero = anuncio.anunciante.whatsapp.lstrip("+")
    return f"https://wa.me/{numero}?text={quote(mensagem_whatsapp(anuncio))}"


def para_vitrine(anuncio: Anuncio):
    """Converte para o AnuncioVitrine do card (os mesmos campos que o demo.json usava na 4c)."""
    from core.services import AnuncioVitrine

    detalhe = anuncio.detalhe
    fotos = [foto for foto in anuncio.fotos.all() if foto.imagem]
    if anuncio.e_veiculo:
        finalidade, tipo = "venda", detalhe.versao.modelo.get_tipo_display()
    else:
        finalidade, tipo = detalhe.modalidade, detalhe.get_tipo_display()
    return AnuncioVitrine(
        titulo=anuncio.titulo,
        categoria=anuncio.categoria,
        finalidade=finalidade,
        tipo=tipo,
        preco=anuncio.preco,
        cidade=anuncio.cidade.nome,
        bairro=anuncio.bairro.nome if anuncio.bairro else "",
        resumo=detalhe.resumo,
        loja_nome=anuncio.anunciante.nome_publico,
        loja_slug=anuncio.anunciante.slug,
        destaque=bool(anuncio.destaque_ate and anuncio.destaque_ate > timezone.now()),
        fotos=len(fotos),
        estilo_foto="f1",
        publicado_em=anuncio.publicado_em,
        url=url_publica(anuncio),
        capa=fotos[0].miniatura.url if fotos else "",
    )


def mais_da_loja(anuncio: Anuncio, limite: int = 4) -> list[Anuncio]:
    """Outros anúncios visíveis da mesma loja, mais novos primeiro."""
    return list(
        anuncios_visiveis()
        .filter(anunciante_id=anuncio.anunciante_id)
        .exclude(pk=anuncio.pk)
        .order_by("-publicado_em")[:limite]
    )


def parecidos(anuncio: Anuncio, limite: int = 4) -> list[Anuncio]:
    """Anúncios visíveis da mesma cidade e do mesmo tipo (de imóvel ou de veículo); completa com a cidade."""
    base = (
        anuncios_visiveis()
        .filter(cidade_id=anuncio.cidade_id)
        .exclude(pk=anuncio.pk)
        .order_by("-publicado_em")
    )
    detalhe = anuncio.detalhe
    if anuncio.e_veiculo and detalhe:
        mesmo_tipo = base.filter(veiculo__versao__modelo__tipo=detalhe.tipo)
    elif detalhe:
        mesmo_tipo = base.filter(imovel__tipo=detalhe.tipo)
    else:
        mesmo_tipo = base.none()
    mesmos = list(mesmo_tipo[:limite])
    if len(mesmos) < limite:
        mesmos += list(base.exclude(pk__in=[a.pk for a in mesmos])[: limite - len(mesmos)])
    return mesmos
