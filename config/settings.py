"""Configurações do Django.

Um único arquivo para dev, CI e produção: tudo o que muda entre ambientes
(segredos, banco, DEBUG, hosts) vem de variáveis de ambiente (`.env`), nunca
fixo no código. Ver `.env.example` para a lista de variáveis.
"""

import re
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def normalizar_admin_url(valor: str) -> str:
    """Devolve o caminho do admin no formato do `path()` ("painel-x/"), recusando valores óbvios.

    O caminho vem do .env (ADMIN_URL). Aceita com ou sem barras nas pontas.
    Recusa vazio e "admin" (o primeiro endereço que robôs testam) e caracteres fora
    de letras, números, "-" e "_", para o valor não virar padrão de URL por engano.
    """
    caminho = valor.strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*", caminho):
        raise ImproperlyConfigured(
            "ADMIN_URL inválido: use só letras, números, '-' e '_' (ex.: painel-abc123)."
        )
    if caminho.lower() == "admin":
        raise ImproperlyConfigured("ADMIN_URL não pode ser 'admin': escolha um caminho difícil de adivinhar.")
    return caminho + "/"


env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
)
# Em dev o Docker Compose já injeta o .env; ler o arquivo aqui cobre quem roda fora do Docker.
environ.Env.read_env(BASE_DIR / ".env")

# --- Núcleo -------------------------------------------------------------------
# Sem valor padrão de propósito: subir sem SECRET_KEY deve falhar, nunca usar uma chave conhecida.
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "config.apps.AdminConfigND",  # admin com verificação de navegador novo (config/admin_site.py)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # GeoDjango: campos geográficos (PostGIS)
    "django_otp",  # base dos códigos de verificação do admin
    "django_otp.plugins.otp_email",  # código de 6 dígitos por e-mail (navegador novo, em produção)
    "django_otp.plugins.otp_static",  # código de emergência gerado no servidor (docs/RUNBOOK.md)
    "axes",  # bloqueio após tentativas de login erradas
    "core",
    "contas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",  # o último: devolve a página de bloqueio
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

# --- Banco de dados -----------------------------------------------------------
# DATABASE_URL no formato postgis://usuario:senha@host:5432/banco (engine PostGIS desde a V1).
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Usuários e senhas --------------------------------------------------------
# Usuário próprio com login por e-mail. Definido antes do primeiro migrate: trocar depois é muito caro.
AUTH_USER_MODEL = "contas.Usuario"

# O backend do axes vem primeiro: recusa o login de quem está bloqueado antes de conferir a senha.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Argon2 é o padrão para novas senhas; os demais só verificam hashes antigos, se existirem.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Idioma e fuso ------------------------------------------------------------
# MT é UTC−4 (uma hora a menos que Brasília). Datas são gravadas em UTC e exibidas em Cuiabá.
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Cuiaba"
USE_I18N = True
USE_TZ = True

# --- Identidade do site ------------------------------------------------------
# Provisório: na Sprint 1 estes textos passam para o modelo Configuracao (editável no admin).
# Usados pelo context processor core.context_processors.site.
SITE_NOME = "Negócios Diários"
SITE_SLOGAN = "Os melhores negócios da sua região, todos os dias."
SITE_LINHA_REGIAO = "Imóveis e veículos de Mato Grosso"
SITE_EMAIL_CONTATO = "contato@negociosdiarios.com.br"
SITE_EMAIL_PRIVACIDADE = "privacidade@negociosdiarios.com.br"
SITE_EMPRESA = "D'Rocha Soluções"
SITE_CIDADE_SEDE = "Tangará da Serra, MT"

# --- Admin: endereço secreto, código de navegador novo e bloqueio --------------------------
# (docs/SEGURANCA.md, docs/RUNBOOK.md)
# Sem valor padrão: um padrão no código seria um endereço conhecido. /admin/ não existe (404).
# O endereço secreto só tira o admin da mira de robôs; a proteção é a senha + código + axes.
ADMIN_URL = normalizar_admin_url(env("ADMIN_URL"))

# Código por e-mail para navegador novo. Só vale em produção (nunca com DEBUG ligado) e só se
# ligado no .env. Fica DESLIGADO até a etapa 6 configurar o envio de e-mail: até lá o admin
# pede só e-mail e senha também em produção (risco aceito, docs/SEGURANCA.md).
ADMIN_CODIGO_EMAIL = env.bool("ADMIN_CODIGO_EMAIL", default=False)
ADMIN_CODIGO_MINUTOS = 10  # validade do código enviado por e-mail
ADMIN_NAVEGADOR_CONFIAVEL_DIAS = 30  # depois do código certo, o navegador não pede código por 30 dias

# Código por e-mail (plugin otp_email do django-otp): 6 dígitos, uso único, espera progressiva
# entre tentativas erradas e no mínimo 60 s entre um envio e outro.
OTP_EMAIL_TOKEN_VALIDITY = ADMIN_CODIGO_MINUTOS * 60
OTP_EMAIL_SUBJECT = f"Seu código de acesso ao {SITE_NOME}"
OTP_EMAIL_BODY_TEMPLATE_PATH = "contas/email_codigo_admin.txt"

# Bloqueio de tentativas (django-axes).
AXES_FAILURE_LIMIT = 5  # na 5ª senha errada a conta é bloqueada
AXES_COOLOFF_TIME = timedelta(hours=1)  # desbloqueia sozinho depois de 1 hora (ou com axes_reset_username)
# Bloqueia a combinação e-mail + IP: um atacante em outro IP não consegue trancar o Daniel do lado de fora.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_CALLABLE = "contas.services.usuario_para_axes"  # e-mail em minúsculas, como no login
AXES_RESET_ON_SUCCESS = True  # login certo zera os erros anteriores
# Não guardar IP e navegador de cada login bem-sucedido (LGPD: só o necessário). O last_login basta.
AXES_DISABLE_ACCESS_LOG = True
AXES_LOCKOUT_TEMPLATE = "contas/bloqueado.html"
# O IP vem só do REMOTE_ADDR (cabeçalho X-Forwarded-For pode ser forjado). Na etapa 8, atrás do
# Nginx, passar a ler o X-Forwarded-For com AXES_IPWARE_PROXY_COUNT = 1.
AXES_IPWARE_META_PRECEDENCE_ORDER = ["REMOTE_ADDR"]

# --- Arquivos estáticos -------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# --- Cabeçalhos de segurança (valem em todos os ambientes) --------------------
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 semanas

if not DEBUG:
    # Produção fica atrás do Nginx com TLS; o Nginx informa o protocolo original.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # /saude/ é chamado por HTTP interno (healthcheck do Docker); não redirecionar.
    SECURE_REDIRECT_EXEMPT = [r"^saude/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Começa com 1 dia; subir para 1 ano depois do lançamento estável (docs/SEGURANCA.md).
    SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24)
