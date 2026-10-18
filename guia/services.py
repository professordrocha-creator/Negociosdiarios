"""Regras do app guia (Guia de Negócios; docs/GUIA.md §5, §8 e §10; docs/GUIA_LGPD_E_TERMO.md).

Publicação: só com aceite válido da versão vigente do termo, ao menos 1 categoria, cidade liberada, WhatsApp
ou telefone em E.164 e local (endereço + ponto) OU área de atendimento. Só o aceite leva a "publicado": o
admin não pula essa etapa. Convite: link de uso único com token de 32 bytes e validade. CPF: só o HMAC
(chave GUIA_CPF_CHAVE do .env) e os 2 últimos dígitos. Duplicidade (CNPJ, CPF, WhatsApp) alerta, não bloqueia.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import ipaddress
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.text import slugify

from core import imagens
from core.models import Cidade
from guia.models import (
    CHAVE_CACHE_CONFIGURACAO_GUIA,
    AceitePublicacao,
    CategoriaServico,
    ConfiguracaoGuia,
    ConviteAceite,
    GrupoCategoria,
    PedidoDoPerfil,
    PerfilGuia,
    TermoGuia,
)

ARQUIVO_CATEGORIAS = Path(settings.BASE_DIR) / "docs" / "guia" / "categorias_iniciais.csv"
COLUNAS_CATEGORIAS = {"grupo", "nome", "slug", "ordem", "regulamentada", "rotulo_registro", "sinonimos"}
# Regulamentadas que são estabelecimentos (mostram horário; docs/GUIA.md §5, item 4).
ESTABELECIMENTOS_REGULADOS = {
    "farmacia",
    "clinica-e-laboratorio",
    "hospital-e-pronto-atendimento",
    "veterinario",
}
TELEFONE_E164 = re.compile(r"^\+55\d{10,11}$")
# Frase é texto puro: nada de link (http, www, domínio) nem marcação HTML.
LINK_OU_HTML = re.compile(
    r"https?://|www\.|<|>|\b[\w-]+\.(?:com|net|org|br|me|ly|io|app|site)\b", re.IGNORECASE
)
DIAS_DA_SEMANA = [
    ("seg", "Segunda"),
    ("ter", "Terça"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sábado"),
    ("dom", "Domingo"),
]
INTERVALO = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(?:-|–|a|às)\s*(\d{1,2})(?::(\d{2}))?$")


class PublicacaoRecusada(ValueError):
    """Faltam requisitos para publicar; `pendencias` diz quais (mostradas no admin)."""

    def __init__(self, pendencias: list[str]):
        self.pendencias = pendencias
        super().__init__(" ".join(pendencias))


# --- Configuração ---------------------------------------------------------------------------------------


def configuracao_guia() -> ConfiguracaoGuia:
    """O registro único da configuração do guia (criado com os padrões na primeira leitura), com cache."""
    config = cache.get(CHAVE_CACHE_CONFIGURACAO_GUIA)
    if config is None:
        config, _ = ConfiguracaoGuia.objects.get_or_create(pk=ConfiguracaoGuia.ID_UNICO)
        cache.set(CHAVE_CACHE_CONFIGURACAO_GUIA, config, timeout=3600)
    return config


# --- Campos do perfil -----------------------------------------------------------------------------------


def erro_da_frase(frase: str) -> str:
    """Mensagem de erro da frase (vazia = ok): sem links nem HTML e até `limite_frase` caracteres."""
    if not frase:
        return ""
    limite = configuracao_guia().limite_frase
    if len(frase) > limite:
        return f"A frase pode ter até {limite} caracteres (tem {len(frase)})."
    if LINK_OU_HTML.search(frase):
        return "A frase é texto puro: sem links, endereços de site nem marcação (< >)."
    return ""


def slug_do_perfil(perfil: PerfilGuia) -> str:
    """Endereço da ficha: nome + cidade, sem acentos e único (acrescenta -2, -3... se já existir)."""
    base = slugify(f"{perfil.nome_publico} {perfil.cidade.slug}")[:130].strip("-") or "perfil"
    slug, n = base, 2
    while PerfilGuia.objects.filter(slug=slug).exclude(pk=perfil.pk).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def ponto_publico_de(perfil: PerfilGuia):
    """O único ponto que sai do servidor: o do endereço comercial, ou o centro da cidade (a domicílio).

    Quem atende a domicílio nunca tem o ponto marcado exposto (pode ser a casa da pessoa).
    """
    if perfil.atendimento == PerfilGuia.Atendimento.ENDERECO and perfil.ponto is not None:
        return perfil.ponto
    return perfil.cidade.ponto if perfil.cidade_id else None


def cpf_valido(digitos: str) -> bool:
    """CPF (só dígitos) com 11 dígitos, não repetidos e com os dois verificadores certos."""
    if not re.fullmatch(r"\d{11}", digitos) or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * p for d, p in zip(digitos[:tamanho], range(tamanho + 1, 1, -1), strict=True))
        if int(digitos[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def normalizar_cpf(texto: str) -> str:
    """Tira pontos e traço e valida. Levanta ValidationError com o que fazer."""
    digitos = re.sub(r"\D", "", texto or "")
    if not cpf_valido(digitos):
        raise ValidationError("CPF inválido. Confira os 11 números (pontos e traço são opcionais).")
    return digitos


def _chave_cpf() -> bytes:
    """Chave do HMAC do CPF (GUIA_CPF_CHAVE do .env). Em dev, sem a chave, deriva da SECRET_KEY."""
    chave = getattr(settings, "GUIA_CPF_CHAVE", "")
    if chave:
        return chave.encode()
    if settings.DEBUG:
        return salted_hmac("guia.cpf", "chave-dev").hexdigest().encode()
    raise ImproperlyConfigured("Defina GUIA_CPF_CHAVE no .env (resumo do CPF do Guia de Negócios).")


def resumo_cpf(cpf: str) -> tuple[str, str]:
    """(HMAC-SHA256 do CPF, 2 últimos dígitos). O CPF em claro nunca é gravado (docs/GUIA.md §4)."""
    digitos = normalizar_cpf(cpf)
    return hmac.new(_chave_cpf(), digitos.encode(), hashlib.sha256).hexdigest(), digitos[-2:]


def definir_cpf(perfil: PerfilGuia, cpf: str) -> None:
    """Guarda só o resumo e o final do CPF no perfil (sem salvar; o chamador salva)."""
    perfil.cpf_hash, perfil.cpf_final = resumo_cpf(cpf)


def interpretar_horario(texto: str) -> list[list[str]]:
    """ "8-12, 14:00-18:00" → [["08:00", "12:00"], ["14:00", "18:00"]]. Vazio = fechado/sem horário.

    Levanta ValidationError explicando o formato. Aceita "-", "a" ou "às" entre as horas.
    """
    intervalos = []
    for trecho in filter(None, (t.strip() for t in re.split(r"[,;/]| e ", texto or ""))):
        achado = INTERVALO.match(trecho.lower().replace("h", ":").replace("::", ":").rstrip(":"))
        if not achado:
            raise ValidationError(
                f'Horário "{trecho}" não entendido. Use, por exemplo: 8:00-12:00, 14:00-18:00.'
            )
        h1, m1, h2, m2 = achado.groups()
        inicio, fim = f"{int(h1):02d}:{int(m1 or 0):02d}", f"{int(h2):02d}:{int(m2 or 0):02d}"
        if not ("00:00" <= inicio < fim <= "24:00") or int(m1 or 0) > 59 or int(m2 or 0) > 59:
            raise ValidationError(
                f'Horário "{trecho}": o início precisa ser antes do fim, entre 00:00 e 24:00.'
            )
        intervalos.append([inicio, fim])
    return intervalos


def formatar_horario(intervalos: list[list[str]]) -> str:
    """[["08:00", "12:00"]] → "08:00-12:00" (para o formulário)."""
    return ", ".join(f"{inicio}-{fim}" for inicio, fim in intervalos or [])


def horarios_legiveis(horarios: dict) -> list[tuple[str, str]]:
    """[("Segunda", "08:00 às 12:00 e 14:00 às 18:00"), ...] só dos dias com horário (para a ficha)."""
    linhas = []
    for chave, dia in DIAS_DA_SEMANA:
        intervalos = (horarios or {}).get(chave) or []
        if intervalos:
            linhas.append((dia, " e ".join(f"{inicio} às {fim}" for inicio, fim in intervalos)))
    return linhas


def validar_categorias(categorias: list[CategoriaServico], frase: str, tipo: str) -> dict[str, str]:
    """Erros da escolha de categorias para o formulário: máximo da configuração e regulamentada sem frase."""
    erros: dict[str, str] = {}
    maximo = configuracao_guia().max_categorias
    if len(categorias) > maximo:
        erros["categorias"] = f"Escolha no máximo {maximo} categorias."
    regulada = tipo == PerfilGuia.Tipo.REGULAMENTADO or any(c.regulamentada for c in categorias)
    if regulada and frase:
        erros["frase"] = (
            "Profissão regulamentada não tem frase promocional (regra dos conselhos). "
            "Deixe a frase em branco."
        )
    return erros


# --- Logo e foto do termo (mesmo tratamento das fotos: tipo real, sem EXIF) ------------------------------


def logo_processada(arquivo: UploadedFile) -> ContentFile:
    """Confere o logo (JPG/PNG/WebP/HEIC de verdade, limites da `Configuracao`), recorta em quadrado e gera
    um WebP de 400 px sem metadados. Levanta ValidationError."""
    from core.services import configuracao

    config = configuracao()
    imagens.validar_foto(
        arquivo, config.limite_logo_kb, config.logo_min_px, config.logo_min_px, imagens.FORMATOS_FOTO_ANUNCIO
    )
    quadrada = imagens.recortar_proporcao(imagens.abrir_limpa(arquivo), 1.0)
    return imagens.webp(quadrada, 400, "logo")


def definir_logo(perfil: PerfilGuia, arquivo: UploadedFile) -> None:
    """Troca o logo do perfil (apaga o antigo do storage). Salva só o campo do logo."""
    limpo = logo_processada(arquivo)
    if perfil.logo:
        perfil.logo.delete(save=False)
    perfil.logo.save("logo.webp", limpo, save=False)
    perfil.save(update_fields=["logo", "atualizado_em"])


def foto_termo_limpa(arquivo: UploadedFile) -> ContentFile:
    """Foto do termo em papel: imagem de verdade até `limite_foto_termo_kb`, regravada em JPEG sem EXIF."""
    imagens.validar_foto(
        arquivo, configuracao_guia().limite_foto_termo_kb, 300, 300, imagens.FORMATOS_FOTO_ANUNCIO
    )
    imagem = imagens.abrir_limpa(arquivo).convert("RGB")
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=88)
    return ContentFile(saida.getvalue(), name="termo.jpg")


# --- Termo, duplicidade e requisitos de publicação ----------------------------------------------------


def termo_vigente(hoje=None) -> TermoGuia | None:
    """A versão do termo em vigor hoje (a de vigência mais recente que já começou)."""
    hoje = hoje or timezone.localdate()
    return TermoGuia.objects.filter(vigente_desde__lte=hoje).order_by("-vigente_desde", "-pk").first()


def valores_do_termo(termo: TermoGuia) -> dict[str, str]:
    """Variáveis do texto do termo (docs/GUIA_LGPD_E_TERMO.md §3)."""
    from anunciantes.validators import cnpj_valido
    from core.services import configuracao

    config = configuracao()
    cnpj = re.sub(r"\D", "", config.cnpj or "")
    return {
        "nome_guia": configuracao_guia().nome_guia,
        "versao": termo.versao,
        "vigente_desde": f"{termo.vigente_desde:%d/%m/%Y}",
        "empresa": config.empresa,
        "documento": f"CNPJ {cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        if cnpj_valido(cnpj)
        else "CNPJ a informar",
        "cidade_sede": config.cidade_sede,
        "email_encarregado": config.email_privacidade,
    }


def blocos_do_termo(termo: TermoGuia) -> list:
    """Texto do termo em blocos escapáveis (formato dos documentos legais), com as variáveis trocadas."""
    from privacidade.services import blocos_do_texto

    valores = valores_do_termo(termo)
    texto = re.sub(r"\{(\w+)\}", lambda m: valores.get(m[1], m[0]), termo.texto)
    return blocos_do_texto(texto)


def aceite_vigente(perfil: PerfilGuia) -> AceitePublicacao | None:
    """Aceite não revogado da versão do termo em vigor (o único que autoriza publicar)."""
    termo = termo_vigente()
    if termo is None or perfil.pk is None:
        return None
    return perfil.aceites.filter(termo=termo, revogado_em__isnull=True).order_by("-aceito_em").first()


def duplicidades(perfil: PerfilGuia) -> list[str]:
    """Outros perfis com o mesmo CNPJ, CPF (resumo) ou WhatsApp. Só alerta: a equipe decide (§5, item 5)."""
    criterios = [
        ("CNPJ", "cnpj", perfil.cnpj),
        ("CPF", "cpf_hash", perfil.cpf_hash),
        ("WhatsApp", "whatsapp", perfil.whatsapp),
    ]
    avisos = []
    for rotulo, campo, valor in criterios:
        if not valor:
            continue
        outros = PerfilGuia.objects.filter(**{campo: valor}).exclude(pk=perfil.pk).select_related("cidade")
        for outro in outros[:5]:
            avisos.append(
                f"Mesmo {rotulo} de “{outro.nome_publico}” "
                f"({outro.cidade}, {outro.get_status_display().lower()})."
            )
    return avisos


def pendencias(perfil: PerfilGuia, exigir_aceite: bool = True) -> list[str]:
    """O que falta para publicar (vazio = pode). Usada pelo admin (botão desabilitado com explicação)."""
    faltas = []
    if perfil.status == PerfilGuia.Status.REMOVIDO:
        return ["Perfil removido: não volta a ser publicado."]
    if perfil.pk is None or not perfil.categorias.filter(ativa=True).exists():
        faltas.append("Escolha ao menos 1 categoria ativa.")
    cidade = perfil.cidade if perfil.cidade_id else None
    if cidade is None or not (cidade.liberada and cidade.uf.liberado):
        faltas.append("A cidade precisa estar liberada no site.")
    if not any(TELEFONE_E164.match(n or "") for n in (perfil.whatsapp, perfil.telefone)):
        faltas.append("Informe um WhatsApp ou telefone válido, com DDD.")
    if perfil.atendimento == PerfilGuia.Atendimento.ENDERECO:
        if not perfil.endereco.strip() or perfil.ponto is None:
            faltas.append("Tem endereço: preencha o endereço comercial e marque o ponto no mapa.")
    elif not perfil.area_atendimento.strip():
        faltas.append("Atende a domicílio: preencha a área de atendimento.")
    if perfil.pk is not None and perfil.regulamentado:
        if perfil.frase:
            faltas.append("Profissão regulamentada não tem frase promocional: apague a frase.")
        if not perfil.registro_profissional.strip():
            faltas.append("Profissão regulamentada: informe o registro no conselho (ex.: CRM-MT 1234).")
    if exigir_aceite:
        if termo_vigente() is None:
            faltas.append("Não há termo do guia em vigor (cadastre uma versão no admin).")
        elif aceite_vigente(perfil) is None:
            faltas.append(
                "Falta o aceite do responsável na versão vigente do termo "
                "(envie o link ou registre o aceite em papel)."
            )
    return faltas


def publicar(perfil: PerfilGuia, motivo: str = "Publicado.") -> PerfilGuia:
    """Põe o perfil no ar. Levanta PublicacaoRecusada se faltar algo (inclusive o aceite vigente)."""
    faltas = pendencias(perfil)
    if faltas:
        raise PublicacaoRecusada(faltas)
    perfil.status = PerfilGuia.Status.PUBLICADO
    perfil.publicado_em = perfil.publicado_em or timezone.now()
    perfil._change_reason = motivo
    perfil.save(update_fields=["status", "publicado_em", "atualizado_em"])
    return perfil


def pausar(perfil: PerfilGuia, motivo: str = "Pausado pela equipe.") -> PerfilGuia:
    """Tira do ar sem apagar nada (volta com `publicar`, se o aceite vigente continuar valendo)."""
    if perfil.status != PerfilGuia.Status.PUBLICADO:
        raise ValueError("Só um perfil publicado pode ser pausado.")
    perfil.status = PerfilGuia.Status.PAUSADO
    perfil._change_reason = motivo
    perfil.save(update_fields=["status", "atualizado_em"])
    return perfil


# --- Convite e aceite ------------------------------------------------------------------------------------


def gerar_convite(
    perfil: PerfilGuia, por=None, canal: str = ConviteAceite.Canal.WHATSAPP, expira_em=None
) -> tuple[ConviteAceite, str]:
    """Cria o link de aceite (uso único, validade da configuração ou `expira_em`) e vence os convites
    anteriores não usados.

    Só com tudo pronto, menos o aceite (o aceite publica na hora), e nunca para número da lista "não
    contatar". Rascunho passa a "aguardando aceite". Devolve (convite, token). Levanta PublicacaoRecusada.
    """
    faltas = pendencias(perfil, exigir_aceite=False)
    if numero_bloqueado(perfil.whatsapp):
        faltas.append("Este WhatsApp recusou ou pediu para não ser contatado (lista de convites).")
    if termo_vigente() is None:
        faltas.append("Não há termo do guia em vigor (cadastre uma versão no admin).")
    if faltas:
        raise PublicacaoRecusada(faltas)
    agora = timezone.now()
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        perfil.convites.filter(usado_em__isnull=True, expira_em__gt=agora).update(expira_em=agora)
        convite = ConviteAceite.objects.create(
            perfil=perfil,
            token=token,
            canal=canal,
            expira_em=expira_em or agora + timedelta(days=configuracao_guia().dias_validade_convite),
            criado_por=por,
        )
        if perfil.status == PerfilGuia.Status.RASCUNHO:
            perfil.status = PerfilGuia.Status.AGUARDANDO_ACEITE
            perfil._change_reason = f"Convite de aceite criado ({convite.get_canal_display()})."
            perfil.save(update_fields=["status", "atualizado_em"])
    return convite, token


def link_aceite(token: str) -> str:
    """Endereço completo da página de aceite."""
    return settings.SITE_URL + reverse("guia:aceite", args=[token])


def mensagem_convite(perfil: PerfilGuia, link: str, por=None) -> str:
    """Mensagem do WhatsApp (docs/GUIA_LGPD_E_TERMO.md §4), montada no servidor."""
    from core.services import configuracao

    config = configuracao()
    quem = (getattr(por, "nome", "") or "").split(" ")[0] or "a equipe"
    nome = perfil.responsavel_nome.split(" ")[0] if perfil.responsavel_nome else perfil.nome_publico
    cidade = config.cidade_sede.split(",")[0].strip()
    return (
        f"Olá, {nome}! Aqui é {quem}, do {config.nome}, de {cidade}. Estou montando um guia gratuito de "
        f"serviços e comércios da região e queria incluir {perfil.nome_publico}, sem custo. "
        "Antes de publicar, "
        f"você confere como vai aparecer e autoriza por este link: {link}\n"
        'Se preferir não participar, é só responder "não" e eu não entro em contato de novo.'
    )


def url_whatsapp(numero_e164: str, texto: str) -> str:
    """Link wa.me com a mensagem pronta (número só com dígitos)."""
    digitos = re.sub(r"\D", "", numero_e164)
    return f"https://wa.me/{digitos}?text={quote(texto)}"


def convite_valido(token: str) -> ConviteAceite | None:
    """Convite pelo token, só se ainda vale (não usado, não vencido, perfil não removido). Senão, None."""
    if not token or len(token) > 64:
        return None
    convite = ConviteAceite.objects.select_related("perfil", "perfil__cidade").filter(token=token).first()
    if convite is None or not convite.valido() or convite.perfil.status == PerfilGuia.Status.REMOVIDO:
        return None
    return convite


def truncar_ip(ip: str) -> str:
    """IP com o último bloco zerado (IPv4: /24; IPv6: /48). Inválido ou vazio: ""."""
    try:
        endereco = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return ""
    prefixo = 24 if endereco.version == 4 else 48
    return str(ipaddress.ip_network(f"{endereco}/{prefixo}", strict=False).network_address)


def resumir_agente(agente: str) -> str:
    """ "Chrome · Android" a partir do User-Agent (nunca o texto inteiro, que ajuda a identificar)."""
    agente = agente or ""
    navegadores = [
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("SamsungBrowser", "Samsung Internet"),
        ("Firefox/", "Firefox"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    ]
    sistemas = [
        ("Android", "Android"),
        ("iPhone", "iPhone"),
        ("iPad", "iPad"),
        ("Windows", "Windows"),
        ("Mac OS", "Mac"),
        ("Linux", "Linux"),
    ]
    navegador = next((nome for marca, nome in navegadores if marca in agente), "Outro navegador")
    sistema = next((nome for marca, nome in sistemas if marca in agente), "outro sistema")
    return f"{navegador} · {sistema}"[:80]


def _confirmar_por_email(perfil: PerfilGuia, aceite: AceitePublicacao) -> None:
    """Confirmação ao responsável, se o contato dele for um e-mail (com o caminho para alterar ou remover)."""
    from core.services import configuracao, enviar_email_modelo

    contato = perfil.responsavel_contato.strip()
    if "@" not in contato:
        return
    enviar_email_modelo(
        "guia_aceite_confirmado",
        "Publicação autorizada",
        [contato],
        {
            "perfil": perfil,
            "aceite": aceite,
            "nome_guia": configuracao_guia().nome_guia,
            "email_encarregado": configuracao().email_privacidade,
        },
    )


def aceitar_convite(
    token: str, nome_digitado: str, ip: str = "", agente: str = "", avisar: bool = True
) -> AceitePublicacao:
    """O responsável autorizou pela página do link: grava o aceite (nome, data e hora, versão, IP truncado,
    resumo do navegador), marca o convite como usado e publica na hora.

    Trava o convite na transação (dois cliques ao mesmo tempo não geram dois aceites). Levanta ValueError
    se o link não vale mais e PublicacaoRecusada se o perfil deixou de cumprir os requisitos.
    """
    nome_digitado = " ".join(nome_digitado.split())
    with transaction.atomic():
        convite = ConviteAceite.objects.select_for_update().filter(token=token).first()
        if convite is None or not convite.valido():
            raise ValueError("Este link já foi utilizado ou expirou.")
        perfil = PerfilGuia.objects.select_for_update().get(pk=convite.perfil_id)
        if perfil.status == PerfilGuia.Status.REMOVIDO:
            raise ValueError("Este link já foi utilizado ou expirou.")
        faltas = pendencias(perfil, exigir_aceite=False)
        termo = termo_vigente()
        if faltas or termo is None:
            raise PublicacaoRecusada(faltas or ["Não há termo em vigor."])
        aceite = AceitePublicacao.objects.create(
            perfil=perfil,
            termo=termo,
            convite=convite,
            canal=convite.canal,
            nome_digitado=nome_digitado[:120],
            ip_truncado=truncar_ip(ip),
            agente_resumido=resumir_agente(agente),
        )
        convite.usado_em = aceite.aceito_em
        convite.save(update_fields=["usado_em"])
        publicar(perfil, motivo=f"Publicado pelo aceite do responsável (termo v{termo.versao}).")
        from guia.models import ContatoConvite

        ContatoConvite.objects.filter(perfil=perfil).update(situacao=ContatoConvite.Situacao.ACEITOU)
    if avisar:
        _confirmar_por_email(perfil, aceite)
    return aceite


def registrar_aceite_presencial(
    perfil: PerfilGuia, foto: UploadedFile, nome_responsavel: str, por
) -> AceitePublicacao:
    """Plano B: termo impresso e assinado. Foto no storage privado (sem EXIF); o perfil é publicado.

    Levanta ValidationError (foto) ou PublicacaoRecusada (faltam requisitos).
    """
    faltas = pendencias(perfil, exigir_aceite=False)
    termo = termo_vigente()
    if faltas or termo is None:
        raise PublicacaoRecusada(faltas or ["Não há termo em vigor."])
    limpa = foto_termo_limpa(foto)
    with transaction.atomic():
        aceite = AceitePublicacao(
            perfil=perfil,
            termo=termo,
            canal=ConviteAceite.Canal.PRESENCIAL,
            nome_digitado=" ".join(nome_responsavel.split())[:120],
            registrado_por=por,
        )
        aceite.foto_termo.save(limpa.name, limpa, save=False)
        aceite.save()
        publicar(perfil, motivo=f"Publicado pelo termo em papel (termo v{termo.versao}).")
    return aceite


def revogar_aceite(aceite: AceitePublicacao, por, motivo: str = "") -> AceitePublicacao:
    """Revoga a autorização: registra a data e despublica na hora (pausa; nada é apagado aqui).

    O registro do aceite continua guardado como prova (prazo da configuração).
    """
    if aceite.revogado_em is not None:
        raise ValueError("Este aceite já foi revogado.")
    with transaction.atomic():
        aceite.revogado_em = timezone.now()
        aceite.revogado_por = por
        aceite.motivo_revogacao = motivo.strip()
        aceite._change_reason = "Aceite revogado."
        aceite.save(update_fields=["revogado_em", "revogado_por", "motivo_revogacao"])
        perfil = aceite.perfil
        if perfil.status == PerfilGuia.Status.PUBLICADO and aceite_vigente(perfil) is None:
            perfil.status = PerfilGuia.Status.PAUSADO
            perfil._change_reason = "Despublicado: aceite revogado."
            perfil.save(update_fields=["status", "atualizado_em"])
    return aceite


# --- Prévia da ficha (página de aceite e admin) ----------------------------------------------------------


def telefone_legivel(numero: str) -> str:
    """+5565999990001 → (65) 99999-0001."""
    digitos = re.sub(r"\D", "", numero or "")[2:]
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return numero


@dataclass(frozen=True)
class Previa:
    """Exatamente o que a ficha pública vai mostrar (e nada além)."""

    nome: str
    categorias: list[str]
    frase: str
    registro: str
    whatsapp: str
    telefone: str
    local: str
    horarios: list[tuple[str, str]]
    logo: str
    selo: str


def previa(perfil: PerfilGuia) -> Previa:
    """Monta a prévia da ficha. Regulamentada: só nome, especialidade, registro e contato (com o local);
    sem frase, logo nem horário (§5, item 4)."""
    regulamentado = perfil.regulamentado
    if perfil.atendimento == PerfilGuia.Atendimento.ENDERECO:
        bairro = f", {perfil.bairro.nome}" if perfil.bairro_id else ""
        local = f"{perfil.endereco}{bairro} · {perfil.cidade}"
    else:
        local = f"Atende a domicílio: {perfil.area_atendimento} ({perfil.cidade})"
    if perfil.tipo == PerfilGuia.Tipo.EMPRESA:
        selo = "CNPJ verificado" if perfil.cnpj_verificado_em else ""
    elif perfil.tipo == PerfilGuia.Tipo.AUTONOMO:
        selo = "Profissional autônomo"
    else:
        selo = ""
    return Previa(
        nome=perfil.nome_publico,
        categorias=[c.nome for c in perfil.categorias.all()],
        frase="" if regulamentado else perfil.frase,
        registro=perfil.registro_profissional if regulamentado else "",
        whatsapp=telefone_legivel(perfil.whatsapp),
        telefone=telefone_legivel(perfil.telefone),
        local=local,
        horarios=horarios_legiveis(perfil.horarios) if perfil.mostra_horario else [],
        logo=perfil.logo.url if perfil.logo and not regulamentado else "",
        selo=selo,
    )


# --- Carga das categorias ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoCategorias:
    """O que o `carregar_categorias_guia` fez."""

    grupos: int
    criadas: int
    atualizadas: int


def carregar_categorias(caminho: Path = ARQUIVO_CATEGORIAS) -> ResultadoCategorias:
    """Lê o CSV (grupo, nome, slug, ordem, regulamentada, rotulo_registro, sinonimos) e faz upsert por slug.

    Idempotente: rodar de novo só atualiza. Grupos na ordem em que aparecem no arquivo. Categoria que saiu
    do arquivo continua no banco (pode ter empresas): desative no admin. Levanta ValueError se faltar coluna.
    """
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = COLUNAS_CATEGORIAS - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"Colunas faltando no CSV: {', '.join(sorted(faltando))}.")
        linhas = list(leitor)
    grupos: dict[str, GrupoCategoria] = {}
    criadas = atualizadas = 0
    with transaction.atomic():
        for linha in linhas:
            nome_grupo = linha["grupo"].strip()
            if nome_grupo not in grupos:
                grupos[nome_grupo], _ = GrupoCategoria.objects.update_or_create(
                    slug=slugify(nome_grupo), defaults={"nome": nome_grupo, "ordem": len(grupos) + 1}
                )
            regulamentada = linha["regulamentada"].strip() in ("1", "sim", "true", "True")
            _, criada = CategoriaServico.objects.update_or_create(
                slug=linha["slug"].strip(),
                defaults={
                    "grupo": grupos[nome_grupo],
                    "nome": linha["nome"].strip(),
                    "ordem": int(linha["ordem"] or 0),
                    "regulamentada": regulamentada,
                    "rotulo_registro": linha["rotulo_registro"].strip() if regulamentada else "",
                    "sinonimos": linha["sinonimos"].strip(),
                    "estabelecimento": regulamentada and linha["slug"].strip() in ESTABELECIMENTOS_REGULADOS,
                },
            )
            criadas += criada
            atualizadas += not criada
    return ResultadoCategorias(grupos=len(grupos), criadas=criadas, atualizadas=atualizadas)


# --- Páginas públicas (G2; docs/GUIA.md §5 a §7) ------------------------------------------------------

# Fuso de cada estado ("aberto agora" na hora local da cidade). Estado com mais de um fuso: o da capital.
FUSO_POR_UF = {
    "AC": "America/Rio_Branco",
    "AM": "America/Manaus",
    "RR": "America/Boa_Vista",
    "RO": "America/Porto_Velho",
    "MT": "America/Cuiaba",
    "MS": "America/Campo_Grande",
    "PA": "America/Belem",
    "AP": "America/Belem",
    "TO": "America/Araguaina",
    "MA": "America/Fortaleza",
    "PI": "America/Fortaleza",
    "CE": "America/Fortaleza",
    "RN": "America/Fortaleza",
    "PB": "America/Fortaleza",
    "PE": "America/Recife",
    "AL": "America/Maceio",
    "SE": "America/Maceio",
    "BA": "America/Bahia",
}
FUSO_PADRAO = "America/Sao_Paulo"
CHAVES_DIAS = [chave for chave, _ in DIAS_DA_SEMANA]  # segunda = 0, como date.weekday()
VISUALIZACAO = "visualizacoes"
CLIQUE_WHATSAPP = "cliques_whatsapp"
CLIQUE_TELEFONE = "cliques_telefone"
EVENTOS_GUIA = (VISUALIZACAO, CLIQUE_WHATSAPP, CLIQUE_TELEFONE)


def fuso_da_uf(uf: str) -> str:
    """Fuso horário do estado (padrão: Brasília)."""
    return FUSO_POR_UF.get((uf or "").upper(), FUSO_PADRAO)


def guia_no_ar() -> bool:
    """A aba está ligada na configuração do guia."""
    return configuracao_guia().ativo


def pode_ver(usuario) -> tuple[bool, bool]:
    """(pode ver as páginas públicas, é pré-visualização da equipe com o guia desligado)."""
    if guia_no_ar():
        return True, False
    equipe = bool(getattr(usuario, "is_authenticated", False) and usuario.is_staff)
    return equipe, equipe


def perfis_visiveis() -> QuerySet[PerfilGuia]:
    """Perfis que o público vê: publicados, em cidade liberada de estado liberado.

    Demonstração só com MOSTRAR_DEMO (nunca misturada a dados reais sem o aviso). Pausado, removido,
    rascunho ou aguardando aceite não aparecem em lugar nenhum (a ficha dá 404).
    """
    perfis = PerfilGuia.objects.filter(
        status=PerfilGuia.Status.PUBLICADO, cidade__liberada=True, cidade__uf__liberado=True
    ).select_related("cidade", "cidade__uf", "bairro")
    return perfis if settings.MOSTRAR_DEMO else perfis.filter(demo=False)


def perfis_da_cidade(cidade: Cidade) -> QuerySet[PerfilGuia]:
    """Perfis visíveis da cidade."""
    return perfis_visiveis().filter(cidade=cidade)


def cidade_do_guia(uf: str, slug: str) -> Cidade | None:
    """Cidade liberada pela URL (/guia/<uf>/<cidade>/); None se não existe ou não está liberada."""
    return (
        Cidade.objects.filter(liberada=True, uf__liberado=True, uf_id=uf.upper(), slug=slug)
        .select_related("uf")
        .first()
    )


@dataclass(frozen=True)
class CategoriaContada:
    """Categoria com quantas empresas a cidade tem nela."""

    categoria: CategoriaServico
    total: int


def grupos_da_cidade(cidade: Cidade) -> list[tuple[GrupoCategoria, list[CategoriaContada]]]:
    """Grupos e categorias (ativas) com empresas na cidade, com a contagem; grupos vazios ficam de fora."""
    contagem: dict[int, int] = {}
    for categoria_id in perfis_da_cidade(cidade).values_list("categorias", flat=True):
        if categoria_id:
            contagem[categoria_id] = contagem.get(categoria_id, 0) + 1
    categorias = CategoriaServico.objects.filter(pk__in=contagem, ativa=True).select_related("grupo")
    grupos: dict[int, tuple[GrupoCategoria, list[CategoriaContada]]] = {}
    for categoria in categorias.order_by("grupo__ordem", "grupo__nome", "ordem", "nome"):
        grupos.setdefault(categoria.grupo_id, (categoria.grupo, []))[1].append(
            CategoriaContada(categoria, contagem[categoria.pk])
        )
    return list(grupos.values())


def rodizio(perfis, semente: str) -> list[PerfilGuia]:
    """Ordem aleatória estável no dia (semente = data + página), nunca a ordem de cadastro (§5, item 10)."""
    import random

    lista = sorted(perfis, key=lambda p: p.pk)
    random.Random(semente).shuffle(lista)  # noqa: S311 (sorteio de exibição, não segurança)
    return lista


def aberto_agora(perfil: PerfilGuia, agora=None) -> bool | None:
    """Aberto neste momento, no fuso do estado da cidade. Sem horário cadastrado: None (não mostra nada)."""
    from zoneinfo import ZoneInfo

    if not perfil.horarios:
        return None
    local = (agora or timezone.now()).astimezone(ZoneInfo(perfil.fuso or FUSO_PADRAO))
    hora = local.strftime("%H:%M")
    intervalos = perfil.horarios.get(CHAVES_DIAS[local.weekday()]) or []
    return any(inicio <= hora < fim for inicio, fim in intervalos)


def horarios_da_semana(perfil: PerfilGuia, agora=None) -> list[tuple[str, str, bool]]:
    """[(dia, "08:00 às 12:00" ou "Fechado", é hoje)] da semana inteira, para a ficha."""
    from zoneinfo import ZoneInfo

    hoje = (agora or timezone.now()).astimezone(ZoneInfo(perfil.fuso or FUSO_PADRAO)).weekday()
    linhas = []
    for indice, (chave, dia) in enumerate(DIAS_DA_SEMANA):
        intervalos = (perfil.horarios or {}).get(chave) or []
        texto = " e ".join(f"{inicio} às {fim}" for inicio, fim in intervalos) or "Fechado"
        linhas.append((dia, texto, indice == hoje))
    return linhas


def filtrar_lista(perfis: list[PerfilGuia], aberto: bool = False, bairro: str = "") -> list[PerfilGuia]:
    """Filtros da lista de uma categoria: "Aberto agora" e bairro (slug)."""
    if bairro:
        perfis = [p for p in perfis if p.bairro_id and p.bairro.slug == bairro]
    if aberto:
        agora = timezone.now()
        perfis = [p for p in perfis if aberto_agora(p, agora)]
    return perfis


def indexavel(total: int) -> bool:
    """Cidade + categoria só vai ao Google com o mínimo da configuração (página fina: noindex, follow)."""
    return total >= configuracao_guia().minimo_empresas_indexar


def pontos_do_mapa(perfis: list[PerfilGuia]) -> list[dict]:
    """Só quem tem endereço comercial e só o `ponto_publico` (a domicílio fica fora do mapa)."""
    return [
        {
            "nome": p.nome_publico,
            "url": reverse("guia:empresa", args=[p.slug]),
            "lat": round(p.ponto_publico.y, 6),
            "lng": round(p.ponto_publico.x, 6),
        }
        for p in perfis
        if p.atendimento == PerfilGuia.Atendimento.ENDERECO and p.ponto_publico is not None
    ]


def ponto_da_ficha(perfil: PerfilGuia) -> dict | None:
    """Mapa da ficha (mesmo formato do mapa do anúncio): só com endereço comercial."""
    if perfil.atendimento != PerfilGuia.Atendimento.ENDERECO or perfil.ponto_publico is None:
        return None
    return {"tipo": "exata", "lat": perfil.ponto_publico.y, "lng": perfil.ponto_publico.x}


def buscar_no_guia(termo: str, cidade: Cidade | None = None, limite: int = 48) -> tuple[list, list]:
    """Busca por texto (nome, categoria e sinônimos) sem acento e tolerante a erro de digitação.

    Devolve (perfis, categorias). `unaccent` + `pg_trgm` (word similarity) do PostgreSQL.
    """
    from anuncios.indice import sem_acento

    termo = " ".join((termo or "").split())[:100]
    if len(termo) < 2:
        return [], []
    limpo = sem_acento(termo)
    categorias = CategoriaServico.objects.filter(ativa=True).filter(
        Q(nome__unaccent__icontains=limpo)
        | Q(sinonimos__unaccent__icontains=limpo)
        | Q(nome__unaccent__trigram_word_similar=limpo)
    )
    perfis = perfis_visiveis() if cidade is None else perfis_da_cidade(cidade)
    perfis = perfis.filter(
        Q(nome_publico__unaccent__icontains=limpo)
        | Q(nome_publico__unaccent__trigram_word_similar=limpo)
        | Q(categorias__in=categorias)
    ).distinct()
    return rodizio(perfis[: limite * 2], f"busca-{timezone.localdate()}")[:limite], list(categorias[:12])


def link_whatsapp_perfil(perfil: PerfilGuia) -> str:
    """wa.me com a mensagem pronta (só montado no redirecionamento: o número nunca vai ao HTML)."""
    from core.services import configuracao

    texto = f"Olá! Vi {perfil.nome_publico} no {configuracao_guia().nome_guia} do {configuracao().nome}."
    return url_whatsapp(perfil.whatsapp, texto)


def contato_liberado(request) -> bool:
    """Limite de contatos revelados por visitante por hora (IP só como resumo; contra robôs coletores)."""
    from core.services import limite_por_ip_excedido

    limite = configuracao_guia().contatos_por_hora
    return not limite_por_ip_excedido(request, "guia_contato", limite=limite, janela_segundos=3600)


def registrar_evento(request, perfil: PerfilGuia, evento: str) -> bool:
    """+1 no total do dia do perfil (visualização ou clique), uma vez por visitante por dia.

    Mesma regra das estatísticas dos anúncios: sem IP e sem cookie (hash do dia com sal aleatório só no
    cache), robôs e a equipe logada não contam. Nunca derruba a página. Devolve True se contou.
    """
    from django.db import IntegrityError
    from django.db.models import F

    from estatisticas.services import _segundos_ate_o_fim_do_dia, assinatura_do_visitante, e_robo
    from guia.models import EstatisticaGuiaDia

    if evento not in EVENTOS_GUIA:
        raise ValueError(f"Evento desconhecido: {evento}")
    usuario = getattr(request, "user", None)
    if e_robo(request) or (usuario is not None and usuario.is_authenticated and usuario.is_staff):
        return False
    agora = timezone.now()
    dia = timezone.localdate(agora)
    marca = f"guia:{evento}:{perfil.pk}:{dia:%Y%m%d}:{assinatura_do_visitante(request, dia)}"
    if not cache.add(marca, 1, timeout=_segundos_ate_o_fim_do_dia(agora)):
        return False
    linhas = EstatisticaGuiaDia.objects.filter(perfil=perfil, dia=dia)
    if not linhas.update(**{evento: F(evento) + 1}):
        try:
            with transaction.atomic():
                EstatisticaGuiaDia.objects.create(perfil=perfil, dia=dia, **{evento: 1})
        except IntegrityError:  # outro acesso criou a linha no mesmo instante
            linhas.update(**{evento: F(evento) + 1})
    return True


def schema_da_ficha(perfil: PerfilGuia, url: str) -> dict:
    """schema.org LocalBusiness da ficha. Sem telefone (o número não vai em texto ao HTML, §7)."""
    regulamentado = perfil.regulamentado
    schema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": perfil.nome_publico,
        "url": url,
        "areaServed": perfil.area_atendimento or f"{perfil.cidade.nome}/{perfil.cidade.uf_id}",
    }
    if perfil.frase and not regulamentado:
        schema["description"] = perfil.frase
    if perfil.logo and not regulamentado:
        schema["image"] = settings.SITE_URL + perfil.logo.url
    if perfil.atendimento == PerfilGuia.Atendimento.ENDERECO:
        schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": perfil.endereco,
            "addressLocality": perfil.cidade.nome,
            "addressRegion": perfil.cidade.uf_id,
            "addressCountry": "BR",
        }
        if perfil.ponto_publico is not None:
            schema["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": round(perfil.ponto_publico.y, 6),
                "longitude": round(perfil.ponto_publico.x, 6),
            }
    if perfil.horarios and perfil.mostra_horario:
        nomes = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        schema["openingHoursSpecification"] = [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": nomes[i], "opens": inicio, "closes": fim}
            for i, chave in enumerate(CHAVES_DIAS)
            for inicio, fim in perfil.horarios.get(chave) or []
        ]
    return schema


def url_categoria(cidade: Cidade, categoria: CategoriaServico) -> str:
    """/guia/<uf>/<cidade>/<categoria>/."""
    return reverse("guia:categoria", args=[cidade.uf_id.lower(), cidade.slug, categoria.slug])


def paginas_do_sitemap() -> list[str]:
    """Caminhos do guia para o sitemap (só com o guia no ar): /guia/, cidades com empresas, cidade +
    categoria com o mínimo para indexar (página fina fica fora) e as fichas publicadas."""
    if not guia_no_ar():
        return []
    caminhos = [reverse("guia:inicio")]
    perfis = list(perfis_visiveis().prefetch_related("categorias"))
    cidades: dict[int, Cidade] = {}
    contagem: dict[tuple[int, int], int] = {}
    categorias: dict[int, CategoriaServico] = {}
    for perfil in perfis:
        cidades[perfil.cidade_id] = perfil.cidade
        for categoria in perfil.categorias.all():
            if categoria.ativa:
                categorias[categoria.pk] = categoria
                contagem[(perfil.cidade_id, categoria.pk)] = (
                    contagem.get((perfil.cidade_id, categoria.pk), 0) + 1
                )
    for cidade in sorted(cidades.values(), key=lambda c: c.pk):
        caminhos.append(reverse("guia:cidade", args=[cidade.uf_id.lower(), cidade.slug]))
    for (cidade_id, categoria_id), total in sorted(contagem.items()):
        if indexavel(total):
            caminhos.append(url_categoria(cidades[cidade_id], categorias[categoria_id]))
    caminhos.extend(reverse("guia:empresa", args=[p.slug]) for p in sorted(perfis, key=lambda p: p.pk))
    return caminhos


# --- G3: pedidos do titular, remoção e limpeza (docs/GUIA.md §5, item 8; GUIA_LGPD_E_TERMO.md §5) --------


def pedido_vencido(pedido: PedidoDoPerfil, hoje=None) -> bool:
    """Ainda sem resposta final e com o prazo (15 dias) já passado."""
    em_aberto = pedido.status in (PedidoDoPerfil.Status.ABERTO, PedidoDoPerfil.Status.EM_ANDAMENTO)
    return em_aberto and pedido.prazo_ate < (hoje or timezone.localdate())


def registrar_pedido(
    perfil: PerfilGuia, tipo: str, descricao: str, contato: str, origem: str = PedidoDoPerfil.Origem.FICHA
) -> PedidoDoPerfil:
    """Grava o pedido do titular (prazo de 15 dias) e avisa a equipe (Moderador e Administrador) por e-mail.

    O aviso leva só o tipo, o perfil e o link do admin: o contato e a descrição ficam no admin.
    """
    from core.services import enviar_email_modelo
    from moderacao.services import destinatarios_moderacao

    pedido = PedidoDoPerfil.objects.create(
        perfil=perfil,
        tipo=tipo,
        descricao=descricao.strip()[:1000],
        contato=contato.strip()[:200],
        origem=origem,
    )
    enviar_email_modelo(
        "guia_pedido_novo",
        "Pedido novo no guia",
        destinatarios_moderacao(),
        {
            "pedido": pedido,
            "link_admin": settings.SITE_URL + reverse("admin:guia_pedidodoperfil_change", args=[pedido.pk]),
        },
    )
    return pedido


def responder_pedido(pedido: PedidoDoPerfil, por, status: str, resposta: str = "") -> PedidoDoPerfil:
    """Fecha (ou marca em andamento) o pedido, com quem decidiu, quando e o que foi feito."""
    pedido.status = status
    pedido.resposta = resposta.strip() or pedido.resposta
    if status in (PedidoDoPerfil.Status.ATENDIDO, PedidoDoPerfil.Status.RECUSADO):
        pedido.decidido_por, pedido.decidido_em = por, timezone.now()
    pedido._change_reason = f"Pedido {pedido.get_status_display().lower()}."
    pedido.save()
    return pedido


def remover_perfil(
    perfil: PerfilGuia, por=None, motivo: str = "", pedido: PedidoDoPerfil | None = None
) -> PerfilGuia:
    """Remoção (pedido do titular): despublica na hora e apaga logo, WhatsApp, telefone e o contato do
    responsável, também no histórico. Ficam só o registro do aceite e o do pedido, pelo prazo de prova
    (`prazo_prova_aceite_anos`); depois a limpeza diária apaga o resto (`limpar_guia_vencido`).

    Com `pedido`, ele é fechado como atendido; se o contato do pedido for um e-mail, vai a confirmação.
    """
    from core.services import enviar_email_modelo

    agora = timezone.now()
    with transaction.atomic():
        perfil = PerfilGuia.objects.select_for_update().get(pk=perfil.pk)
        if perfil.logo:
            perfil.logo.delete(save=False)
        perfil.logo = ""
        perfil.whatsapp = perfil.telefone = perfil.responsavel_contato = ""
        perfil.status = PerfilGuia.Status.REMOVIDO
        perfil.removido_em = agora
        perfil._change_reason = f"Removido: {motivo.strip() or 'pedido do titular'}"[:100]
        perfil.save()
        PerfilGuia.history.filter(id=perfil.pk).update(
            whatsapp="", telefone="", responsavel_contato="", logo=""
        )
        perfil.convites.filter(usado_em__isnull=True, expira_em__gt=agora).update(expira_em=agora)
        if pedido is not None:
            responder_pedido(
                pedido, por, PedidoDoPerfil.Status.ATENDIDO, motivo or "Perfil removido do guia."
            )
    if pedido is not None and "@" in pedido.contato:
        enviar_email_modelo(
            "guia_remocao_confirmada",
            "Ficha removida do guia",
            [pedido.contato],
            {"perfil": perfil, "nome_guia": configuracao_guia().nome_guia},
        )
    return perfil


def limpar_guia_vencido(hoje=None) -> int:
    """Rotina diária: passado o prazo de prova, apaga de vez o perfil removido com aceites (e fotos do termo),
    convites, pedidos, estatísticas e histórico; e os pedidos já decididos de qualquer perfil. Devolve
    quantos perfis saíram."""
    from datetime import datetime, time

    anos = configuracao_guia().prazo_prova_aceite_anos
    hoje = hoje or timezone.localdate()
    limite = timezone.make_aware(datetime.combine(hoje, time.min)) - timedelta(days=round(365.25 * anos))
    vencidos = list(
        PerfilGuia.objects.filter(status=PerfilGuia.Status.REMOVIDO, removido_em__lt=limite).values_list(
            "pk", flat=True
        )
    )
    from guia.models import ContatoConvite, EstatisticaGuiaDia

    with transaction.atomic():
        antigos = PedidoDoPerfil.objects.filter(
            status__in=(PedidoDoPerfil.Status.ATENDIDO, PedidoDoPerfil.Status.RECUSADO),
            decidido_em__lt=limite,
        )
        PedidoDoPerfil.history.filter(id__in=list(antigos.values_list("pk", flat=True))).delete()
        antigos.delete()
        if not vencidos:
            return 0
        for aceite in AceitePublicacao.objects.filter(perfil_id__in=vencidos).exclude(foto_termo=""):
            aceite.foto_termo.delete(save=False)
        PedidoDoPerfil.history.filter(perfil_id__in=vencidos).delete()
        PedidoDoPerfil.objects.filter(perfil_id__in=vencidos).delete()
        AceitePublicacao.history.filter(perfil_id__in=vencidos).delete()
        AceitePublicacao.objects.filter(perfil_id__in=vencidos).delete()
        ConviteAceite.objects.filter(perfil_id__in=vencidos).delete()
        EstatisticaGuiaDia.objects.filter(perfil_id__in=vencidos).delete()
        ContatoConvite.objects.filter(perfil_id__in=vencidos).update(perfil=None)
        PerfilGuia.objects.filter(pk__in=vencidos).delete()
        PerfilGuia.history.filter(id__in=vencidos).delete()
    return len(vencidos)


# --- G3: termo novo (docs/GUIA.md §5, item 3) -------------------------------------------------------------


def prazo_do_termo(termo: TermoGuia):
    """Último dia para aceitar a versão: início da vigência + `dias_aceite_termo_novo` (30)."""
    return termo.vigente_desde + timedelta(days=configuracao_guia().dias_aceite_termo_novo)


@dataclass(frozen=True)
class PendenteDoTermo:
    """Perfil publicado que ainda não aceitou a versão vigente."""

    perfil: PerfilGuia
    dias_restantes: int
    convite_ate: object  # datetime do convite válido, ou None


def pendentes_do_termo(hoje=None) -> list[PendenteDoTermo]:
    """Publicados sem aceite da versão em vigor, com os dias que faltam (negativo = prazo passado)."""
    termo = termo_vigente(hoje)
    if termo is None:
        return []
    hoje = hoje or timezone.localdate()
    dias = (prazo_do_termo(termo) - hoje).days
    agora = timezone.now()
    aceitaram = AceitePublicacao.objects.filter(termo=termo, revogado_em__isnull=True).values("perfil_id")
    perfis = (
        PerfilGuia.objects.filter(status=PerfilGuia.Status.PUBLICADO)
        .exclude(pk__in=aceitaram)
        .select_related("cidade")
        .order_by("nome_publico")
    )
    resultado = []
    for perfil in perfis:
        convite = (
            perfil.convites.filter(usado_em__isnull=True, expira_em__gt=agora).order_by("-expira_em").first()
        )
        resultado.append(PendenteDoTermo(perfil, dias, convite.expira_em if convite else None))
    return resultado


def convidar_para_termo_novo(hoje=None) -> int:
    """Termo novo em vigor: cria o link de aceite (vale até o fim do prazo) para cada publicado sem aceite e
    sem link válido. Se o contato do responsável for e-mail, manda o aviso com o link (aviso de mudança a
    quem já autorizou; não é convite em massa). WhatsApp: a equipe envia um a um pelo admin."""
    from datetime import datetime, time

    from core.services import enviar_email_modelo

    termo = termo_vigente(hoje)
    if termo is None:
        return 0
    fim = timezone.make_aware(datetime.combine(prazo_do_termo(termo), time(23, 59)))
    criados = 0
    for pendente in pendentes_do_termo(hoje):
        if pendente.convite_ate is not None:
            continue
        perfil = pendente.perfil
        if perfil.aceites.filter(termo=termo).exists():
            continue
        try:
            _, token = gerar_convite(perfil, None, ConviteAceite.Canal.EMAIL, expira_em=fim)
        except PublicacaoRecusada:
            continue
        criados += 1
        contato = perfil.responsavel_contato.strip()
        if "@" in contato:
            enviar_email_modelo(
                "guia_termo_novo",
                "Atualizamos o termo do guia",
                [contato],
                {
                    "perfil": perfil,
                    "termo": termo,
                    "prazo": prazo_do_termo(termo),
                    "link": link_aceite(token),
                    "nome_guia": configuracao_guia().nome_guia,
                },
            )
    return criados


def pausar_sem_aceite_do_termo(hoje=None) -> int:
    """Passado o prazo do termo novo sem aceite, pausa o perfil (nunca apaga); volta com o aceite."""
    termo = termo_vigente(hoje)
    hoje = hoje or timezone.localdate()
    if termo is None or hoje <= prazo_do_termo(termo):
        return 0
    pausados = 0
    for pendente in pendentes_do_termo(hoje):
        pausar(pendente.perfil, f"Pausado: sem aceite do termo v{termo.versao} no prazo.")
        pausados += 1
    return pausados


def rotina_do_guia(hoje=None) -> dict[str, int]:
    """Rotina diária (Celery beat): convites do termo novo, pausa de quem passou do prazo, limpeza LGPD."""
    return {
        "convites_termo": convidar_para_termo_novo(hoje),
        "pausados_termo": pausar_sem_aceite_do_termo(hoje),
        "removidos_de_vez": limpar_guia_vencido(hoje),
    }


# --- G3: lista de convites e "não contatar" (docs/GUIA.md §9) ----------------------------------------------


def numero_bloqueado(whatsapp: str) -> bool:
    """O número recusou ou pediu para não ser contatado (vale para qualquer convite)."""
    from guia.models import ContatoConvite

    return (
        bool(whatsapp)
        and ContatoConvite.objects.filter(whatsapp=whatsapp, situacao__in=ContatoConvite.BLOQUEADOS).exists()
    )


@dataclass
class ResultadoImportacao:
    """Prévia da importação: linhas válidas (prontas para gravar), erros e linhas ignoradas, por número."""

    validas: list[dict]
    erros: list[tuple[int, str]]
    ignoradas: list[tuple[int, str]]


COLUNAS_CONVITES = {"nome", "whatsapp", "cidade"}
LIMITE_LINHAS_IMPORTACAO = 2000


def _cidade_do_csv(texto: str) -> Cidade | None:
    """ "Tangará da Serra", "Tangará da Serra/MT" ou "tangara-da-serra": só cidades liberadas."""
    nome, _, uf = texto.replace(" - ", "/").partition("/")
    cidades = Cidade.objects.filter(liberada=True, uf__liberado=True, slug=slugify(nome))
    if uf.strip():
        cidades = cidades.filter(uf_id=uf.strip().upper())
    return cidades.first() if cidades.count() == 1 else None


def ler_csv_convites(texto: str) -> ResultadoImportacao:
    """Lê o CSV (nome, whatsapp, cidade[, categoria]) e diz o que entra, o que tem erro e o que fica de fora.

    Não grava nada (é a prévia). Fica de fora: número repetido no arquivo ou já na lista (mesmo bloqueado).
    Levanta ValueError se faltar coluna ou se passar de `LIMITE_LINHAS_IMPORTACAO` linhas.
    """
    from anunciantes.validators import normalizar_whatsapp
    from guia.models import ContatoConvite

    leitor = csv.DictReader(
        io.StringIO(texto.lstrip("﻿")), delimiter=";" if texto.count(";") > texto.count(",") else ","
    )
    colunas = {c.strip().lower() for c in (leitor.fieldnames or [])}
    faltando = COLUNAS_CONVITES - colunas
    if faltando:
        raise ValueError(
            f"Colunas faltando: {', '.join(sorted(faltando))}. Use: nome, whatsapp, cidade, categoria."
        )
    resultado = ResultadoImportacao([], [], [])
    vistos: set[str] = set()
    for numero, bruta in enumerate(leitor, start=2):  # linha 1 = cabeçalho
        if numero - 1 > LIMITE_LINHAS_IMPORTACAO:
            raise ValueError(f"Máximo de {LIMITE_LINHAS_IMPORTACAO} linhas por arquivo.")
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in bruta.items()}
        if not any(linha.values()):
            continue
        problemas = []
        nome = linha.get("nome", "")[:120]
        if not nome:
            problemas.append("nome vazio")
        try:
            whatsapp = normalizar_whatsapp(linha.get("whatsapp", ""))
        except ValidationError:
            whatsapp = ""
            problemas.append(f"WhatsApp inválido ({linha.get('whatsapp', '') or 'vazio'})")
        cidade = _cidade_do_csv(linha.get("cidade", ""))
        if cidade is None:
            problemas.append(f"cidade não atendida ou não encontrada ({linha.get('cidade', '') or 'vazia'})")
        categoria = None
        if linha.get("categoria"):
            categoria = CategoriaServico.objects.filter(
                Q(slug=slugify(linha["categoria"])) | Q(nome__iexact=linha["categoria"])
            ).first()
            if categoria is None:
                problemas.append(f"categoria desconhecida ({linha['categoria']})")
        if problemas:
            resultado.erros.append((numero, "; ".join(problemas)))
            continue
        if whatsapp in vistos:
            resultado.ignoradas.append((numero, "número repetido no arquivo"))
            continue
        vistos.add(whatsapp)
        existente = ContatoConvite.objects.filter(whatsapp=whatsapp).first()
        if existente is not None:
            motivo = "não contatar" if existente.bloqueado else "já está na lista"
            resultado.ignoradas.append((numero, f"{motivo} ({existente.nome})"))
            continue
        resultado.validas.append(
            {"linha": numero, "nome": nome, "whatsapp": whatsapp, "cidade": cidade, "categoria": categoria}
        )
    return resultado


def importar_convites(texto: str, origem: str = "lista_antiga") -> int:
    """Grava as linhas válidas do CSV (a mesma leitura da prévia). Devolve quantos contatos entraram."""
    from guia.models import ContatoConvite

    validas = ler_csv_convites(texto).validas
    with transaction.atomic():
        for linha in validas:
            ContatoConvite.objects.create(
                nome=linha["nome"],
                whatsapp=linha["whatsapp"],
                cidade=linha["cidade"],
                categoria=linha["categoria"],
                origem=origem,
            )
    return len(validas)


def mensagem_convite_contato(contato, por=None) -> str:
    """Primeiro contato (docs/GUIA_LGPD_E_TERMO.md §4): ainda sem ficha, então sem link; quem disser "sim"
    ganha o perfil e o link de aceite depois. Montada no servidor."""
    from core.services import configuracao

    config = configuracao()
    quem = (getattr(por, "nome", "") or "").split(" ")[0] or "a equipe"
    cidade = config.cidade_sede.split(",")[0].strip()
    return (
        f"Olá, {contato.nome.split(' ')[0]}! Aqui é {quem}, do {config.nome}, de {cidade}. "
        "Estou montando um guia "
        f"gratuito de serviços e comércios da região e queria incluir {contato.nome}, sem custo. Antes de "
        "publicar, você confere como vai aparecer e autoriza por um link que eu te mando. Posso montar a sua "
        'ficha?\nSe preferir não participar, é só responder "não" e eu não entro em contato de novo.'
    )


def convidar_contato(contato, por=None) -> str:
    """Marca o contato como convidado (com a data) e devolve o wa.me com a mensagem. Um por vez, pela equipe.
    Levanta ValueError se o número estiver bloqueado ("recusou" / "não contatar")."""
    if contato.bloqueado or numero_bloqueado(contato.whatsapp):
        raise ValueError("Este número recusou ou pediu para não ser contatado: não envie convite.")
    contato.situacao = contato.Situacao.CONVIDADO
    contato.convidado_em = timezone.now()
    contato._change_reason = "Convidado pelo WhatsApp."
    contato.save(update_fields=["situacao", "convidado_em"])
    return url_whatsapp(contato.whatsapp, mensagem_convite_contato(contato, por))


def marcar_contato(contato, situacao: str) -> None:
    """Recusou / não contatar (bloqueia novos convites) ou volta a "novo"."""
    contato.situacao = situacao
    contato._change_reason = f"Marcado como {contato.get_situacao_display().lower()}."
    contato.save(update_fields=["situacao"])


def criar_perfil_do_contato(contato, por=None) -> PerfilGuia:
    """Quem disse "sim": vira rascunho de `PerfilGuia` (origem lista antiga), que a equipe completa e envia o
    link de aceite. Reaproveita o perfil já criado para o contato."""
    if contato.perfil_id:
        return contato.perfil
    if contato.bloqueado:
        raise ValueError("Este número recusou ou pediu para não ser contatado.")
    perfil = PerfilGuia.objects.create(
        nome_publico=contato.nome,
        tipo=PerfilGuia.Tipo.AUTONOMO,
        responsavel_nome=contato.nome,
        whatsapp=contato.whatsapp,
        cidade=contato.cidade,
        origem=PerfilGuia.Origem.LISTA_ANTIGA,
        cadastrado_por=por,
        demo=contato.demo,
    )
    if contato.categoria_id:
        perfil.categorias.set([contato.categoria])
    contato.perfil = perfil
    contato.save(update_fields=["perfil"])
    return perfil


# --- G3: fila, lotes, CSV e estatísticas -------------------------------------------------------------------


def perfis_com_duplicidade() -> QuerySet[PerfilGuia]:
    """Perfis que dividem CNPJ, resumo do CPF ou WhatsApp com outro (fora os removidos)."""
    from django.db.models import Exists, OuterRef

    base = PerfilGuia.objects.exclude(status=PerfilGuia.Status.REMOVIDO)
    outros = base.exclude(pk=OuterRef("pk"))
    return base.filter(
        Exists(outros.filter(cnpj=OuterRef("cnpj")).exclude(cnpj=""))
        | Exists(outros.filter(cpf_hash=OuterRef("cpf_hash")).exclude(cpf_hash=""))
        | Exists(outros.filter(whatsapp=OuterRef("whatsapp")).exclude(whatsapp=""))
    )


def pausar_em_lote(perfis, motivo: str = "Pausado em lote pela equipe.") -> int:
    """Pausa os publicados do conjunto (os outros ficam como estão). Devolve quantos pausou."""
    total = 0
    for perfil in perfis:
        if perfil.status == PerfilGuia.Status.PUBLICADO:
            pausar(perfil, motivo)
            total += 1
    return total


def reativar_em_lote(perfis) -> tuple[int, list[str]]:
    """Volta ao ar os pausados que ainda cumprem os requisitos (com aceite vigente). (quantos, falhas)."""
    total, falhas = 0, []
    for perfil in perfis:
        if perfil.status != PerfilGuia.Status.PAUSADO:
            continue
        try:
            publicar(perfil, motivo="Reativado em lote pela equipe.")
            total += 1
        except PublicacaoRecusada as erro:
            falhas.append(f"{perfil.nome_publico}: {erro.pendencias[0]}")
    return total, falhas


def celula_csv(valor) -> str:
    """Texto seguro para planilha: neutraliza fórmula (começo com = + - @, tab ou CR) com um apóstrofo."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _csv(cabecalho: list[str], linhas) -> str:
    """CSV com ; (abre direto no Excel em português) e todas as células neutralizadas."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([celula_csv(v) for v in linha])
    return "﻿" + saida.getvalue()


def csv_perfis(perfis) -> str:
    """Exportação dos perfis (dados públicos e situação; sem documento nem contato do responsável)."""
    linhas = (
        [
            p.nome_publico,
            p.cidade.nome,
            p.cidade.uf_id,
            ", ".join(c.nome for c in p.categorias.all()),
            p.get_tipo_display(),
            p.get_status_display(),
            p.get_origem_display(),
            p.whatsapp,
            p.telefone,
            timezone.localtime(p.criado_em).strftime("%d/%m/%Y"),
            timezone.localtime(p.publicado_em).strftime("%d/%m/%Y") if p.publicado_em else "",
        ]
        for p in perfis.select_related("cidade").prefetch_related("categorias")
    )
    cabecalho = ["nome", "cidade", "uf", "categorias", "tipo", "situacao", "origem", "whatsapp", "telefone",
                 "criado_em", "publicado_em"]  # fmt: skip
    return _csv(cabecalho, linhas)


def estatisticas_do_guia(dias: int = 30) -> dict:
    """Totais dos últimos `dias` dias (hoje incluído): por perfil e por categoria, mais vistos primeiro."""
    from django.db.models import Sum

    from guia.models import EstatisticaGuiaDia

    inicio = timezone.localdate() - timedelta(days=dias - 1)
    soma = {
        "visualizacoes": Sum("visualizacoes"),
        "cliques_whatsapp": Sum("cliques_whatsapp"),
        "cliques_telefone": Sum("cliques_telefone"),
    }
    base = EstatisticaGuiaDia.objects.filter(dia__gte=inicio)
    por_perfil = list(
        base.values("perfil_id", "perfil__nome_publico", "perfil__cidade__nome")
        .annotate(**soma)
        .order_by("-visualizacoes", "perfil__nome_publico")
    )
    por_categoria = list(base.values("perfil__categorias__nome").annotate(**soma).order_by("-visualizacoes"))
    total = base.aggregate(**soma)
    return {
        "dias": dias,
        "inicio": inicio,
        "por_perfil": por_perfil,
        "por_categoria": por_categoria,
        "total": total,
    }


def csv_estatisticas(dias: int = 30) -> str:
    """Exportação das estatísticas por perfil do período."""
    dados = estatisticas_do_guia(dias)
    linhas = (
        [
            d["perfil__nome_publico"],
            d["perfil__cidade__nome"],
            d["visualizacoes"] or 0,
            d["cliques_whatsapp"] or 0,
            d["cliques_telefone"] or 0,
        ]
        for d in dados["por_perfil"]
    )
    return _csv(["perfil", "cidade", "visualizacoes", "cliques_whatsapp", "cliques_telefone"], linhas)


# --- Demonstração ------------------------------------------------------------------------------------

AGENTE_DEMO = "Mozilla/5.0 (Linux; Android 14) Chrome/120"
CATEGORIAS_DEMO = [
    "eletricista",
    "encanador",
    "pintor",
    "vidraceiro-e-vidracaria",
    "diarista",
    "chaveiro",
    "cabeleireiro",
    "mecanica",
    "restaurante",
    "padaria-e-confeitaria",
    "dentista",
    "serralheiro",
]
# Categoria → (tipo, atende em endereço?, horário, nomes). Autônomos atendem a domicílio (CPF só em resumo).
H_COMERCIO = {d: [["08:00", "18:00"]] for d in ("seg", "ter", "qua", "qui", "sex")} | {
    "sab": [["08:00", "12:00"]]
}
H_RESTAURANTE = {
    d: [["11:00", "14:30"], ["18:00", "23:00"]] for d in ("ter", "qua", "qui", "sex", "sab", "dom")
}
H_PADARIA = {d: [["06:00", "20:00"]] for d in ("seg", "ter", "qua", "qui", "sex", "sab")} | {
    "dom": [["06:00", "12:00"]]
}
MODELOS_DEMO = {
    "eletricista": (
        "autonomo",
        False,
        H_COMERCIO,
        ["João Eletricista", "Faísca Instalações", "Carlos Luz", "Pedro Elétrica", "Zé da Fiação"],
    ),
    "encanador": (
        "autonomo",
        False,
        H_COMERCIO,
        ["Hidráulica Rápida", "Marcos Encanador", "Vazamento Zero", "Tião Hidráulica"],
    ),
    "pintor": ("autonomo", False, {}, ["Ana Pinturas", "Cor & Arte Pintor", "Renato Pintor"]),
    "vidraceiro-e-vidracaria": (
        "empresa",
        True,
        H_COMERCIO,
        ["Vidraçaria Boa Vista", "Vidros Cristal", "Box & Espelho"],
    ),
    "diarista": (
        "autonomo",
        False,
        {},
        ["Diarista Lúcia", "Limpeza Brilho", "Dona Rosa Diarista", "Casa Limpa"],
    ),
    "chaveiro": ("empresa", True, H_COMERCIO, ["Chaveiro 24h Centro", "Chave Mestra", "Chaveiro Rápido"]),
    "cabeleireiro": (
        "empresa",
        True,
        H_COMERCIO,
        ["Salão Bela Flor", "Studio Cachos", "Barbearia do Léo", "Espaço Beleza", "Salão Charme"],
    ),
    "mecanica": (
        "empresa",
        True,
        H_COMERCIO,
        ["Oficina do Zé", "Auto Center Serra", "Mecânica Pé na Estrada", "Motor Bom", "Oficina 3 Irmãos"],
    ),
    "restaurante": (
        "empresa",
        True,
        H_RESTAURANTE,
        ["Restaurante Sabor da Serra", "Cantina da Nona", "Peixaria do Rio", "Churrascaria Pantanal"],
    ),
    "padaria-e-confeitaria": (
        "empresa",
        True,
        H_PADARIA,
        ["Padaria Pão Quente", "Doce Trigo", "Panificadora Central"],
    ),
    "dentista": (
        "profissional_regulamentado",
        True,
        H_COMERCIO,
        ["Dra. Carla Souza", "Dr. Paulo Lima", "Dra. Ana Ribeiro"],
    ),
    "serralheiro": ("empresa", True, H_COMERCIO, ["Serralheria Ferro Forte", "Portões Serra"]),
}
# Cidade IBGE → {categoria: quantos}. Tangará tem categorias com 3+ (indexáveis) e algumas finas.
DISTRIBUICAO_DEMO = {
    5107958: {"eletricista": 4, "encanador": 3, "pintor": 2, "vidraceiro-e-vidracaria": 3, "diarista": 3,
              "chaveiro": 2, "cabeleireiro": 4, "mecanica": 3, "restaurante": 3, "padaria-e-confeitaria": 2,
              "dentista": 3, "serralheiro": 1},
    5101704: {"eletricista": 2, "encanador": 1, "diarista": 1, "chaveiro": 1, "cabeleireiro": 3,
              "mecanica": 3,
              "restaurante": 2, "padaria-e-confeitaria": 1, "dentista": 1},
    5102637: {"eletricista": 1, "encanador": 1, "pintor": 1, "vidraceiro-e-vidracaria": 1, "cabeleireiro": 2,
              "mecanica": 3, "restaurante": 3, "padaria-e-confeitaria": 2, "dentista": 1, "serralheiro": 1},
}  # fmt: skip
# Os n-ésimos perfis criados que fogem do "publicado": um pausado, dois aguardando aceite, um rascunho.
SITUACAO_DEMO = {5: "pausado", 9: "aguardando_aceite", 21: "aguardando_aceite", 40: "rascunho"}


def _documento_demo(base: str, valido) -> str:
    """Completa `base` com os 2 dígitos que tornam o documento válido (CNPJ ou CPF fictício)."""
    return next(base + f"{n:02d}" for n in range(100) if valido(base + f"{n:02d}"))


def criar_guia_demo() -> int:
    """Categorias (carga do CSV se o banco estiver vazio) e cerca de 60 perfis fictícios em 3 cidades e 12
    categorias, marcados como demo.

    Mistura empresa com CNPJ (metade com "CNPJ verificado"), autônomo a domicílio (só o resumo do CPF),
    regulamentado (dentista, com registro), com e sem horário, um pausado, dois aguardando aceite e um
    rascunho; os publicados têm aceite registrado na versão vigente. Bairros demo da cidade, se houver.
    Telefones inexistentes, e-mails @demo.invalid. Recria do zero (apaga os demo do guia antes).
    """
    from anunciantes.validators import cnpj_valido
    from core.models import Bairro

    apagar_guia_demo()
    if not CategoriaServico.objects.exists():
        carregar_categorias()
    categorias = {c.slug: c for c in CategoriaServico.objects.filter(slug__in=CATEGORIAS_DEMO)}
    termo = termo_vigente()
    cidades = {c.codigo_ibge: c for c in Cidade.objects.filter(codigo_ibge__in=DISTRIBUICAO_DEMO)}
    n = 0
    for ibge, quantos in DISTRIBUICAO_DEMO.items():
        cidade = cidades.get(ibge)
        if cidade is None:
            continue
        bairros = list(Bairro.objects.filter(cidade=cidade, ativo=True).order_by("pk"))
        for slug, total in quantos.items():
            tipo, endereco, horario, nomes = MODELOS_DEMO[slug]
            for i in range(total):
                n += 1
                sem_horario = n % 7 == 0
                perfil = PerfilGuia(
                    demo=True,
                    nome_publico=f"{nomes[(i + ibge) % len(nomes)]} (demo)",
                    tipo=tipo,
                    frase=""
                    if tipo == PerfilGuia.Tipo.REGULAMENTADO
                    else f"Atendimento em {cidade.nome} e região.",
                    registro_profissional=f"CRO-MT {1000 + n}"
                    if tipo == PerfilGuia.Tipo.REGULAMENTADO
                    else "",
                    cnpj=_documento_demo(f"90{n:03d}0000001", cnpj_valido) if tipo == "empresa" else "",
                    cnpj_verificado_em=timezone.localdate() if tipo == "empresa" and n % 2 else None,
                    responsavel_nome=f"Responsável {n} (demo)",
                    responsavel_contato=f"responsavel{n}@demo.invalid",
                    whatsapp=f"+5565900{n:06d}",
                    telefone=f"+556530{n:06d}" if n % 3 == 0 else "",
                    cidade=cidade,
                    bairro=bairros[n % len(bairros)] if bairros and endereco else None,
                    atendimento=PerfilGuia.Atendimento.ENDERECO
                    if endereco
                    else PerfilGuia.Atendimento.DOMICILIO,
                    endereco=f"Rua Fictícia, {100 + n}" if endereco else "",
                    ponto=_ponto_demo(cidade, n) if endereco else None,
                    area_atendimento="" if endereco else f"{cidade.nome} e região",
                    horarios={} if sem_horario else horario,
                    status=PerfilGuia.Status.RASCUNHO,
                )
                if tipo == "autonomo":
                    definir_cpf(perfil, _documento_demo(f"900{n:06d}", cpf_valido))
                perfil.save()
                perfil.categorias.set([categorias[slug]] if slug in categorias else [])
                _publicar_demo(perfil, SITUACAO_DEMO.get(n, "publicado"), termo)
    _criar_operacao_demo(termo)
    return n


def _criar_operacao_demo(termo: TermoGuia | None) -> None:
    """G3: 6 pedidos do titular (2 vencidos, 2 no prazo, 2 atendidos, um deles removendo o perfil), 15
    contatos da lista de convites em situações variadas e 1 termo novo (demo) aceito só por metade dos
    publicados. Contatos de resposta sem e-mail: nada sai para a fila de e-mails."""
    from guia.models import ContatoConvite

    publicados = list(PerfilGuia.objects.filter(demo=True, status=PerfilGuia.Status.PUBLICADO).order_by("pk"))
    if len(publicados) < 8:
        return
    agora = timezone.now()
    Tipo, Status = PedidoDoPerfil.Tipo, PedidoDoPerfil.Status
    pedidos = [  # (perfil, tipo, dias atrás, situação final)
        (publicados[0], Tipo.ALTERAR, 20, Status.ABERTO),
        (publicados[1], Tipo.OUTRO, 18, Status.EM_ANDAMENTO),
        (publicados[2], Tipo.ALTERAR, 2, Status.ABERTO),
        (publicados[3], Tipo.REMOVER, 1, Status.ABERTO),
        (publicados[4], Tipo.ALTERAR, 30, Status.ATENDIDO),
        (publicados[5], Tipo.REMOVER, 10, "remover"),
    ]
    for i, (perfil, tipo, dias, situacao) in enumerate(pedidos, 1):
        pedido = PedidoDoPerfil.objects.create(
            demo=True,
            perfil=perfil,
            tipo=tipo,
            origem=PedidoDoPerfil.Origem.EMAIL if i % 3 == 0 else PedidoDoPerfil.Origem.FICHA,
            descricao=f"Pedido de demonstração {i}.",
            contato=f"WhatsApp (65) 90000-00{i:02d} (demo)",
            criado_em=agora - timedelta(days=dias),
        )
        if situacao == "remover":
            remover_perfil(perfil, None, "Remoção a pedido do titular (demonstração).", pedido=pedido)
        elif situacao in (Status.ATENDIDO, Status.EM_ANDAMENTO):
            responder_pedido(pedido, None, situacao, "Horário atualizado (demonstração).")

    cidades = list(Cidade.objects.filter(codigo_ibge__in=DISTRIBUICAO_DEMO).order_by("pk"))
    categorias = list(CategoriaServico.objects.filter(slug__in=CATEGORIAS_DEMO).order_by("pk"))
    S = ContatoConvite.Situacao
    situacoes = [S.NOVO] * 5 + [S.CONVIDADO] * 4 + [S.ACEITOU] * 2 + [S.RECUSOU] * 2 + [S.NAO_CONTATAR] * 2
    for i, situacao in enumerate(situacoes, 1):
        ContatoConvite.objects.create(
            demo=True,
            nome=f"Contato {i} (demo)",
            whatsapp=f"+5565910{i:06d}",
            cidade=cidades[i % len(cidades)],
            categoria=categorias[i % len(categorias)],
            situacao=situacao,
            convidado_em=agora - timedelta(days=i) if situacao != S.NOVO else None,
            perfil=publicados[6 + i % 2] if situacao == S.ACEITOU else None,
        )

    if termo is None:
        return
    novo = TermoGuia.objects.create(
        demo=True,
        versao=f"{termo.versao}-b (demo)",
        texto=termo.texto
        + "\n\n## 9. Novidade desta versão (demonstração)\nTexto fictício para testar o termo novo.",
        vigente_desde=max(termo.vigente_desde, timezone.localdate()),
    )
    for perfil in publicados[::2]:  # metade aceita a versão nova; a outra aparece em "quem falta aceitar"
        perfil.refresh_from_db()
        if perfil.status != PerfilGuia.Status.PUBLICADO:
            continue
        _, token = gerar_convite(perfil)
        aceitar_convite(token, perfil.responsavel_nome, "10.0.0.1", AGENTE_DEMO, avisar=False)
    assert termo_vigente() == novo


def _publicar_demo(perfil: PerfilGuia, situacao: str, termo: TermoGuia | None) -> None:
    """Leva o perfil demo à situação pedida pelo caminho de verdade (convite, aceite, pausa)."""
    if situacao == "rascunho" or termo is None:
        return
    _, token = gerar_convite(perfil)
    if situacao == "aguardando_aceite":
        return
    aceitar_convite(token, perfil.responsavel_nome, "10.0.0.1", AGENTE_DEMO, avisar=False)
    if situacao == "pausado":
        pausar(PerfilGuia.objects.get(pk=perfil.pk), "Pausado (demonstração).")


def _ponto_demo(cidade: Cidade, n: int):
    """Ponto fictício perto da sede da cidade (até ~1 km), fixo por perfil."""
    from django.contrib.gis.geos import Point

    if cidade.ponto is None:
        return None
    return Point(cidade.ponto.x + (n % 5 - 2) * 0.002, cidade.ponto.y + (n % 3 - 1) * 0.002, srid=4326)


def apagar_guia_demo() -> int:
    """Apaga perfis demo do guia com aceites, convites, pedidos, estatísticas, logos e histórico.

    Exceção à regra "nada é apagado": dados demo nunca vão para produção. Devolve quantos perfis saíram.
    """
    perfis = PerfilGuia.objects.filter(demo=True)
    ids = list(perfis.values_list("pk", flat=True))
    with transaction.atomic():
        for aceite in AceitePublicacao.objects.filter(perfil_id__in=ids).exclude(foto_termo=""):
            aceite.foto_termo.delete(save=False)
        for perfil in perfis.exclude(logo=""):
            perfil.logo.delete(save=False)
        PedidoDoPerfil.objects.filter(Q(demo=True) | Q(perfil_id__in=ids)).delete()
        PedidoDoPerfil.history.filter(Q(demo=True) | Q(perfil_id__in=ids)).delete()
        AceitePublicacao.objects.filter(perfil_id__in=ids).delete()
        AceitePublicacao.history.filter(perfil_id__in=ids).delete()
        ConviteAceite.objects.filter(perfil_id__in=ids).delete()
        from guia.models import ContatoConvite

        contatos = ContatoConvite.objects.filter(Q(demo=True) | Q(perfil_id__in=ids))
        ContatoConvite.history.filter(id__in=list(contatos.values_list("pk", flat=True))).delete()
        contatos.delete()
        total, _ = perfis.delete()
        PerfilGuia.history.filter(id__in=ids).delete()
        termos = TermoGuia.objects.filter(demo=True)
        AceitePublicacao.objects.filter(termo__in=termos).delete()  # só em dev: aceites do termo demo
        TermoGuia.history.filter(demo=True).delete()
        termos.delete()
    return len(ids) if total else 0
