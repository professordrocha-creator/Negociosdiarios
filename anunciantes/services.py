"""Regras do app anunciantes: cadastro, confirmação de e-mail, painel, aprovação/suspensão e demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.text import slugify

from anunciantes.models import Anunciante
from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from core.models import Cidade
from core.services import AnuncioVitrine, PlanoVitrine, anuncios_demo_da_loja, enviar_email_modelo, planos

if TYPE_CHECKING:
    from contas.models import Usuario

# Mensagens mostradas no login e no painel para quem não pode entrar (dizem o que fazer).
MENSAGENS_SEM_ACESSO = {
    "equipe": "Esta é uma conta da equipe do site. Use o painel administrativo.",
    "sem_loja": "Esta conta não tem loja cadastrada. Para anunciar, veja os planos e fale com a gente.",
    "email_nao_confirmado": (
        "Falta confirmar o seu e-mail: abra o link que enviamos. Depois disso o cadastro vai para análise."
    ),
    Anunciante.Status.PENDENTE: "Seu cadastro está em análise. Avisaremos por e-mail quando for aprovado.",
    Anunciante.Status.SUSPENSO: "Sua loja está suspensa. Fale com a gente para entender o motivo.",
}


def motivo_sem_painel(usuario: AbstractBaseUser | AnonymousUser) -> str | None:
    """Diz por que o usuário NÃO pode usar o painel do anunciante, ou None se pode.

    Regras: equipe (staff) nunca usa o painel do cliente (tem o admin); é preciso ter
    loja (Anunciante) e ela estar `ativo`. Devolve a chave de MENSAGENS_SEM_ACESSO.
    """
    if not usuario.is_authenticated:
        return "anonimo"
    if usuario.is_staff:
        return "equipe"
    anunciante = Anunciante.objects.filter(usuario=usuario).first()
    if anunciante is None:
        return "sem_loja"
    if anunciante.status == Anunciante.Status.PENDENTE and not usuario.email_confirmado_em:
        return "email_nao_confirmado"
    if anunciante.status != Anunciante.Status.ATIVO:
        return anunciante.status
    return None


def _mudar_status(anunciante: Anunciante, status: str, por: Usuario | None, motivo: str) -> Anunciante:
    """Troca o status, guarda o motivo e registra no histórico quem mudou e por quê."""
    anunciante.status = status
    anunciante.motivo_status = motivo
    anunciante._history_user = por  # simple_history: autor da mudança
    anunciante._change_reason = motivo[:100]  # aparece na lista de histórico do admin
    anunciante.save(update_fields=["status", "motivo_status", "atualizado_em"])
    return anunciante


def aprovar(anunciante: Anunciante, por: Usuario | None, motivo: str = "") -> Anunciante:
    """Aprova o anunciante (CRECI/CNPJ conferido) e avisa por e-mail, com o link para entrar.

    Só aprova quem já confirmou o e-mail (antes disso o cadastro nem aparece para aprovação).
    """
    if not anunciante.usuario.email_confirmado_em:
        raise ValueError(f"{anunciante.nome_publico}: o e-mail ainda não foi confirmado.")
    _mudar_status(anunciante, Anunciante.Status.ATIVO, por, motivo.strip() or "Documento conferido.")
    enviar_email_modelo(
        "loja_aprovada",
        "Sua loja foi aprovada",
        [anunciante.usuario.email],
        {"anunciante": anunciante, "link_entrar": settings.SITE_URL + reverse("contas:entrar")},
    )
    return anunciante


def suspender(anunciante: Anunciante, por: Usuario | None, motivo: str) -> Anunciante:
    """Suspende o anunciante e avisa por e-mail com o motivo (obrigatório; fica no histórico)."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da suspensão.")
    _mudar_status(anunciante, Anunciante.Status.SUSPENSO, por, motivo.strip())
    enviar_email_modelo(
        "loja_suspensa",
        "Sua loja foi suspensa",
        [anunciante.usuario.email],
        {
            "anunciante": anunciante,
            "motivo": motivo.strip(),
            "link_contato": settings.SITE_URL + reverse("core:contato"),
        },
    )
    return anunciante


def anuncios_da_loja(anunciante: Anunciante) -> list[AnuncioVitrine]:
    """Anúncios do anunciante para o painel.

    Por enquanto só lojas de demonstração têm anúncios (do demo.json, pelo slug da
    loja). A checagem `demo` impede que uma loja real com o mesmo endereço veja
    anúncios fictícios. Na Sprint 3 passa a ler do banco, sempre filtrando pelo dono.
    """
    return anuncios_demo_da_loja(anunciante.slug) if anunciante.demo else []


def plano_de_exemplo() -> PlanoVitrine:
    """Plano mostrado no resumo do painel até existir assinatura (Sprint 2): o Profissional."""
    lista = planos()
    return next((p for p in lista if p.slug == "profissional"), lista[0])


# --- Dados de demonstração (chamados pelo core.services.criar/apagar_dados_demo) ---------


