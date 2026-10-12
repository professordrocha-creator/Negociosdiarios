"""Regras do app anunciantes: cadastro, confirmação de e-mail, painel, aprovação/suspensão e demo."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.text import slugify

from anunciantes.models import Anunciante, SolicitacaoCidade
from anunciantes.validators import normalizar_cnpj, normalizar_creci, normalizar_whatsapp
from core import imagens
from core.models import Cidade
from core.services import (
    AnuncioVitrine,
    LojaVitrine,
    configuracao,
    enviar_email_modelo,
)

if TYPE_CHECKING:
    from contas.models import Usuario

logger = logging.getLogger(__name__)

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
    if not anunciante.cidade.liberada:
        raise ValueError(
            f"{anunciante.nome_publico}: a cidade {anunciante.cidade} ainda não é atendida. "
            "Libere a cidade (Solicitações de cidade) antes de aprovar."
        )
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
    """Anúncios da vitrine pública /loja/<slug>/: só os visíveis ao público, mais novos primeiro."""
    from anuncios.services import anuncios_visiveis, para_vitrine  # anuncios depende deste app

    return [
        para_vitrine(a) for a in anuncios_visiveis().filter(anunciante=anunciante).order_by("-publicado_em")
    ]


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
        anunciante, _ = Anunciante.objects.update_or_create(
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
        demo = {
            "sobre": f"{loja['nome']} é uma loja de demonstração do {configuracao().nome}. "
            "Os dados e anúncios desta página são fictícios.",
            "horario": "Seg a sex 8h–18h · Sáb 8h–12h",
            "endereco_publico": "Av. Brasil, 1.000 · Centro",
            "mostrar_no_mapa": True,
        }
        for campo, valor in demo.items():
            if not getattr(anunciante, campo):
                setattr(anunciante, campo, valor)
        anunciante.save(update_fields=[*demo, "atualizado_em"])
        gerar_imagens_demo(anunciante)
        if not cidade.liberada:  # como no cadastro real: cidade não atendida vira solicitação
            SolicitacaoCidade.objects.get_or_create(
                anunciante=anunciante,
                cidade=cidade,
                status=SolicitacaoCidade.Status.PENDENTE,
                defaults={"demo": True},
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
        if not dados.cidade.liberada:  # cidade ainda não atendida: vira pedido para o admin
            SolicitacaoCidade.objects.create(anunciante=anunciante, cidade=dados.cidade)
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
    return emails or [configuracao().email_contato]


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


# --- Solicitações de cidade (cadastro em cidade ainda não atendida) ----------------------


def liberar_cidade_da_solicitacao(solicitacao: SolicitacaoCidade, por: Usuario | None) -> int:
    """Libera a cidade pedida e dá como atendidas TODAS as solicitações pendentes dela.

    Devolve quantas solicitações foram atendidas. Se a solicitação for de demonstração,
    a cidade é marcada `liberada_pela_demo` (o `apagar_dados_demo` desfaz). O anunciante
    continua pendente: a aprovação da loja é outro passo (Aprovar, em Anunciantes).
    """
    from core.services import liberar_cidades

    cidade = solicitacao.cidade
    with transaction.atomic():
        liberar_cidades(Cidade.objects.filter(pk=cidade.pk))
        if solicitacao.demo:
            Cidade.objects.filter(pk=cidade.pk).update(liberada_pela_demo=True)
        return SolicitacaoCidade.objects.filter(
            cidade=cidade, status=SolicitacaoCidade.Status.PENDENTE
        ).update(
            status=SolicitacaoCidade.Status.LIBERADA,
            decidido_por=por,
            decidido_em=timezone.now(),
            motivo=f"Cidade liberada por {por or 'sistema'}.",
        )


def recusar_solicitacao(
    solicitacao: SolicitacaoCidade, por: Usuario | None, motivo: str
) -> SolicitacaoCidade:
    """Recusa o pedido (motivo obrigatório) e avisa o anunciante por e-mail com o motivo."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da recusa.")
    solicitacao.status = SolicitacaoCidade.Status.RECUSADA
    solicitacao.motivo = motivo.strip()
    solicitacao.decidido_por = por
    solicitacao.decidido_em = timezone.now()
    solicitacao.save(update_fields=["status", "motivo", "decidido_por", "decidido_em"])
    enviar_email_modelo(
        "cidade_recusada",
        "Ainda não atendemos a sua cidade",
        [solicitacao.anunciante.usuario.email],
        {
            "anunciante": solicitacao.anunciante,
            "cidade": solicitacao.cidade,
            "motivo": solicitacao.motivo,
            "link_contato": settings.SITE_URL + reverse("core:contato"),
        },
    )
    return solicitacao


