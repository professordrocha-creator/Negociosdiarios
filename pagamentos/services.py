"""Regras da cobrança manual assistida (Sprint 6; docs/PAGAMENTOS.md, ARQUITETURA §5 regra 2).

Ciclo de uma fatura:
1. `gerar_faturas` (rotina diária): X dias antes do vencimento da assinatura
   (`Configuracao.fatura_antecedencia_dias`) cria a fatura do próximo ciclo e manda "fatura disponível".
2. O anunciante paga pelo Pix estático (copia e cola + QR Code, `pagamentos.pix`) ou pelo link de boleto
   e clica em "Já paguei" com o comprovante (`enviar_comprovante`): a fatura fica aguardando confirmação e
   o Financeiro recebe e-mail.
3. A equipe confere no admin: `confirmar_pagamento` (renova a assinatura e, se estava em atraso, reativa os
   anúncios) ou `recusar_comprovante` (motivo por e-mail; a fatura volta a aberta/vencida).
4. Sem pagamento: `marcar_vencidas` no dia seguinte ao vencimento; passada a carência,
   `planos.services.processar_atrasos` põe a assinatura em atraso (anúncios pausados, nunca apagados).
   Comprovante aguardando confirmação segura a pausa até a equipe decidir.
5. Régua de e-mails (`enviar_avisos`): 3 dias antes, no dia, 1 e 3 dias depois. Textos no admin
   (`ModeloEmailCobranca`); cada lembrete sai uma vez só por fatura.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Sum
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from anunciantes.models import Anunciante
from core import imagens
from core.services import configuracao, enviar_email_modelo
from core.templatetags.nd import moeda
from pagamentos import pix
from pagamentos.models import Fatura, ModeloEmailCobranca
from planos.models import Assinatura, Periodicidade
from planos.services import (
    destinatarios_financeiro,
    fim_da_vigencia,
    processar_atrasos,
    proximo_vencimento,
    renovar_assinatura,
)

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

    from contas.models import Usuario

logger = logging.getLogger(__name__)

# Régua de cobrança: (e-mail, dias em relação ao vencimento; negativo = antes).
REGUA = (
    (ModeloEmailCobranca.Chave.LEMBRETE_3_DIAS, -3),
    (ModeloEmailCobranca.Chave.VENCE_HOJE, 0),
    (ModeloEmailCobranca.Chave.VENCIDA_1_DIA, 1),
    (ModeloEmailCobranca.Chave.VENCIDA_3_DIAS, 3),
)
# PDF com conteúdo ativo é recusado (o comprovante de banco nunca precisa disso).
PDF_PERIGOSO = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles?|RichMedia|XFA)\b")
FORMATOS_IMAGEM = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


# --- Consultas ---------------------------------------------------------------------------------


def faturas_da_loja(anunciante: Anunciante) -> QuerySet[Fatura]:
    """Faturas da loja (sempre filtradas pelo anunciante logado: sem IDOR), as mais novas primeiro."""
    return Fatura.objects.filter(assinatura__anunciante=anunciante).select_related("assinatura__plano")


def faturas_em_aberto(anunciante: Anunciante) -> list[Fatura]:
    """Abertas, vencidas e aguardando confirmação, da que vence primeiro para a última."""
    return list(
        faturas_da_loja(anunciante).filter(situacao__in=Fatura.EM_ABERTO).order_by("vencimento", "pk")
    )


def descricao_da_assinatura(assinatura: Assinatura) -> str:
    """Ex.: "Profissional · mensal"."""
    return f"{assinatura.plano.nome} · {assinatura.get_periodicidade_display().lower()}"


def credenciais_pix() -> tuple[str, str, str]:
    """Chave, nome e cidade do recebedor: da "Configuração do Pix" (admin) ou, se a chave estiver vazia lá,
    do .env (PIX_CHAVE, PIX_NOME, PIX_CIDADE; instalações antigas)."""
    config = configuracao()
    if config.pix_chave.strip():
        return config.pix_chave, config.pix_nome, config.pix_cidade
    return settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE


def gerar_pix(valor: Decimal | None, identificador: str) -> dict | None:
    """Pix copia e cola, QR Code (SVG, gerado aqui, sem serviço externo) e a instrução ao cliente.
    None se o Pix não estiver configurado."""
    try:
        codigo = pix.br_code(*credenciais_pix(), valor, identificador)
    except pix.PixNaoConfigurado:
        return None
    return {
        "copia_e_cola": codigo,
        "qr_code": pix.qr_code_svg(codigo),
        "instrucao": configuracao().pix_instrucao,
    }


def dados_pix(fatura: Fatura) -> dict | None:
    """Pix da fatura (valor e identificador dentro). None sem Pix configurado."""
    return gerar_pix(fatura.valor, fatura.identificador_pix)


# --- Geração, vencimento e régua (rotina diária) --------------------------------------------------


def gerar_fatura(assinatura: Assinatura, hoje: date | None = None, avisar: bool = True) -> Fatura | None:
    """Fatura do ciclo que começa no vencimento atual da assinatura, se ainda não existe.

    Vencimento já passado (assinatura antiga, sem fatura) nasce "vencida". Com `avisar`, manda
    "fatura disponível". Devolve None se a fatura do ciclo já existe (idempotente, também com duas
    rotinas ao mesmo tempo: a restrição única do banco decide).
    """
    hoje = hoje or timezone.localdate()
    competencia = assinatura.vencimento
    if (
        assinatura.faturas.filter(competencia=competencia)
        .exclude(situacao=Fatura.Situacao.CANCELADA)
        .exists()
    ):
        return None
    try:
        with transaction.atomic():
            fatura = Fatura.objects.create(
                assinatura=assinatura,
                competencia=competencia,
                periodo_fim=fim_da_vigencia(competencia, assinatura.plano, assinatura.periodicidade),
                descricao=descricao_da_assinatura(assinatura),
                valor=assinatura.valor,
                vencimento=competencia,
                situacao=Fatura.Situacao.VENCIDA if competencia < hoje else Fatura.Situacao.ABERTA,
                demo=assinatura.demo,
            )
    except IntegrityError:
        return None
    if avisar:
        avisar_cliente(fatura, ModeloEmailCobranca.Chave.FATURA_DISPONIVEL)
    return fatura


def gerar_faturas(hoje: date | None = None) -> int:
    """Gera a fatura de cada assinatura (não cancelada) que vence em até X dias e ainda não tem a do ciclo."""
    hoje = hoje or timezone.localdate()
    limite = hoje + timedelta(days=configuracao().fatura_antecedencia_dias)
    ja_tem = Fatura.objects.filter(assinatura=OuterRef("pk"), competencia=OuterRef("vencimento")).exclude(
        situacao=Fatura.Situacao.CANCELADA
    )
    pendentes = (  # pedido ainda não aprovado (lote 3B) não gera fatura de renovação
        Assinatura.objects.exclude(situacao__in=[Assinatura.Situacao.CANCELADA, Assinatura.Situacao.PENDENTE])
        .filter(vencimento__lte=limite)
        .filter(~Exists(ja_tem))
        .select_related("plano", "anunciante__usuario")
    )
    return sum(1 for assinatura in pendentes if gerar_fatura(assinatura, hoje))


def marcar_vencidas(hoje: date | None = None) -> int:
    """Fatura aberta com vencimento antes de hoje vira "vencida" (com histórico)."""
    hoje = hoje or timezone.localdate()
    total = 0
    for fatura in Fatura.objects.filter(situacao=Fatura.Situacao.ABERTA, vencimento__lt=hoje):
        fatura.situacao = Fatura.Situacao.VENCIDA
        fatura._change_reason = f"Vencida em {fatura.vencimento:%d/%m/%Y} sem pagamento."
        fatura.save(update_fields=["situacao", "atualizado_em"])
        total += 1
    return total


def enviar_avisos(hoje: date | None = None) -> int:
    """Régua: lembrete 3 dias antes, no dia, 1 e 3 dias depois, só para faturas ainda a pagar.

    Recupera dia perdido: se a rotina não rodou (beat parado), no dia seguinte sai o lembrete que ficou
    devendo. Se vários ficaram para trás, sai só o mais recente (os anteriores são dados como tratados,
    para o cliente não receber uma rajada de e-mails). Aguardando confirmação não recebe cobrança. Cada
    lembrete sai uma vez por fatura (`avisos_enviados`). Devolve quantos e-mails saíram.
    """
    hoje = hoje or timezone.localdate()
    antecedencia = -min(dias for _, dias in REGUA)
    faturas = (
        Fatura.objects.filter(
            situacao__in=Fatura.A_PAGAR, vencimento__lte=hoje + timedelta(days=antecedencia)
        )
        .exclude(assinatura__situacao=Assinatura.Situacao.PENDENTE)  # pedido pelo site: sem régua de cobrança
        .select_related("assinatura__anunciante__usuario", "campanha__patrocinador")
    )
    total = 0
    for fatura in faturas:
        devidos = [
            chave.value
            for chave, dias in REGUA
            if hoje >= fatura.vencimento + timedelta(days=dias) and chave.value not in fatura.avisos_enviados
        ]
        if not devidos:
            continue
        total += avisar_cliente(fatura, devidos[-1])
        pulados = [chave for chave in devidos[:-1] if chave not in fatura.avisos_enviados]
        if pulados:  # tratados sem e-mail: o mais recente já cobre
            Fatura.objects.filter(pk=fatura.pk).update(avisos_enviados=[*fatura.avisos_enviados, *pulados])
    return total


def rotina_de_cobranca(hoje: date | None = None) -> dict[str, int]:
    """A rotina diária, nesta ordem: gerar faturas, marcar vencidas, atrasos (pausa) e lembretes."""
    hoje = hoje or timezone.localdate()
    resultado = {
        "geradas": gerar_faturas(hoje),
        "vencidas": marcar_vencidas(hoje),
        "em_atraso": processar_atrasos(hoje),
        "avisos": enviar_avisos(hoje),
    }
    logger.info("Rotina de cobrança: %s", resultado)  # só números: nada de dado pessoal no log
    return resultado


# --- E-mails ao anunciante (textos no admin) -------------------------------------------------------


def _preencher(texto: str, valores: dict[str, str]) -> str:
    """Troca {variavel} pelo valor. Só nomes simples: nada de atributos ({x.y}) nem formatação."""
    return re.sub(r"\{(\w+)\}", lambda m: valores.get(m[1], m[0]), texto)


def _data(valor: date | datetime) -> str:
    """dd/mm/aaaa."""
    return f"{valor:%d/%m/%Y}"


def valores_do_email(fatura: Fatura, motivo: str = "") -> dict[str, str]:
    """Variáveis dos e-mails de cobrança."""
    return {
        "loja": fatura.cliente_nome,
        "valor": moeda(fatura.valor),
        "vencimento": _data(fatura.vencimento),
        "competencia": f"{_data(fatura.competencia)} a {_data(fatura.periodo_fim)}",
        "codigo": fatura.codigo or "",
        "link": settings.SITE_URL + fatura.link_pagamento,
        "motivo": motivo,
        "site": configuracao().nome,
    }


def avisar_cliente(fatura: Fatura, chave: str, motivo: str = "") -> int:
    """Manda ao anunciante o e-mail `chave` (texto do admin) e anota em `avisos_enviados`.

    Texto desligado ou inexistente: não envia. Devolve 1 se enviou, 0 se não.
    """
    modelo = ModeloEmailCobranca.objects.filter(chave=chave, ativo=True).first()
    email = fatura.cliente_email
    if modelo is None or not email:
        return 0
    valores = valores_do_email(fatura, motivo)
    send_mail(
        f"{_preencher(modelo.assunto, valores)} · {valores['site']}",
        _preencher(modelo.corpo, valores),
        None,
        [email],
    )
    with transaction.atomic():
        travada = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if chave not in travada.avisos_enviados:
            travada.avisos_enviados = [*travada.avisos_enviados, str(chave)]
            Fatura.objects.filter(pk=fatura.pk).update(avisos_enviados=travada.avisos_enviados)
        fatura.avisos_enviados = travada.avisos_enviados
    return 1


# --- Comprovante ("Já paguei") ------------------------------------------------------------------


def comprovante_limpo(arquivo: UploadedFile) -> ContentFile:
    """Confere e limpa o comprovante: PDF sem conteúdo ativo, ou imagem regravada sem EXIF.

    Limite de tamanho em `Configuracao.limite_comprovante_kb`. Imagem: JPG, PNG ou WebP de verdade
    (Pillow), regravada a partir dos pixels (some o GPS do celular). Levanta ValidationError.
    """
    limite_kb = configuracao().limite_comprovante_kb
    if arquivo.size > limite_kb * 1024:
        raise ValidationError(f"O comprovante pode ter até {limite_kb // 1024} MB.")
    arquivo.seek(0)
    inicio = arquivo.read(5)
    arquivo.seek(0)
    if inicio == b"%PDF-":
        conteudo = arquivo.read()
        if PDF_PERIGOSO.search(conteudo) or b"%%EOF" not in conteudo[-2048:]:
            raise ValidationError(
                "Este PDF não pôde ser aceito. Envie o PDF do banco ou uma foto do comprovante."
            )
        return ContentFile(conteudo, name="comprovante.pdf")
    try:
        with Image.open(arquivo) as original:
            formato = original.format
            original.verify()
    except Exception as erro:  # Pillow levanta vários tipos para arquivo que não é imagem
        raise ValidationError("Envie o comprovante em PDF, JPG, PNG ou WebP.") from erro
    if formato not in FORMATOS_IMAGEM:
        raise ValidationError("Envie o comprovante em PDF, JPG, PNG ou WebP.")
    imagem = imagens.abrir_limpa(arquivo)
    if formato == "JPEG" and imagem.mode not in ("RGB", "L"):
        imagem = imagem.convert("RGB")
    saida = io.BytesIO()
    imagem.save(saida, format=formato, **({"quality": 90} if formato in ("JPEG", "WEBP") else {}))
    return ContentFile(saida.getvalue(), name=f"comprovante{FORMATOS_IMAGEM[formato]}")


def enviar_comprovante(fatura: Fatura, arquivo: UploadedFile | None, recado: str = "") -> Fatura:
    """ "Já paguei": guarda o comprovante (privado), põe a fatura aguardando confirmação e avisa o Financeiro.

    Só fatura aberta ou vencida. Um comprovante recusado antes é substituído (o arquivo antigo é
    apagado; a recusa fica no histórico). Na tela Pagar (lote 3B) o comprovante é opcional (`arquivo`
    None): a equipe confere pelo identificador no extrato. Levanta ValidationError (arquivo) ou ValueError
    (situação).
    """
    limpo = comprovante_limpo(arquivo) if arquivo else None
    with transaction.atomic():
        fatura = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if not fatura.a_pagar:
            raise ValueError("Esta fatura não está esperando pagamento.")
        if limpo is not None:
            if fatura.comprovante:
                fatura.comprovante.delete(save=False)
            fatura.comprovante.save(limpo.name, limpo, save=False)
        fatura.comprovante_enviado_em = timezone.now()
        fatura.situacao = Fatura.Situacao.AGUARDANDO
        fatura.motivo_recusa = ""
        recado = recado.strip()
        if recado:
            fatura.observacao = "\n".join(
                filter(None, [fatura.observacao, f"Anunciante ({timezone.localdate():%d/%m/%Y}): {recado}"])
            )
        fatura._change_reason = (
            "Comprovante enviado pelo anunciante." if limpo else 'Cliente informou o pagamento ("Já paguei").'
        )
        fatura.save()
    link_admin = (  # loja: a tela "Cadastros aguardando" aprova numa tela só; campanha: a fatura
        reverse("admin:pagamentos_pedidoaguardando_changelist")
        if fatura.assinatura_id
        else reverse("admin:pagamentos_fatura_change", args=[fatura.pk])
    )
    enviar_email_modelo(
        "comprovante_recebido_equipe",
        "Pagamento para conferir",
        destinatarios_financeiro(),
        {"fatura": fatura, "recado": recado, "link_admin": settings.SITE_URL + link_admin},
    )
    return fatura


# --- Decisões da equipe ------------------------------------------------------------------------


def confirmar_pagamento(
    fatura: Fatura,
    por: Usuario | None,
    forma: str = Fatura.Forma.PIX,
    observacao: str = "",
    hoje: date | None = None,
) -> Fatura:
    """Baixa a fatura (paga) e renova a assinatura; se estava em atraso, os anúncios voltam (sinal).

    Só renova se a fatura é do ciclo atual (competência a partir do vencimento da assinatura): confirmar
    uma fatura antiga nunca empurra o vencimento duas vezes. Avisa o anunciante por e-mail.
    """
    hoje = hoje or timezone.localdate()
    observacao = observacao.strip()
    with transaction.atomic():
        fatura = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if fatura.situacao not in Fatura.EM_ABERTO:
            raise ValueError(f"{fatura.codigo}: já está {fatura.get_situacao_display().lower()}.")
        fatura.situacao = Fatura.Situacao.PAGA
        fatura.pago_em = timezone.now()
        fatura.forma = forma
        fatura.confirmado_por = por
        if observacao:
            fatura.observacao = "\n".join(filter(None, [fatura.observacao, observacao]))
        fatura._history_user = por
        fatura._change_reason = "Pagamento confirmado pela equipe."
        fatura.save()
        if fatura.assinatura_id:  # fatura de campanha de publicidade não mexe em assinatura
            assinatura = Assinatura.objects.select_for_update().get(pk=fatura.assinatura_id)
            if fatura.competencia >= assinatura.vencimento:
                motivo = f"{fatura.codigo}" + (f" ({observacao})" if observacao else "")
                renovar_assinatura(assinatura, por, motivo, hoje)
    avisar_cliente(fatura, ModeloEmailCobranca.Chave.PAGAMENTO_CONFIRMADO)
    return fatura


def recusar_comprovante(fatura: Fatura, por: Usuario | None, motivo: str, hoje: date | None = None) -> Fatura:
    """Comprovante não confere: a fatura volta a aberta (ou vencida) e o anunciante recebe o motivo."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da recusa.")
    hoje = hoje or timezone.localdate()
    with transaction.atomic():
        fatura = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if fatura.situacao != Fatura.Situacao.AGUARDANDO:
            raise ValueError(f"{fatura.codigo}: não há comprovante aguardando confirmação.")
        fatura.situacao = Fatura.Situacao.VENCIDA if fatura.vencimento < hoje else Fatura.Situacao.ABERTA
        fatura.motivo_recusa = motivo.strip()
        fatura._history_user = por
        fatura._change_reason = f"Comprovante recusado: {motivo.strip()}"[:100]
        fatura.save()
    avisar_cliente(fatura, ModeloEmailCobranca.Chave.COMPROVANTE_RECUSADO, motivo=motivo.strip())
    return fatura


