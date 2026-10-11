"""Regras do app contas."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from axes.utils import reset as axes_reset
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils.crypto import constant_time_compare, salted_hmac
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

if TYPE_CHECKING:
    # Só para tipagem: contas.models importa este módulo (normalizar_email), import real seria circular.
    from contas.models import Usuario

logger = logging.getLogger(__name__)

# Nomes dos dispositivos do django-otp (aparecem no admin do superusuário).
NOME_CODIGO_EMAIL = "Código por e-mail"
NOME_CODIGO_EMERGENCIA = "Código de emergência"

# Sessão: guarda o id de quem já passou pela verificação de navegador nesta sessão.
SESSAO_ACESSO_VERIFICADO = "nd_admin_verificado"
# Cookie do navegador confiável (só no caminho do admin) e o "sal" da assinatura dele.
COOKIE_NAVEGADOR_CONFIAVEL = "nd_admin_navegador"
SAL_NAVEGADOR_CONFIAVEL = "contas.navegador_confiavel"

ResultadoEnvio = Literal["enviado", "aguarde", "falhou"]


def normalizar_email(email: str) -> str:
    """Devolve o e-mail sem espaços nas pontas e todo em minúsculas.

    O e-mail é o login: guardar sempre normalizado evita duas contas para a
    mesma pessoa ("Joao@x.com" e "joao@x.com") e faz o login não depender de
    maiúsculas. A parte local é tratada sem distinção de caixa, como fazem
    na prática todos os provedores de e-mail.
    """
    return email.strip().lower()


def mascarar_email(email: str) -> str:
    """Mostra o e-mail sem revelar o endereço inteiro: "daniel@x.com" vira "d*****@x.com"."""
    local, _, dominio = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{dominio}"


def usuario_para_axes(request: HttpRequest, credentials: dict | None) -> str:
    """Diz ao django-axes qual é o "usuário" de uma tentativa de login: o e-mail normalizado.

    Sem isto, "Daniel@X.com" e "daniel@x.com" contariam como pessoas diferentes
    (dava para errar 5 vezes de cada jeito) e o `axes_reset_username` precisaria
    da caixa exata digitada no formulário.
    """
    bruto = (credentials or {}).get("username") or request.POST.get("username", "")
    return normalizar_email(bruto)


# --- Verificação de navegador novo no admin ---------------------------------------------


def codigo_admin_exigido() -> bool:
    """Diz se o admin pede código por e-mail para navegador novo.

    Só em produção (DEBUG desligado) e só com `ADMIN_CODIGO_EMAIL` ligado no .env.
    Em dev, ou até a etapa 6 configurar o envio de e-mail, basta e-mail e senha.
    """
    return settings.ADMIN_CODIGO_EMAIL and not settings.DEBUG


def acesso_verificado(request: HttpRequest) -> bool:
    """Diz se o usuário logado já pode usar o admin nesta sessão.

    Verdadeiro quando o código não é exigido, ou quando esta sessão já passou pela
    verificação (navegador confiável ou código certo). A marca na sessão guarda o id
    do usuário, então não serve para outra pessoa que entre no mesmo navegador.
    """
    if not codigo_admin_exigido():
        return True
    usuario = getattr(request, "user", None)
    return bool(
        usuario and usuario.is_authenticated and request.session.get(SESSAO_ACESSO_VERIFICADO) == usuario.pk
    )


def marcar_acesso_verificado(request: HttpRequest) -> None:
    """Registra na sessão que o usuário logado passou pela verificação de navegador."""
    request.session[SESSAO_ACESSO_VERIFICADO] = request.user.pk


def _marca_da_senha(usuario: Usuario) -> str:
    """Resumo do hash da senha atual: trocar a senha invalida todos os navegadores confiáveis."""
    return salted_hmac(SAL_NAVEGADOR_CONFIAVEL, usuario.password).hexdigest()[:24]


def gravar_navegador_confiavel(resposta: HttpResponse, usuario: Usuario) -> None:
    """Marca este navegador como confiável por `ADMIN_NAVEGADOR_CONFIAVEL_DIAS` dias.

    Cookie assinado com a SECRET_KEY (não dá para forjar nem trocar o usuário),
    HttpOnly (JavaScript não lê), Secure em produção (só HTTPS), SameSite=Lax e
    restrito ao caminho do admin (não vai junto nas páginas públicas). Fica
    inválido se a senha mudar ou se a SECRET_KEY for trocada.
    """
    valor = signing.dumps({"u": usuario.pk, "s": _marca_da_senha(usuario)}, salt=SAL_NAVEGADOR_CONFIAVEL)
    resposta.set_cookie(
        COOKIE_NAVEGADOR_CONFIAVEL,
        valor,
        max_age=int(timedelta(days=settings.ADMIN_NAVEGADOR_CONFIAVEL_DIAS).total_seconds()),
        path=f"/{settings.ADMIN_URL}",
        secure=not settings.DEBUG,
        httponly=True,
        samesite="Lax",
    )


def navegador_confiavel(request: HttpRequest, usuario: Usuario) -> bool:
    """Diz se o cookie deste navegador é válido para este usuário (assinatura, prazo e senha atual)."""
    valor = request.COOKIES.get(COOKIE_NAVEGADOR_CONFIAVEL)
    if not valor:
        return False
    try:
        dados = signing.loads(
            valor,
            salt=SAL_NAVEGADOR_CONFIAVEL,
            max_age=timedelta(days=settings.ADMIN_NAVEGADOR_CONFIAVEL_DIAS),
        )
    except signing.BadSignature:  # inclui o cookie vencido (SignatureExpired)
        return False
    return dados.get("u") == usuario.pk and constant_time_compare(
        dados.get("s", ""), _marca_da_senha(usuario)
    )


def enviar_codigo_email(usuario: Usuario) -> ResultadoEnvio:
    """Gera um código de 6 dígitos e envia para o e-mail do usuário.

    O código vale `ADMIN_CODIGO_MINUTOS` minutos e uma vez só; um código novo
    substitui o anterior. Entre um envio e outro há espera mínima de 60 s
    ("aguarde"), para ninguém lotar a caixa de e-mail apertando "reenviar".
    Se o envio falhar, devolve "falhou" (o log não leva o e-mail, LGPD); a saída
    de emergência é o `redefinir_acesso` no servidor (docs/RUNBOOK.md).
    """
    dispositivo, _ = EmailDevice.objects.get_or_create(user=usuario, name=NOME_CODIGO_EMAIL)
    permitido, _ = dispositivo.generate_is_allowed()
    if not permitido:
        return "aguarde"
    try:
        dispositivo.generate_challenge(extra_context={"minutos": settings.ADMIN_CODIGO_MINUTOS})
    except Exception:  # SMTP fora do ar, endereço recusado etc.: a tela avisa, o login não quebra.
        logger.exception("Falha ao enviar código de acesso ao admin (usuário id=%s).", usuario.pk)
        return "falhou"
    return "enviado"


def verificar_codigo(usuario: Usuario, codigo: str) -> bool:
    """Confere o código digitado na tela de verificação. Cada código vale uma vez só.

    6 dígitos = código enviado por e-mail; letras e números = código de emergência
    gerado no servidor. Depois de alguns erros seguidos o django-otp faz esperar
    (cada vez mais) antes de aceitar nova tentativa, mesmo que o código esteja certo.
    """
    codigo = codigo.strip().lower()
    if not codigo:
        return False
    modelo, nome = (
        (EmailDevice, NOME_CODIGO_EMAIL) if codigo.isdigit() else (StaticDevice, NOME_CODIGO_EMERGENCIA)
    )
    with transaction.atomic():
        # select_for_update: duas abas não conseguem usar o mesmo código ao mesmo tempo.
        dispositivo = modelo.objects.select_for_update().filter(user=usuario, name=nome).first()
        return dispositivo is not None and dispositivo.verify_token(codigo)


def redefinir_acesso(usuario: Usuario) -> str:
    """Emergência pelo servidor: desbloqueia o login e gera um código de emergência de uso único.

    Para quem ficou sem acesso ao e-mail ou foi bloqueado pelo axes. Só roda na
    linha de comando do servidor, nunca por tela: quem tem o servidor já tem tudo.
    O código substitui um código de emergência anterior e serve na tela de
    verificação no lugar do código por e-mail. Para invalidar os navegadores
    confiáveis (ex.: notebook roubado), troque a senha (`changepassword`).
    """
    with transaction.atomic():
        StaticDevice.objects.filter(user=usuario, name=NOME_CODIGO_EMERGENCIA).delete()
        dispositivo = StaticDevice.objects.create(user=usuario, name=NOME_CODIGO_EMERGENCIA, confirmed=True)
        codigo = StaticToken.random_token()
        StaticToken.objects.create(device=dispositivo, token=codigo)
    axes_reset(username=usuario.email)
    return codigo