# --- Página da loja: imagens, visibilidade e vitrine (Sprint 2) ---------------------------

# Tamanhos gerados (docs/TELAS.md §1): campo -> largura do WebP. Proporção: logo 1:1, capa 4:1.
TAMANHOS_IMAGEM = {
    "logo": {"proporcao": 1.0, "saidas": {"logo": 400, "logo_mini": 96}},
    "capa": {"proporcao": 4.0, "saidas": {"capa": 1600, "capa_media": 800}},
}


def processar_imagem_loja(anunciante: Anunciante, tipo: str) -> bool:
    """Gera os WebP do logo ou da capa a partir do envio, apaga o envio e as versões antigas.

    Roda no Celery (`anunciantes.tasks.processar_imagem_loja`). A foto é aberta na posição
    certa e sem EXIF (`core.imagens.abrir_limpa`), recortada pelo centro na proporção e
    reduzida (nunca ampliada). Devolve False se não havia envio ou se a imagem não abriu
    (nesse caso o envio é descartado e o log não leva dados pessoais).
    """
    regra = TAMANHOS_IMAGEM[tipo]
    original = getattr(anunciante, f"{tipo}_original")
    if not original:
        return False
    try:
        with original.open("rb") as arquivo:
            recortada = imagens.recortar_proporcao(imagens.abrir_limpa(arquivo), regra["proporcao"])
    except Exception:
        logger.exception(
            "Imagem da loja não pôde ser processada (anunciante id=%s, %s).", anunciante.pk, tipo
        )
        original.delete(save=False)
        anunciante.save(update_fields=[f"{tipo}_original"])
        return False
    for campo, largura in regra["saidas"].items():
        antigo = getattr(anunciante, campo)
        if antigo:
            antigo.delete(save=False)  # não deixa versões velhas ocupando o storage
        getattr(anunciante, campo).save(f"{campo}.webp", imagens.webp(recortada, largura, campo), save=False)
    original.delete(save=False)  # o original nunca é servido (docs/SEGURANCA.md)
    anunciante._change_reason = f"{tipo.capitalize()} da loja processado."
    anunciante.save(update_fields=[f"{tipo}_original", *regra["saidas"], "atualizado_em"])
    return True


def lojas_visiveis() -> QuerySet[Anunciante]:
    """Lojas que o público pode ver: ativas, em cidade liberada de estado liberado.

    Lojas de demonstração só com MOSTRAR_DEMO (nunca misturadas a lojas reais sem o aviso).
    Pendente, suspensa ou fora da área atendida não aparece em lugar nenhum (e a página dá 404).
    """
    lojas = Anunciante.objects.filter(
        status=Anunciante.Status.ATIVO, cidade__liberada=True, cidade__uf__liberado=True
    ).select_related("cidade", "cidade__uf")
    return lojas if settings.MOSTRAR_DEMO else lojas.filter(demo=False)


def total_anuncios(anunciante: Anunciante) -> int:
    """Anúncios da loja visíveis ao público agora."""
    from anuncios.services import anuncios_visiveis

    return anuncios_visiveis().filter(anunciante=anunciante).count()