def cancelar_fatura(fatura: Fatura, por: Usuario | None, motivo: str) -> Fatura:
    """Cancela uma fatura ainda não paga (motivo obrigatório; nada é apagado)."""
    if not motivo.strip():
        raise ValueError("Informe o motivo do cancelamento.")
    with transaction.atomic():
        fatura = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if fatura.situacao not in Fatura.EM_ABERTO:
            raise ValueError(f"{fatura.codigo}: já está {fatura.get_situacao_display().lower()}.")
        fatura.situacao = Fatura.Situacao.CANCELADA
        fatura._history_user = por
        fatura._change_reason = f"Cancelada: {motivo.strip()}"[:100]
        fatura.save()
    return fatura


def registrar_pagamento_manual(
    assinatura: Assinatura, por: Usuario | None, motivo: str, hoje: date | None = None
) -> Fatura:
    """ "Registrar pagamento manual" do admin de assinaturas: baixa a fatura em aberto mais antiga da
    loja ou, se não houver, cria a do ciclo atual e já a baixa. Motivo obrigatório (vai para a fatura e
    para o histórico da assinatura)."""
    if not motivo.strip():
        raise ValueError("Informe o motivo/comprovante da baixa manual.")
    hoje = hoje or timezone.localdate()
    fatura = assinatura.faturas.filter(situacao__in=Fatura.EM_ABERTO).order_by(
        "vencimento", "pk"
    ).first() or gerar_fatura(assinatura, hoje, avisar=False)
    if fatura is None:
        raise ValueError(f"{assinatura}: a fatura do ciclo atual já está paga.")
    return confirmar_pagamento(fatura, por, Fatura.Forma.OUTRO, motivo.strip(), hoje)


