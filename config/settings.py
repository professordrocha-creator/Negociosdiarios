"""Configurações do Django.

Um único arquivo para dev, CI e produção: tudo o que muda entre ambientes
(segredos, banco, DEBUG, hosts) vem de variáveis de ambiente (`.env`), nunca
fixo no código. Ver `.env.example` para a lista de variáveis.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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