def criar_anunciantes_demo(lojas: list[dict], senha: str) -> int:
    """Cria (ou atualiza) as lojas do demo.json, cada uma com login próprio. Idempotente.

    Cada loja vira um Usuario (e-mail da loja, já confirmado; senha = DEMO_SENHA; nunca
    equipe) e um Anunciante com o `status` do JSON (padrão `ativo`), ambos com `demo=True`.
    Recusa se e-mail, endereço da loja ou documento já pertencerem a dados reais (nunca
    sobrescreve conta de verdade).
    Chame dentro de uma transação; as cidades das lojas já devem estar liberadas.
    """
    Usuario = get_user_model()
    emails = [loja["email"] for loja in lojas]
    conflitos = list(Usuario.objects.filter(email__in=emails, demo=False).values_list("email", flat=True))
    conflitos += list(
        Anunciante.objects.filter(slug__in=[loja["slug"] for loja in lojas], demo=False).values_list(
            "slug", flat=True
        )
    )
    if conflitos:
        raise ValueError(f"Dados de demonstração colidem com dados reais: {', '.join(conflitos)}.")

    cidades = {
        c.codigo_ibge: c
        for c in Cidade.objects.filter(codigo_ibge__in={loja["cidade_ibge"] for loja in lojas})
    }
    for loja in lojas:
        usuario, _ = Usuario.objects.get_or_create(
            email=loja["email"], defaults={"nome": loja["responsavel"]}
        )
        usuario.nome = loja["responsavel"]
        usuario.demo = True
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.is_active = True
        usuario.email_confirmado_em = usuario.email_confirmado_em or timezone.now()
        usuario.set_password(senha)
        usuario.save()

        cidade = cidades[loja["cidade_ibge"]]
        if loja["tipo"] == Anunciante.Tipo.CORRETOR_AUTONOMO:
            documento = (Anunciante.DocumentoTipo.CRECI, normalizar_creci(loja["creci"], cidade.uf_id))
        else:
            documento = (Anunciante.DocumentoTipo.CNPJ, normalizar_cnpj(loja["cnpj"]))
        Anunciante.objects.update_or_create(
            slug=loja["slug"],
            defaults={
                "usuario": usuario,
                "tipo": loja["tipo"],
                "nome_publico": loja["nome"],
                "sigla": loja["sigla"],
                "cor": loja["cor"],
                "documento_tipo": documento[0],
                "documento_numero": documento[1],
                "whatsapp": normalizar_whatsapp(loja["whatsapp"]),
                "email_publico": loja["email"],
                "cidade": cidade,
                "status": loja.get("status", Anunciante.Status.ATIVO),
                "motivo_status": "Loja de demonstração.",
                "demo": True,
            },
        )
    return len(lojas)


def apagar_anunciantes_demo() -> int:
    """Apaga os anunciantes de demonstração e o histórico deles. Devolve quantos eram.

    Os usuários (logins) demo são apagados depois, pelo core, com os demais `demo=True`.
    """
    with transaction.atomic():
        quantos = Anunciante.objects.filter(demo=True).count()
        Anunciante.objects.filter(demo=True).delete()
        Anunciante.history.filter(demo=True).delete()
    return quantos


# --- Cadastro público e confirmação de e-mail --------------------------------------------

SAL_CONFIRMACAO = "anunciantes.confirmar_email"


@dataclass(frozen=True)
class DadosCadastro:
    """Dados já validados pelo formulário de /cadastro/ (documento e WhatsApp normalizados)."""

    nome: str
    email: str
    senha: str
    tipo: str
    nome_publico: str
    documento_tipo: str
    documento_numero: str
    whatsapp: str
    cidade: Cidade


def slug_livre(nome_publico: str) -> str:
    """Endereço da loja a partir do nome, sem repetir: "loja-x", "loja-x-2", "loja-x-3"..."""
    base = slugify(nome_publico)[:70] or "loja"
    slug, n = base, 1
    while Anunciante.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def cadastrar_anunciante(dados: DadosCadastro) -> Anunciante:
    """Cria a conta, a loja (pendente) e os aceites dos documentos; depois envia os e-mails.

    Tudo numa transação: com erro, nada fica pela metade. Os e-mails ("confirme seu
    e-mail" e "recebemos seu cadastro") só saem depois que o banco gravou. A equipe só
    é avisada quando o e-mail for confirmado (`confirmar_email`).
    """
    from contas.models import AceiteDocumento

    Usuario = get_user_model()
    with transaction.atomic():
        usuario = Usuario.objects.create_user(email=dados.email, password=dados.senha, nome=dados.nome)
        anunciante = Anunciante(
            usuario=usuario,
            tipo=dados.tipo,
            nome_publico=dados.nome_publico,
            slug=slug_livre(dados.nome_publico),
            documento_tipo=dados.documento_tipo,
            documento_numero=dados.documento_numero,
            whatsapp=dados.whatsapp,
            email_publico=usuario.email,
            cidade=dados.cidade,
            status=Anunciante.Status.PENDENTE,
            motivo_status="Cadastro pelo site.",
        )
        anunciante.full_clean()
        anunciante._change_reason = "Cadastro pelo site."
        anunciante.save()
        AceiteDocumento.objects.bulk_create(
            [
                AceiteDocumento(usuario=usuario, documento="termos", versao=settings.VERSAO_TERMOS),
                AceiteDocumento(usuario=usuario, documento="privacidade", versao=settings.VERSAO_PRIVACIDADE),
            ]
        )
    enviar_confirmacao(usuario)
    enviar_email_modelo(
        "cadastro_recebido", "Recebemos seu cadastro", [usuario.email], {"anunciante": anunciante}
    )
    return anunciante