def gerar_fatura_campanha(campanha, hoje: date | None = None) -> Fatura:
    """Fatura avulsa de uma campanha de publicidade (cobrança manual, Pix estático): o período da campanha,
    o valor dela e vencimento no início (ou hoje, se já começou). Uma por campanha (cancelada não conta).
    Manda "fatura disponível" ao patrocinador com o link da página pública de pagamento."""
    hoje = hoje or timezone.localdate()
    if campanha.faturas.exclude(situacao=Fatura.Situacao.CANCELADA).exists():
        raise ValueError(f"{campanha}: já tem fatura (cancele a anterior para gerar outra).")
    fatura = Fatura.objects.create(
        campanha=campanha,
        competencia=campanha.inicio,
        periodo_fim=campanha.fim,
        descricao=f"Publicidade · {campanha.nome}"[:120],
        valor=campanha.valor,
        vencimento=max(campanha.inicio, hoje),
        demo=campanha.demo,
    )
    avisar_cliente(fatura, ModeloEmailCobranca.Chave.FATURA_DISPONIVEL)
    return fatura


def fatura_publica(token) -> Fatura | None:
    """Fatura de campanha pelo token do link (a de loja só é paga pelo painel, com login)."""
    return (
        Fatura.objects.filter(token=token, campanha__isnull=False)
        .select_related("campanha__patrocinador")
        .first()
    )


