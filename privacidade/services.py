"""Regras de LGPD (docs/LGPD.md, Sprint 7B): documentos legais com versão e aceite, cookies, "Meus dados"
(exportação e exclusão com anonimização), pedidos do titular e a limpeza pela guarda fiscal.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from contas.models import AceiteDocumento
from core.services import configuracao
from privacidade.models import DocumentoLegal, PedidoTitular

if TYPE_CHECKING:
    from contas.models import Usuario

logger = logging.getLogger(__name__)


# --- Documentos legais e aceite ------------------------------------------------------------------------


def documento_vigente(tipo: str, hoje: date | None = None) -> DocumentoLegal | None:
    """A versão em vigor: publicada, com a vigência mais recente que já começou."""
    hoje = hoje or timezone.localdate()
    return (
        DocumentoLegal.objects.filter(tipo=tipo, publicado=True, vigencia__lte=hoje)
        .order_by("-vigencia", "-pk")
        .first()
    )


def documentos_vigentes(hoje: date | None = None) -> list[DocumentoLegal]:
    """Termos e Privacidade em vigor (os que existirem)."""
    return [d for tipo in DocumentoLegal.Tipo.values if (d := documento_vigente(tipo, hoje))]


def pendencias_de_aceite(usuario) -> list[DocumentoLegal]:
    """Versões em vigor que a pessoa ainda não aceitou (equipe e anônimo: nada a aceitar aqui)."""
    if not usuario.is_authenticated or usuario.is_staff:
        return []
    aceitas = set(AceiteDocumento.objects.filter(usuario=usuario).values_list("documento", "versao"))
    return [d for d in documentos_vigentes() if (d.tipo, d.versao) not in aceitas]


def registrar_aceites(usuario: Usuario, documentos: list[DocumentoLegal]) -> int:
    """Grava o aceite (usuário, documento, versão, data e hora). Sem IP (só o necessário)."""
    AceiteDocumento.objects.bulk_create(
        AceiteDocumento(usuario=usuario, documento=d.tipo, versao=d.versao) for d in documentos
    )
    return len(documentos)


@dataclass(frozen=True)
class Bloco:
    """Pedaço do texto do documento para o template: título, parágrafo ou lista."""

    tipo: str  # "titulo" | "paragrafo" | "lista"
    conteudo: str | list[str]
    ancora: str = ""


def _valores_do_texto() -> dict[str, str]:
    """Variáveis que o texto do documento pode usar."""
    config = configuracao()
    return {
        "site": config.nome,
        "empresa": config.empresa,
        "cidade_sede": config.cidade_sede,
        "email_contato": config.email_contato,
        "email_privacidade": config.email_privacidade,
    }


def _fechar(blocos: list[Bloco], paragrafo: list[str], itens: list[str]) -> None:
    """Fecha o parágrafo e a lista em andamento (se houver) e limpa os acumuladores."""
    if paragrafo:
        blocos.append(Bloco("paragrafo", " ".join(paragrafo)))
        paragrafo.clear()
    if itens:
        blocos.append(Bloco("lista", list(itens)))
        itens.clear()


def blocos_do_texto(texto: str) -> list[Bloco]:
    """Texto puro do admin → blocos (o template escapa tudo: nada de HTML vindo do banco).

    "## " começa um título (com âncora), "- " um item de lista, linha em branco separa parágrafos.
    """
    valores = _valores_do_texto()
    texto = re.sub(r"\{(\w+)\}", lambda m: valores.get(m[1], m[0]), texto.replace("\r\n", "\n"))
    blocos: list[Bloco] = []
    for trecho in re.split(r"\n\s*\n", texto.strip()):
        itens: list[str] = []
        paragrafo: list[str] = []
        for linha in (linha.strip() for linha in trecho.split("\n")):
            if not linha:
                continue
            if linha.startswith("## "):
                _fechar(blocos, paragrafo, itens)
                titulo = linha[3:].strip()
                ancora = re.sub(r"[^a-z0-9]+", "-", _sem_acento(titulo).lower()).strip("-")
                blocos.append(Bloco("titulo", titulo, ancora))
            elif linha.startswith("- "):
                if paragrafo:
                    _fechar(blocos, paragrafo, itens)
                itens.append(linha[2:].strip())
            else:
                if itens:
                    _fechar(blocos, paragrafo, itens)
                paragrafo.append(linha)
        _fechar(blocos, paragrafo, itens)
    return blocos


def _sem_acento(texto: str) -> str:
    """Para âncoras: "Seções" → "Secoes"."""
    import unicodedata

    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


# --- Cookies (docs/LGPD.md) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cookie:
    """Um cookie que o site grava, para a seção "Cookies" da Política."""

    nome: str
    finalidade: str
    quem: str
    duracao: str
    essencial: bool = True


# Todos os cookies do site. Cookie novo = linha nova aqui e no docs/LGPD.md (um teste confere). Se um dia
# entrar um não essencial (essencial=False), o site precisa do aviso com "Aceitar" e "Recusar" iguais.
COOKIES = (
    Cookie(
        "csrftoken",
        "Protege formulários contra envio forjado por outros sites",
        "Quem usa um formulário",
        "1 ano",
    ),
    Cookie(
        "sessionid",
        "Mantém você conectado depois do login",
        "Só quem faz login (anunciantes e equipe)",
        "2 semanas",
    ),
    Cookie(
        "messages",
        'Mostra um aviso de uma página para a seguinte (ex.: "comprovante enviado")',
        "Quem envia um formulário",
        "Até o aviso aparecer",
    ),
    Cookie(
        "nd_admin_navegador",
        "Lembra que este navegador já foi confirmado com código, para não pedir de novo",
        "Só a equipe, na área administrativa",
        "30 dias",
    ),
)


def precisa_aviso_de_cookies() -> bool:
    """Só há aviso (banner) se existir cookie não essencial. Hoje: não."""
    return any(not c.essencial for c in COOKIES)


# --- Pedidos do titular --------------------------------------------------------------------------------


def registrar_pedido(
    usuario: Usuario | None, tipo: str, resposta: str, origem: str = PedidoTitular.Origem.PAINEL
) -> PedidoTitular:
    """Pedido feito e atendido na hora pelo painel (exportação, exclusão), para o registro da equipe."""
    agora = timezone.now()
    return PedidoTitular.objects.create(
        usuario=usuario,
        tipo=tipo,
        origem=origem,
        situacao=PedidoTitular.Situacao.ATENDIDO,
        recebido_em=agora,
        atendido_em=agora,
        resposta=resposta,
        demo=bool(usuario and usuario.demo),
    )


def responder_pedido(pedido: PedidoTitular, por, resposta: str) -> PedidoTitular:
    """A equipe marca como atendido, com o que foi feito (ação do admin)."""
    if not resposta.strip():
        raise ValueError("Escreva o que foi feito (fica no registro do pedido).")
    pedido.situacao = PedidoTitular.Situacao.ATENDIDO
    pedido.atendido_em = timezone.now()
    pedido.resposta = resposta.strip()
    pedido._history_user = por
    pedido._change_reason = "Pedido atendido."
    pedido.save()
    return pedido


# --- "Baixar meus dados" ------------------------------------------------------------------------------


def _ponto(ponto) -> dict | None:
    """Ponto do mapa como latitude/longitude."""
    return {"latitude": ponto.y, "longitude": ponto.x} if ponto else None


def exportar_dados(usuario: Usuario) -> dict:
    """Tudo o que o site guarda sobre a pessoa e a loja dela (LGPD, art. 18, II e V), em dicionário.

    Conta, loja, assinatura, pedidos de plano, anúncios (com ficha, endereço e ponto privados e as fotos),
    faturas (sem o arquivo do comprovante, que fica no armazenamento privado), aceites e pedidos de titular.
    """
    from anunciantes.models import Anunciante

    dados: dict = {
        "gerado_em": timezone.now(),
        "site": configuracao().nome,
        "conta": {
            "email": usuario.email,
            "nome": usuario.nome,
            "criada_em": usuario.criado_em,
            "email_confirmado_em": usuario.email_confirmado_em,
            "ultimo_acesso": usuario.last_login,
        },
        "aceites": [
            {"documento": a.get_documento_display(), "versao": a.versao, "aceito_em": a.aceito_em}
            for a in usuario.aceites.order_by("aceito_em")
        ],
        "pedidos_titular": [
            {"tipo": p.get_tipo_display(), "recebido_em": p.recebido_em, "situacao": p.get_situacao_display()}
            for p in usuario.pedidos_titular.order_by("recebido_em")
        ],
    }
    anunciante = Anunciante.objects.filter(usuario=usuario).select_related("cidade").first()
    if anunciante is None:
        return dados
    dados["loja"] = {
        "tipo": anunciante.get_tipo_display(),
        "nome_publico": anunciante.nome_publico,
        "endereco_da_pagina": anunciante.slug,
        "documento": f"{anunciante.get_documento_tipo_display()} {anunciante.documento_numero}",
        "whatsapp": anunciante.whatsapp,
        "email_publico": anunciante.email_publico,
        "cidade": str(anunciante.cidade),
        "situacao": anunciante.get_status_display(),
        "sobre": anunciante.sobre,
        "endereco_publico": anunciante.endereco_publico,
        "mostrar_no_mapa": anunciante.mostrar_no_mapa,
        "ponto_no_mapa": _ponto(anunciante.ponto),
        "horario": anunciante.horario,
        "instagram": anunciante.instagram,
        "site": anunciante.site,
        "cadastrada_em": anunciante.criado_em,
    }
    assinatura = getattr(anunciante, "assinatura", None)
    if assinatura:
        dados["assinatura"] = {
            "plano": assinatura.plano.nome,
            "periodicidade": assinatura.get_periodicidade_display(),
            "inicio": assinatura.inicio,
            "vencimento": assinatura.vencimento,
            "situacao": assinatura.get_situacao_display(),
        }
        dados["faturas"] = [
            {
                "codigo": f.codigo,
                "descricao": f.descricao,
                "periodo": f"{f.competencia} a {f.periodo_fim}",
                "valor": f.valor,
                "vencimento": f.vencimento,
                "situacao": f.get_situacao_display(),
                "pago_em": f.pago_em,
                "forma": f.get_forma_display() if f.forma else "",
                "observacao": f.observacao,
                "comprovante_enviado": bool(f.comprovante),
            }
            for f in assinatura.faturas.order_by("vencimento")
        ]
    dados["pedidos_de_plano"] = [
        {
            "plano_pedido": p.plano_novo.nome,
            "periodicidade": p.get_periodicidade_display(),
            "situacao": p.get_status_display(),
            "pedido_em": p.criado_em,
        }
        for p in anunciante.pedidos_plano.select_related("plano_novo").order_by("criado_em")
    ]
    dados["anuncios"] = [
        _anuncio(a) for a in anunciante.anuncios.select_related("cidade", "bairro").order_by("pk")
    ]
    return dados


def _anuncio(anuncio) -> dict:
    """Um anúncio com a ficha e os endereços das fotos."""
    item = {
        "codigo": anuncio.codigo,
        "titulo": anuncio.titulo,
        "descricao": anuncio.descricao,
        "preco": anuncio.preco,
        "situacao": anuncio.get_situacao_display(),
        "cidade": str(anuncio.cidade),
        "bairro": str(anuncio.bairro) if anuncio.bairro_id else "",
        "criado_em": anuncio.criado_em,
        "publicado_em": anuncio.publicado_em,
        "expira_em": anuncio.expira_em,
        "fotos": [settings.SITE_URL + f.imagem.url for f in anuncio.fotos.all() if f.imagem],
    }
    imovel = getattr(anuncio, "imovel", None)
    if anuncio.categoria == "imovel" and imovel:
        item["imovel"] = {
            "tipo": imovel.get_tipo_display(),
            "negocio": imovel.get_modalidade_display(),
            "quartos": imovel.quartos,
            "area_total": imovel.area_total,
            "endereco_privado": imovel.endereco,
            "ponto_privado": _ponto(imovel.ponto),
            "localizacao_no_site": imovel.get_exibir_localizacao_display(),
        }
    veiculo = getattr(anuncio, "veiculo", None)
    if anuncio.categoria == "veiculo" and veiculo:
        item["veiculo"] = {
            "versao": str(veiculo.versao),
            "ano": f"{veiculo.ano_fabricacao}/{veiculo.ano_modelo}",
            "quilometragem": veiculo.quilometragem,
            "final_da_placa": veiculo.final_placa,
        }
    return item


def exportar_json(usuario: Usuario) -> str:
    """Os dados em JSON legível (datas ISO, valores com ponto decimal) e registra o pedido atendido."""
    texto = json.dumps(exportar_dados(usuario), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
    registrar_pedido(usuario, PedidoTitular.Tipo.EXPORTACAO, "Cópia dos dados baixada pelo painel (JSON).")
    return texto


# --- "Excluir minha conta" ----------------------------------------------------------------------------


def faturas_em_aberto(usuario: Usuario) -> list:
    """Faturas ainda não pagas da loja (avisadas antes da exclusão; não impedem)."""
    from pagamentos.models import Fatura

    return list(
        Fatura.objects.filter(
            assinatura__anunciante__usuario=usuario, situacao__in=Fatura.EM_ABERTO
        ).order_by("vencimento")
    )


def _apagar_arquivos(objeto, campos: tuple[str, ...]) -> None:
    """Apaga do storage os arquivos dos campos (sem salvar o objeto)."""
    for campo in campos:
        arquivo = getattr(objeto, campo)
        if arquivo:
            arquivo.delete(save=False)


def anonimizar_conta(usuario: Usuario) -> PedidoTitular:
    """Exclusão pedida pelo titular (LGPD, art. 18, VI): anonimiza a conta e a loja, tira os anúncios do ar
    e apaga as fotos; guarda só o exigido por lei.

    - Conta: e-mail removido-<id>@anonimo.invalid, nome "Conta removida", senha inutilizável, inativa
      (as sessões abertas deixam de valer), códigos de acesso e tentativas de login com o e-mail apagados.
    - Loja: encerrada, nome/endereço da página trocados, WhatsApp, e-mail, textos, ponto, logo e capa
      apagados; o mesmo no histórico. CRECI/CNPJ ficam (obrigação fiscal das faturas).
    - Anúncios: removidos (exclusão lógica), fotos apagadas do storage, endereço e ponto privados
      apagados (também no histórico). Assinatura cancelada.
    - Faturas e comprovantes: ficam pela guarda fiscal (`Configuracao.retencao_fiscal_anos`), ligadas à loja
      já anonimizada; a rotina diária apaga o comprovante e as anotações depois do prazo.
    Manda a confirmação ao e-mail antigo (antes de apagá-lo) e registra o pedido atendido.
    """
    from anunciantes.models import Anunciante
    from anuncios.models import Anuncio, DetalheImovel, Foto
    from planos.models import Assinatura

    if usuario.is_staff:
        raise ValueError("Conta da equipe não é excluída por aqui.")
    email_antigo, primeiro_nome = usuario.email, usuario.get_short_name()
    with transaction.atomic():
        anunciante = Anunciante.objects.filter(usuario=usuario).first()
        if anunciante:
            anuncios = Anuncio.objects.filter(anunciante=anunciante)
            for foto in Foto.objects.filter(anuncio__in=anuncios):
                _apagar_arquivos(foto, ("original", "imagem", "miniatura", "compartilhamento"))
            Foto.objects.filter(anuncio__in=anuncios).delete()
            for anuncio in anuncios.exclude(situacao=Anuncio.Situacao.REMOVIDO):
                anuncio.situacao, anuncio.removido_em = Anuncio.Situacao.REMOVIDO, timezone.now()
                anuncio._change_reason = "Conta excluída pelo titular (LGPD)."
                anuncio.save()
            for imovel in DetalheImovel.objects.filter(anuncio__in=anuncios):
                imovel.endereco, imovel.ponto = "", None
                imovel._change_reason = "Conta excluída pelo titular (LGPD)."
                imovel.save()
            DetalheImovel.history.filter(anuncio_id__in=anuncios.values("pk")).update(endereco="", ponto=None)

            Assinatura.objects.filter(anunciante=anunciante).exclude(
                situacao=Assinatura.Situacao.CANCELADA
            ).update(situacao=Assinatura.Situacao.CANCELADA)
            _apagar_arquivos(
                anunciante, ("logo_original", "capa_original", "logo", "logo_mini", "capa", "capa_media")
            )
            anonimos = {
                "nome_publico": f"Loja removida {anunciante.pk}",
                "slug": f"loja-removida-{anunciante.pk}",
                "sigla": "",
                "whatsapp": "",
                "email_publico": "",
                "sobre": "",
                "endereco_publico": "",
                "mostrar_no_mapa": False,
                "ponto": None,
                "horario": "",
                "instagram": "",
                "site": "",
            }
            Anunciante.objects.filter(pk=anunciante.pk).update(
                **anonimos,
                logo_original="",
                capa_original="",
                logo="",
                logo_mini="",
                capa="",
                capa_media="",
                status=Anunciante.Status.ENCERRADO,
                motivo_status="Conta excluída pelo titular (LGPD).",
            )
            Anunciante.history.filter(id=anunciante.pk).update(
                **anonimos, logo="", logo_mini="", capa="", capa_media=""
            )

        _apagar_rastros_de_acesso(usuario, email_antigo)
        Usuario = get_user_model()
        Usuario.objects.filter(pk=usuario.pk).update(
            email=f"removido-{usuario.pk}@anonimo.invalid", nome="Conta removida", is_active=False
        )
        usuario.refresh_from_db()
        usuario.set_unusable_password()
        usuario.save(update_fields=["password"])
        pedido = registrar_pedido(
            usuario,
            PedidoTitular.Tipo.EXCLUSAO,
            "Conta anonimizada pelo próprio titular no painel; anúncios removidos e fotos apagadas; "
            "faturas guardadas "
            "pela obrigação fiscal.",
        )
    transaction.on_commit(lambda: _confirmar_exclusao(email_antigo, primeiro_nome))
    logger.info("Conta anonimizada a pedido do titular (usuário id=%s).", usuario.pk)  # sem e-mail no log
    return pedido


def _apagar_rastros_de_acesso(usuario: Usuario, email: str) -> None:
    """Tentativas de login (axes) com o e-mail e os códigos de acesso por e-mail (django-otp)."""
    from axes.models import AccessAttempt
    from django_otp.plugins.otp_email.models import EmailDevice
    from django_otp.plugins.otp_static.models import StaticDevice

    AccessAttempt.objects.filter(username=email).delete()
    EmailDevice.objects.filter(user=usuario).delete()
    StaticDevice.objects.filter(user=usuario).delete()


def _confirmar_exclusao(email: str, primeiro_nome: str) -> None:
    """E-mail ao endereço antigo dizendo o que foi feito e o que fica guardado."""
    config = configuracao()
    send_mail(
        f"Sua conta foi excluída · {config.nome}",
        f"Olá{', ' + primeiro_nome if primeiro_nome else ''}.\n\n"
        f"Como você pediu, excluímos sua conta no {config.nome}: seus dados de contato foram apagados, "
        "a loja saiu do ar e os anúncios e as fotos foram removidos.\n\n"
        f"Guardamos só o que a lei exige: as faturas e os comprovantes de pagamento, por "
        f"{config.retencao_fiscal_anos} anos (obrigação fiscal), sem seus dados de contato.\n\n"
        f"Dúvidas: {config.email_privacidade}\n",
        None,
        [email],
    )


# --- Guarda fiscal (rotina diária) --------------------------------------------------------------------


def limpar_dados_vencidos(hoje: date | None = None) -> int:
    """Faturas pagas ou canceladas há mais que a guarda fiscal: apaga o comprovante e limpa as anotações
    (também no histórico). A fatura (valores e datas) continua para o histórico financeiro."""
    from pagamentos.models import Fatura

    hoje = hoje or timezone.localdate()
    anos = configuracao().retencao_fiscal_anos
    try:
        limite = hoje.replace(year=hoje.year - anos)
    except ValueError:  # 29/02 num ano que não é bissexto
        limite = hoje.replace(year=hoje.year - anos, day=28)
    antigas = Fatura.objects.filter(
        situacao__in=[Fatura.Situacao.PAGA, Fatura.Situacao.CANCELADA], vencimento__lt=limite
    ).exclude(comprovante="", observacao="", motivo_recusa="")
    total = 0
    for fatura in antigas:
        if fatura.comprovante:
            fatura.comprovante.delete(save=False)
        Fatura.objects.filter(pk=fatura.pk).update(comprovante="", observacao="", motivo_recusa="")
        Fatura.history.filter(id=fatura.pk).update(comprovante="", observacao="", motivo_recusa="")
        total += 1
    logger.info("Guarda fiscal: %s fatura(s) limpas.", total)
    return total


# --- Dados de demonstração ----------------------------------------------------------------------------


def criar_pedido_demo() -> PedidoTitular:
    """Um pedido fictício chegado por e-mail, em aberto (para ver a lista do admin com o prazo)."""
    apagar_pedidos_demo()
    return PedidoTitular.objects.create(
        contato="titular@demo.invalid",
        tipo=PedidoTitular.Tipo.ACESSO,
        origem=PedidoTitular.Origem.EMAIL,
        descricao="Pedido fictício: quero saber quais dados o site guarda sobre mim (demonstração).",
        recebido_em=timezone.now() - timedelta(days=3),
        demo=True,
    )


def apagar_pedidos_demo() -> int:
    """Apaga os pedidos de demonstração (e de contas demo), com o histórico."""
    quantos, _ = PedidoTitular.objects.filter(demo=True).delete()
    PedidoTitular.history.filter(demo=True).delete()
    return quantos