def loja_para_vitrine(anunciante: Anunciante) -> LojaVitrine:
    """Converte o anunciante no formato usado pelo parcial _loja_mini.html."""
    return LojaVitrine(
        slug=anunciante.slug,
        nome=anunciante.nome_publico,
        tipo=anunciante.tipo,
        sigla=anunciante.iniciais,
        cor=anunciante.cor,
        cidade=anunciante.cidade.nome,
        total_anuncios=total_anuncios(anunciante),
        url=reverse("anunciantes:loja", args=[anunciante.slug]),
        logo=anunciante.logo_mini.url if anunciante.logo_mini else "",
    )


def lojas_verificadas(limite: int = 6) -> list[LojaVitrine]:
    """Vitrine de lojas da home: lojas visíveis, as com mais anúncios primeiro."""
    lojas = [loja_para_vitrine(a) for a in lojas_visiveis()]
    return sorted(lojas, key=lambda loja: (-loja.total_anuncios, loja.nome))[:limite]


def listar_lojas(tipo: str = "", cidade_id: str = "") -> QuerySet[Anunciante]:
    """Lojas de /lojas/ com os filtros opcionais por tipo e cidade (valores inválidos são ignorados)."""
    lojas = lojas_visiveis().order_by("nome_publico")
    if tipo in Anunciante.Tipo.values:
        lojas = lojas.filter(tipo=tipo)
    if str(cidade_id).isdigit():
        lojas = lojas.filter(cidade_id=int(cidade_id))
    return lojas


def cidades_com_lojas() -> QuerySet[Cidade]:
    """Cidades do filtro de /lojas/: só as que têm loja visível."""
    return Cidade.objects.filter(anunciantes__in=lojas_visiveis()).distinct().order_by("nome")


# Cores da paleta das lojas (as mesmas classes nd-cor-1..6 do nd.css), para as imagens demo.
CORES_DEMO = {
    1: (14, 74, 87),
    2: (155, 77, 52),
    3: (77, 122, 78),
    4: (91, 103, 121),
    5: (138, 106, 58),
    6: (47, 95, 105),
}


def gerar_imagens_demo(anunciante: Anunciante) -> None:
    """Logo (iniciais sobre a cor da loja) e capa (degradê) feitos com Pillow, sem baixar nada.

    Passam pelo MESMO processamento das imagens reais (WebP, tamanhos, sem EXIF), só que na
    hora, sem Celery, para o comando terminar com tudo pronto. Lojas que já têm logo ficam como estão.
    """
    if anunciante.logo:
        return
    from django.core.files.base import ContentFile
    from PIL import Image, ImageDraw, ImageFont

    cor = CORES_DEMO.get(anunciante.cor, CORES_DEMO[1])
    clara = tuple(min(255, c + 70) for c in cor)

    logo = Image.new("RGB", (512, 512), cor)
    desenho = ImageDraw.Draw(logo)
    fonte = ImageFont.load_default(size=220)
    desenho.text((256, 256), anunciante.iniciais, fill=(255, 255, 255), font=fonte, anchor="mm")
    desenho.ellipse((380, -60, 620, 180), fill=(242, 183, 5))  # toque amarelo-ipê da identidade

    capa = Image.new("RGB", (1600, 400), cor)
    desenho = ImageDraw.Draw(capa)
    for x in range(1600):  # degradê horizontal da cor da loja para um tom mais claro
        mistura = x / 1599
        desenho.line(
            [(x, 0), (x, 400)],
            fill=tuple(round(a + (b - a) * mistura) for a, b in zip(cor, clara, strict=True)),
        )
    desenho.ellipse((1250, -150, 1700, 300), fill=(242, 183, 5))

    for tipo, imagem in (("logo", logo), ("capa", capa)):
        saida = io.BytesIO()
        imagem.save(saida, format="PNG")
        getattr(anunciante, f"{tipo}_original").save(f"{tipo}.png", ContentFile(saida.getvalue()), save=True)
        processar_imagem_loja(anunciante, tipo)