def atualizar_fatura_aberta(assinatura: Assinatura) -> int:
    """Troca de plano: a fatura ainda aberta do ciclo atual passa a cobrar o plano novo."""
    total = 0
    for fatura in assinatura.faturas.filter(
        situacao=Fatura.Situacao.ABERTA, competencia__gte=assinatura.vencimento
    ):
        valor, descricao = assinatura.valor, descricao_da_assinatura(assinatura)
        if (fatura.valor, fatura.descricao) == (valor, descricao):
            continue
        fatura.valor, fatura.descricao = valor, descricao
        fatura._change_reason = f"Plano trocado para {descricao}."
        fatura.save(update_fields=["valor", "descricao", "atualizado_em"])
        total += 1
    return total


# --- Pedido de plano pelo site, Pix e aprovação numa tela só (lote 3B) ---------------------------


class LimiteDePedidos(Exception):
    """A loja passou do limite de pedidos de plano por hora (`Configuracao.pedidos_por_hora`)."""


def pedidos_aguardando() -> QuerySet[Fatura]:
    """Lista "Cadastros aguardando": faturas de loja aguardando conferência (o cliente tocou em "Já paguei") e
    as aguardando pagamento de quem pediu o plano pelo site e ainda não tem plano ativo."""
    return Fatura.objects.filter(assinatura__isnull=False).filter(
        Q(situacao=Fatura.Situacao.AGUARDANDO)
        | Q(situacao__in=Fatura.A_PAGAR, assinatura__situacao=Assinatura.Situacao.PENDENTE)
    )