def _marca_confirmacao(usuario: Usuario) -> str:
    """Resumo de e-mail + situação da confirmação: muda ao confirmar (link vira de uso único)."""
    return salted_hmac(SAL_CONFIRMACAO, f"{usuario.email}|{usuario.email_confirmado_em}").hexdigest()[:24]


def link_confirmacao(usuario: Usuario) -> str:
    """Link absoluto de confirmação, assinado e com validade (CONFIRMACAO_EMAIL_HORAS)."""
    token = signing.dumps({"u": usuario.pk, "m": _marca_confirmacao(usuario)}, salt=SAL_CONFIRMACAO)
    return settings.SITE_URL + reverse("anunciantes:confirmar_email", args=[token])


def enviar_confirmacao(usuario: Usuario) -> None:
    """Envia o e-mail "confirme seu e-mail" com um link novo."""
    enviar_email_modelo(
        "confirmar_email",
        "Confirme seu e-mail",
        [usuario.email],
        {
            "nome": usuario.get_short_name(),
            "link": link_confirmacao(usuario),
            "horas": settings.CONFIRMACAO_EMAIL_HORAS,
        },
    )


def destinatarios_equipe() -> list[str]:
    """Quem recebe "novo cadastro aguardando aprovação": superusuários e o grupo Moderador.

    Sem ninguém (banco novo), vai para o e-mail de contato do site.
    """
    Usuario = get_user_model()
    emails = list(
        Usuario.objects.filter(is_active=True, is_staff=True)
        .filter(Q(is_superuser=True) | Q(groups__name="Moderador"))
        .values_list("email", flat=True)
        .distinct()
    )
    return emails or [settings.SITE_EMAIL_CONTATO]


@dataclass(frozen=True)
class ResultadoConfirmacao:
    """Resultado do clique no link: "confirmado", "ja_confirmado", "vencido" ou "invalido"."""

    situacao: str
    usuario: Usuario | None = None


def confirmar_email(token: str) -> ResultadoConfirmacao:
    """Confere o link de confirmação e, se válido, confirma o e-mail e avisa a equipe.

    Uso único: depois de confirmado, o mesmo link responde "ja_confirmado" e não faz
    mais nada. Vencido (48 h) ou adulterado não confirma.
    """
    try:
        dados = signing.loads(
            token, salt=SAL_CONFIRMACAO, max_age=timedelta(hours=settings.CONFIRMACAO_EMAIL_HORAS)
        )
        vencido = False
    except signing.SignatureExpired:
        dados = signing.loads(token, salt=SAL_CONFIRMACAO)  # assinatura ok, só o prazo passou
        vencido = True
    except signing.BadSignature:
        return ResultadoConfirmacao("invalido")

    usuario = get_user_model().objects.filter(pk=dados.get("u")).first()
    if usuario is None:
        return ResultadoConfirmacao("invalido")
    if usuario.email_confirmado_em:
        return ResultadoConfirmacao("ja_confirmado", usuario)
    if vencido:
        return ResultadoConfirmacao("vencido", usuario)
    if not constant_time_compare(dados.get("m", ""), _marca_confirmacao(usuario)):
        return ResultadoConfirmacao("invalido")

    usuario.email_confirmado_em = timezone.now()
    usuario.save(update_fields=["email_confirmado_em"])
    anunciante = Anunciante.objects.filter(usuario=usuario).first()
    if anunciante and anunciante.status == Anunciante.Status.PENDENTE:
        enviar_email_modelo(
            "novo_cadastro_equipe",
            "Novo cadastro aguardando aprovação",
            destinatarios_equipe(),
            {
                "anunciante": anunciante,
                "link_admin": settings.SITE_URL
                + reverse("admin:anunciantes_anunciante_change", args=[anunciante.pk]),
            },
        )
    return ResultadoConfirmacao("confirmado", usuario)


def reenviar_confirmacao(email: str) -> None:
    """Manda um link novo para quem ainda não confirmou. Silencioso nos outros casos.

    A resposta na tela é sempre a mesma, para não revelar quais e-mails têm conta.
    """
    from contas.services import normalizar_email

    usuario = (
        get_user_model()
        .objects.filter(
            email=normalizar_email(email), is_active=True, is_staff=False, email_confirmado_em__isnull=True
        )
        .first()
    )
    if usuario:
        enviar_confirmacao(usuario)