def motivo_sem_pedido(anunciante: Anunciante) -> str | None:
    """Por que a loja NÃO pode fazer um pedido de plano pelo site (None = pode).

    Pode quem ainda não tem plano (cadastro novo, pedido anterior não pago ou recusado, plano cancelado). Quem
    já tem plano troca em "Meu plano" e renova pagando a fatura (a rotina gera a do próximo período).
    """
    if anunciante.status not in (Anunciante.Status.PENDENTE, Anunciante.Status.ATIVO):
        return "Sua loja não pode contratar plano agora. Fale com a gente."
    assinatura = Assinatura.objects.filter(anunciante=anunciante).first()
    if assinatura is None:
        return None
    if assinatura.situacao in (Assinatura.Situacao.ATIVA, Assinatura.Situacao.EM_ATRASO):
        return "Você já tem um plano: para trocar, use Meu plano; para renovar, pague a fatura em Faturas."
    if assinatura.faturas.filter(situacao=Fatura.Situacao.AGUARDANDO).exists():
        return "Seu pagamento está em conferência. Avisaremos por e-mail assim que for aprovado."
    return None


def pedido_em_aberto(anunciante: Anunciante) -> Fatura | None:
    """O pedido de plano ainda não aprovado da loja (aguardando pagamento ou conferência), se houver."""
    return (
        Fatura.objects.filter(
            assinatura__anunciante=anunciante,
            assinatura__situacao=Assinatura.Situacao.PENDENTE,
            situacao__in=Fatura.EM_ABERTO,
        )
        .order_by("-criado_em")
        .first()
    )


def fazer_pedido(
    anunciante: Anunciante,
    plano,
    periodicidade: str,
    hoje: date | None = None,
    checar_limite: bool = True,
) -> Fatura:
    """O cliente escolheu o plano: cria (ou reaproveita) a assinatura "aguardando pagamento" e a fatura do
    pedido, com o valor do plano, para pagar pelo Pix na tela Pagar.

    Um pedido novo substitui o anterior ainda não pago (a fatura antiga é cancelada, com motivo). Limite de
    pedidos por loja por hora (`Configuracao.pedidos_por_hora`; contado no banco, vale para todos os
    processos).
    A assinatura só fica ativa quando a equipe aprovar em "Cadastros aguardando". Levanta ValueError (não pode
    pedir) ou LimiteDePedidos.
    """
    hoje = hoje or timezone.localdate()
    motivo = motivo_sem_pedido(anunciante)
    if motivo:
        raise ValueError(motivo)
    if not plano.ativo:
        raise ValueError("Este plano não está mais à venda.")
    if checar_limite:
        recentes = Fatura.objects.filter(
            assinatura__anunciante=anunciante, criado_em__gte=timezone.now() - timedelta(hours=1)
        ).count()
        if recentes >= configuracao().pedidos_por_hora:
            raise LimiteDePedidos("Muitos pedidos na última hora. Aguarde um pouco e tente de novo.")
    with transaction.atomic():
        assinatura = Assinatura.objects.select_for_update().filter(anunciante=anunciante).first()
        if assinatura is None:
            assinatura = Assinatura(anunciante=anunciante, demo=anunciante.demo)
        assinatura.plano, assinatura.periodicidade = plano, periodicidade
        assinatura.inicio = assinatura.vencimento = hoje  # as datas valem de verdade na aprovação
        assinatura.situacao = Assinatura.Situacao.PENDENTE
        assinatura._change_reason = f"Pedido pelo site: {plano.nome} ({periodicidade})."
        assinatura.save()
        for antiga in assinatura.faturas.filter(situacao__in=Fatura.A_PAGAR):
            cancelar_fatura(antiga, None, "Substituída por um pedido novo.")
        fatura = Fatura(
            assinatura=assinatura,
            competencia=hoje,
            periodo_fim=fim_da_vigencia(hoje, plano, periodicidade),
            descricao=descricao_da_assinatura(assinatura),
            valor=assinatura.valor,
            vencimento=hoje,
            demo=assinatura.demo,
        )
        fatura._change_reason = "Pedido de plano pelo site (aguardando pagamento)."
        fatura.save()
    return fatura


def datas_sugeridas(fatura: Fatura, hoje: date | None = None) -> tuple[date, date]:
    """Início e fim da vigência sugeridos na aprovação (a equipe pode ajustar antes de confirmar).

    Pedido novo (plano ainda não ativo): começa hoje. Renovação (fatura gerada pela rotina): começa na
    competência da fatura, o vencimento anterior, para a loja não perder nem ganhar dias por pagar antes ou
    depois. Fim = início + "dias de vigência" do plano (mensal ou anual).
    """
    hoje = hoje or timezone.localdate()
    assinatura = fatura.assinatura
    novo = assinatura.situacao in (Assinatura.Situacao.PENDENTE, Assinatura.Situacao.CANCELADA)
    inicio = hoje if novo else fatura.competencia
    return inicio, fim_da_vigencia(inicio, assinatura.plano, assinatura.periodicidade)


def aprovar_pedido_pago(
    fatura: Fatura, por: Usuario | None, inicio: date, fim: date, observacao: str = ""
) -> Assinatura:
    """ "Aprovar" de "Cadastros aguardando", tudo de uma vez: fatura paga (Pix), vigência de `inicio` a `fim`
    (o plano permite anúncios novos até `fim`, inclusive), loja aprovada (se estava pendente) e plano ativo.

    Vale também para fatura ainda "aguardando pagamento" (a equipe viu o Pix no banco antes do "Já paguei").
    Se a assinatura estava em atraso, os anúncios pausados voltam (sinal `assinatura_regularizada`). Fica no
    histórico de cada um quem aprovou e quando. Levanta ValueError (datas, situação, loja sem e-mail
    confirmado ou cidade não liberada: nesse caso nada muda). Avisa o cliente com UM e-mail: loja nova recebe
    "aprovada e plano ativo"; renovação, "pagamento confirmado".
    """
    from anunciantes.services import aprovar
    from planos.sinais import assinatura_regularizada

    if fim <= inicio:
        raise ValueError("O fim da vigência precisa ser depois do início.")
    observacao = observacao.strip()
    with transaction.atomic():
        fatura = Fatura.objects.select_for_update().get(pk=fatura.pk)
        if fatura.assinatura_id is None or fatura.situacao not in Fatura.EM_ABERTO:
            raise ValueError(f"{fatura.codigo}: já está {fatura.get_situacao_display().lower()}.")
        assinatura = (
            Assinatura.objects.select_for_update()
            .select_related("anunciante__usuario", "plano")
            .get(pk=fatura.assinatura_id)
        )
        anunciante = assinatura.anunciante
        if anunciante.status not in (Anunciante.Status.PENDENTE, Anunciante.Status.ATIVO):
            raise ValueError(f"{anunciante}: a loja está {anunciante.get_status_display().lower()}.")
        fatura.situacao = Fatura.Situacao.PAGA
        fatura.pago_em = timezone.now()
        fatura.forma = Fatura.Forma.PIX
        fatura.confirmado_por = por
        fatura.competencia, fatura.periodo_fim = inicio, fim
        if observacao:
            fatura.observacao = "\n".join(filter(None, [fatura.observacao, observacao]))
        fatura._history_user = por
        fatura._change_reason = f"Aprovado em Cadastros aguardando: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}."
        try:
            with transaction.atomic():
                fatura.save()
        except IntegrityError as erro:
            raise ValueError(
                f"{fatura.codigo}: já existe outra fatura começando em {inicio:%d/%m/%Y}. Ajuste o início."
            ) from erro
        estava_em_atraso = assinatura.situacao == Assinatura.Situacao.EM_ATRASO
        if assinatura.situacao in (Assinatura.Situacao.PENDENTE, Assinatura.Situacao.CANCELADA):
            assinatura.inicio = inicio
        assinatura.vencimento = fim
        assinatura.situacao = Assinatura.Situacao.ATIVA
        assinatura._history_user = por
        assinatura._change_reason = f"Pagamento {fatura.codigo} aprovado: vigência até {fim:%d/%m/%Y}."
        assinatura.save()
        if estava_em_atraso:
            assinatura_regularizada.send(sender=Assinatura, assinatura=assinatura)
        loja_nova = anunciante.status == Anunciante.Status.PENDENTE
        if loja_nova:  # verificação + pagamento na mesma aprovação
            # Por último: se faltar e-mail confirmado ou cidade liberada, o ValueError desfaz tudo acima.
            aprovar(anunciante, por, f"Documento e pagamento ({fatura.codigo}) conferidos.", avisar=False)
    if loja_nova:  # lote 3C: um e-mail só ("loja aprovada" + "pagamento confirmado")
        enviar_email_modelo(
            "loja_aprovada_plano_ativo",
            "Sua loja foi aprovada e o plano está ativo",
            [anunciante.usuario.email],
            {
                "anunciante": anunciante,
                "fatura": fatura,
                "assinatura": assinatura,
                "link_entrar": settings.SITE_URL + reverse("contas:entrar"),
            },
        )
    else:
        avisar_cliente(fatura, ModeloEmailCobranca.Chave.PAGAMENTO_CONFIRMADO)
    return assinatura


def recusar_pedido_pago(fatura: Fatura, por: Usuario | None, motivo: str) -> Fatura:
    """ "Recusar" de "Cadastros aguardando": cancela a fatura do pedido (motivo obrigatório, no histórico), o
    plano que esperava pagamento fica cancelado e o cliente recebe o motivo por e-mail. Nada é apagado; a loja
    pode fazer um pedido novo."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da recusa.")
    motivo = motivo.strip()
    with transaction.atomic():
        fatura = cancelar_fatura(fatura, por, f"Pedido recusado: {motivo}")
        assinatura = Assinatura.objects.select_for_update().get(pk=fatura.assinatura_id)
        if assinatura.situacao == Assinatura.Situacao.PENDENTE:
            assinatura.situacao = Assinatura.Situacao.CANCELADA
            assinatura._history_user = por
            assinatura._change_reason = f"Pedido recusado: {motivo}"[:100]
            assinatura.save(update_fields=["situacao", "atualizado_em"])
    enviar_email_modelo(
        "pedido_plano_recusado",
        "Seu pedido de plano foi recusado",
        [fatura.cliente_email],
        {
            "fatura": fatura,
            "motivo": motivo,
            "link": settings.SITE_URL + reverse("pagamentos:assinar"),
        },
    )
    return fatura


def marcar_nao_pago(fatura: Fatura, por: Usuario | None, motivo: str) -> Fatura:
    """ "Marcar como não pago": o Pix não apareceu no banco. A fatura volta a "aguardando pagamento" e o
    cliente recebe o motivo (mesma regra e e-mail da recusa de comprovante)."""
    return recusar_comprovante(fatura, por, motivo)


# --- Admin: painel de cobrança ------------------------------------------------------------------


def _soma(faturas: QuerySet[Fatura]) -> dict:
    """Quantas e quanto."""
    dados = faturas.aggregate(quantas=Count("pk"), total=Sum("valor"))
    return {"quantas": dados["quantas"], "total": dados["total"] or Decimal("0")}


def resumo_cobranca(hoje: date | None = None) -> dict[str, dict]:
    """Números do painel de cobrança do admin (com o filtro da lista de faturas de cada um)."""
    hoje = hoje or timezone.localdate()
    inicio_mes = hoje.replace(day=1)
    proximo_mes = (inicio_mes + timedelta(days=32)).replace(day=1)
    faturas = Fatura.objects.all()
    return {
        "a_receber_mes": {
            **_soma(
                faturas.filter(
                    situacao__in=Fatura.EM_ABERTO, vencimento__gte=inicio_mes, vencimento__lt=proximo_mes
                )
            ),
            "filtro": f"vencimento__gte={inicio_mes:%Y-%m-%d}&vencimento__lt={proximo_mes:%Y-%m-%d}",
        },
        "recebido_mes": {
            **_soma(
                faturas.filter(
                    situacao=Fatura.Situacao.PAGA,
                    pago_em__date__gte=inicio_mes,
                    pago_em__date__lt=proximo_mes,
                )
            ),
            "filtro": "situacao__exact=paga",
        },
        "vencendo_7_dias": {
            **_soma(
                faturas.filter(
                    situacao=Fatura.Situacao.ABERTA,
                    vencimento__gte=hoje,
                    vencimento__lte=hoje + timedelta(days=7),
                )
            ),
            "filtro": f"situacao__exact=aberta&vencimento__gte={hoje:%Y-%m-%d}"
            f"&vencimento__lt={hoje + timedelta(days=8):%Y-%m-%d}",
        },
        "vencidas": {
            **_soma(faturas.filter(situacao=Fatura.Situacao.VENCIDA)),
            "filtro": "situacao__exact=vencida",
        },
        "aguardando": {
            **_soma(faturas.filter(situacao=Fatura.Situacao.AGUARDANDO)),
            "filtro": "situacao__exact=aguardando_confirmacao",
        },
    }


# --- Dados de demonstração ----------------------------------------------------------------------


def periodo_anterior(data: date, periodicidade: str) -> date:
    """Um mês (ou um ano) antes, com o mesmo ajuste de fim de mês do `proximo_vencimento`."""
    import calendar

    if periodicidade == Periodicidade.ANUAL:
        ano, mes = data.year - 1, data.month
    else:
        ano, mes = (data.year - 1, 12) if data.month == 1 else (data.year, data.month - 1)
    return date(ano, mes, min(data.day, calendar.monthrange(ano, mes)[1]))


def _comprovante_demo(fatura: Fatura) -> ContentFile:
    """Imagem fictícia de comprovante (Pillow), com o aviso de demonstração."""
    imagem = Image.new("RGB", (600, 400), (245, 247, 248))
    desenho = ImageDraw.Draw(imagem)
    linhas = [
        "COMPROVANTE DE DEMONSTRACAO",
        "Pix enviado",
        f"Valor: {moeda(fatura.valor)}",
        f"Identificador: {fatura.identificador_pix}",
        "Dados ficticios: nao e um pagamento real.",
    ]
    for indice, linha in enumerate(linhas):
        desenho.text((40, 60 + indice * 50), linha, fill=(14, 74, 87))
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return ContentFile(saida.getvalue(), name="comprovante.png")


def criar_faturas_demo(slugs_em_atraso: list[str] | tuple[str, ...] = ()) -> int:
    """Faturas das lojas demo: histórico pago em todas; uma aberta, uma aguardando confirmação (com
    comprovante fictício) e as lojas em atraso com a fatura vencida. Recria do zero (idempotente)."""
    apagar_faturas_demo()
    hoje = timezone.localdate()
    assinaturas = list(
        Assinatura.objects.filter(demo=True).select_related("plano", "anunciante").order_by("pk")
    )
    atrasadas = set(slugs_em_atraso)
    em_dia = [a for a in assinaturas if a.anunciante.slug not in atrasadas]
    especiais = {}
    if em_dia:
        especiais[em_dia[0].pk] = ("aberta", 5)
    if len(em_dia) > 1:
        especiais[em_dia[1].pk] = ("aguardando", 2)
    total = 0
    for assinatura in assinaturas:
        tipo, dias = especiais.get(assinatura.pk, ("", 0))
        if tipo:  # o vencimento fica dentro da antecedência: a fatura do ciclo já existe
            assinatura.vencimento = hoje + timedelta(days=dias)
            assinatura.save(update_fields=["vencimento", "atualizado_em"])
        competencia = assinatura.vencimento
        quantas = 1 if assinatura.periodicidade == Periodicidade.ANUAL else 3
        for _ in range(quantas):  # ciclos já pagos, do mais recente para o mais antigo
            competencia = periodo_anterior(competencia, assinatura.periodicidade)
            fatura = Fatura.objects.create(
                assinatura=assinatura,
                competencia=competencia,
                periodo_fim=proximo_vencimento(competencia, assinatura.periodicidade) - timedelta(days=1),
                descricao=descricao_da_assinatura(assinatura),
                valor=assinatura.valor,
                vencimento=competencia,
                situacao=Fatura.Situacao.PAGA,
                pago_em=timezone.make_aware(
                    datetime.combine(competencia - timedelta(days=1), datetime.min.time())
                )
                + timedelta(hours=10),
                forma=Fatura.Forma.PIX,
                demo=True,
            )
            total += 1
        if tipo or assinatura.anunciante.slug in atrasadas:
            fatura = gerar_fatura(assinatura, hoje, avisar=False)
            total += 1
            if tipo == "aguardando":
                fatura.comprovante.save("comprovante.png", _comprovante_demo(fatura), save=False)
                fatura.comprovante_enviado_em = timezone.now()
                fatura.situacao = Fatura.Situacao.AGUARDANDO
                fatura.observacao = "Anunciante: paguei pelo Pix hoje de manhã (demonstração)."
                fatura.save()
    return total


# Lote 3B: as lojas pendentes do demo.json com um pedido de plano pelo site ("Cadastros aguardando").
PEDIDOS_DEMO = (
    ("cerrado-novo-imoveis", True),
    ("sinop-auto-prime", False),
)  # (loja, já tocou em "Já paguei")


def criar_pedidos_demo() -> int:
    """Pedidos de plano das lojas demo pendentes: um aguardando conferência (sem comprovante) e um aguardando
    pagamento. Sem e-mails. Roda depois de `criar_faturas_demo` (que apaga as faturas demo). Devolve
    quantos."""
    from planos.services import planos_a_venda

    plano = planos_a_venda().first()
    total = 0
    for slug, informou in PEDIDOS_DEMO:
        loja = Anunciante.objects.filter(slug=slug, demo=True, status=Anunciante.Status.PENDENTE).first()
        if loja is None or plano is None or motivo_sem_pedido(loja):
            continue
        fatura = fazer_pedido(loja, plano, Periodicidade.MENSAL, checar_limite=False)
        if informou:
            fatura.situacao = Fatura.Situacao.AGUARDANDO
            fatura.comprovante_enviado_em = timezone.now()
            fatura.observacao = "Anunciante: paguei pelo Pix agora há pouco (demonstração)."
            fatura._change_reason = 'Cliente informou o pagamento ("Já paguei").'
            fatura.save()
        total += 1
    return total


def apagar_faturas_demo() -> int:
    """Apaga as faturas de demonstração (com os comprovantes e o histórico). Devolve quantas eram."""
    faturas = (
        Fatura.objects.filter(demo=True)
        | Fatura.objects.filter(assinatura__demo=True)
        | Fatura.objects.filter(campanha__demo=True)
    )
    quantas = 0
    for fatura in faturas.distinct():
        if fatura.comprovante:
            fatura.comprovante.delete(save=False)
        quantas += 1
    with transaction.atomic():
        Fatura.objects.filter(demo=True).delete()
        Fatura.objects.filter(assinatura__demo=True).delete()
        Fatura.objects.filter(campanha__demo=True).delete()
        Fatura.history.filter(demo=True).delete()
    return quantas
