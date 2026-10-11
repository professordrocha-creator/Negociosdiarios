"""Configurações do Django.

Um único arquivo para dev, CI e produção: tudo o que muda entre ambientes
(segredos, banco, DEBUG, hosts) vem de variáveis de ambiente (`.env`), nunca
fixo no código. Ver `.env.example` para a lista de variáveis.
"""

import re
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
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


def validar_mostrar_demo(mostrar: bool, debug: bool) -> bool:
    """Garante que a home só mostre dados de demonstração em dev.

    MOSTRAR_DEMO=True com DEBUG=False derruba a subida: dados fictícios nunca podem
    aparecer em produção (regra "Dados de demonstração" do CLAUDE.md).
    """
    if mostrar and not debug:
        raise ImproperlyConfigured(
            "MOSTRAR_DEMO=True é proibido com DEBUG=False (dados fictícios em produção)."
        )
    return mostrar


def armazenamento_de_midia(tipo: str, env: environ.Env, base_dir: Path) -> tuple[dict, str, Path]:
    """Monta STORAGES, MEDIA_URL e MEDIA_ROOT conforme ARMAZENAMENTO (docs/adr/0002).

    - "local": arquivos na pasta media/ do projeto (dev). Servidos pelo Django só com DEBUG.
    - "s3": bucket S3 compatível (produção: Cloudflare R2) via django-storages. Com
      S3_DOMINIO_PUBLICO (ex.: midia.negociosdiarios.com.br), as URLs são públicas e
      cacheáveis; sem ele, saem assinadas e temporárias.
    Qualquer outro valor derruba a subida, para um erro de digitação não gravar fotos no lugar errado.
    """
    estaticos = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    media_root = base_dir / "media"
    if tipo == "local":
        midia = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        return {"default": midia, "staticfiles": estaticos}, "/media/", media_root
    if tipo == "s3":
        dominio = env("S3_DOMINIO_PUBLICO", default="")
        opcoes = {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL"),
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "region_name": env("S3_REGIAO", default="auto"),  # o R2 usa "auto"
            "signature_version": "s3v4",
            "default_acl": None,  # o R2 não usa ACL; a visibilidade é do bucket/domínio
            "file_overwrite": False,  # nome repetido ganha sufixo, nunca apaga foto de outro anúncio
            "custom_domain": dominio or None,
            "querystring_auth": not dominio,
            "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"},
        }
        midia = {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": opcoes}
        media_url = f"https://{dominio}/" if dominio else "/media/"
        return {"default": midia, "staticfiles": estaticos}, media_url, media_root
    raise ImproperlyConfigured(f"ARMAZENAMENTO inválido: {tipo!r}. Use 'local' (dev) ou 's3' (produção).")


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
    "django.contrib.sitemaps",  # /sitemap.xml (config/sitemaps.py)
    "django_otp",  # base dos códigos de verificação do admin
    "django_otp.plugins.otp_email",  # código de 6 dígitos por e-mail (navegador novo, em produção)
    "django_otp.plugins.otp_static",  # código de emergência gerado no servidor (docs/RUNBOOK.md)
    "axes",  # bloqueio após tentativas de login erradas
    "simple_history",  # histórico de alterações (quem mudou o quê e quando)
    "core",
    "contas",
    "anunciantes",
    "planos",
    "anuncios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",  # grava quem fez cada mudança no histórico
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

# Login do cliente (anunciante) em /entrar/; a equipe usa o login do admin.
LOGIN_URL = "contas:entrar"
LOGIN_REDIRECT_URL = "anunciantes:painel"
LOGOUT_REDIRECT_URL = "core:inicio"

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
# Só VALORES INICIAIS: na primeira leitura viram o registro core.Configuracao, e dali em diante
# o site lê do admin ("Identidade do site"). Mudar aqui depois não muda o site.
SITE_NOME = "Negócios Diários"
SITE_SLOGAN = "Os melhores negócios da sua região, todos os dias."
SITE_LINHA_REGIAO = "Imóveis e veículos de Mato Grosso"
SITE_EMAIL_CONTATO = "contato@negociosdiarios.com.br"
SITE_EMAIL_PRIVACIDADE = "privacidade@negociosdiarios.com.br"
SITE_EMPRESA = "D'Rocha Soluções"
SITE_CIDADE_SEDE = "Tangará da Serra, MT"
# Endereço público do site, usado nos links dos e-mails (confirmação, aprovação, senha).
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")

# Versões dos documentos legais aceitos no cadastro (gravadas em contas.AceiteDocumento).
# Mudou o texto de /termos/ ou /privacidade/? Suba a versão: novos aceites registram a nova.
VERSAO_TERMOS = "2026-10-rascunho"
VERSAO_PRIVACIDADE = "2026-10-rascunho"

# Cadastro e recuperação de senha. Provisório: na Sprint 2 os limites vão para Configuracao.
CONFIRMACAO_EMAIL_HORAS = 48  # validade do link "confirme seu e-mail"
PASSWORD_RESET_TIMEOUT = 2 * 60 * 60  # link "esqueci minha senha" vale 2 horas (e uma vez só)
LIMITE_CADASTROS_POR_HORA = 5  # por IP: cadastros enviados
LIMITE_PEDIDOS_EMAIL_POR_HORA = 5  # por IP: "esqueci minha senha" e "reenviar confirmação"

# Contatos públicos (página /contato/ e documentos legais). Vazios = a página mostra "em breve"
# ou "a informar", nunca um dado inventado. WhatsApp em E.164 (ex.: +5565999999999).
SITE_WHATSAPP = env("SITE_WHATSAPP", default="")
SITE_ENDERECO = env("SITE_ENDERECO", default="")
SITE_CNPJ = env("SITE_CNPJ", default="")  # só dígitos

# Espaços de publicidade (mídia kit /anuncie/, docs/PUBLICIDADE.md). Provisório: na Sprint 7
# viram registros do app publicidade, editáveis no admin.
PUBLICIDADE_FORMATOS = [
    {
        "slug": "banner-topo",
        "nome": "Banner topo",
        "onde": "Todas as páginas, logo abaixo do cabeçalho",
        "tamanho": "970×90 no computador e 320×100 no celular (as duas imagens)",
        "arquivo": "JPG, PNG ou WebP, sem animação, até 1 MB cada",
        "preco_de": "299.00",
        "preco_ate": "599.00",
        "periodo": "mês",
    },
    {
        "slug": "card-patrocinador",
        "nome": "Card patrocinador",
        "onde": "Rodapé da página inicial (3 vagas)",
        "tamanho": "Logo quadrada 400×400 + frase de até 80 caracteres + link",
        "arquivo": "Logo em JPG, PNG ou WebP, até 1 MB",
        "preco_de": "149.00",
        "preco_ate": "299.00",
        "periodo": "mês",
    },
    {
        "slug": "anuncio-nativo",
        "nome": "Anúncio nativo",
        "onde": "Topo dos resultados de busca, por cidade",
        "tamanho": "Título de até 60 e texto de até 120 caracteres + link",
        "arquivo": "Só texto",
        "preco_de": "49.90",
        "preco_ate": "",
        "periodo": "semana",
    },
]

# --- Dados de demonstração (só em dev; regra no CLAUDE.md) --------------------------------
# MOSTRAR_DEMO: a home mostra lojas e anúncios fictícios de core/dados/demo.json (até a
# Sprint 3, quando passam a vir do banco). Proibido com DEBUG=False.
MOSTRAR_DEMO = validar_mostrar_demo(env.bool("MOSTRAR_DEMO", default=False), DEBUG)
# Senha de todos os usuários criados pelo criar_dados_demo (sem padrão: nada de senha conhecida).
DEMO_SENHA = env("DEMO_SENHA", default="")

# --- Admin: endereço secreto, código de navegador novo e bloqueio --------------------------
# (docs/SEGURANCA.md, docs/RUNBOOK.md)
# Sem valor padrão: um padrão no código seria um endereço conhecido. /admin/ não existe (404).
# O endereço secreto só tira o admin da mira de robôs; a proteção é a senha + código + axes.
ADMIN_URL = normalizar_admin_url(env("ADMIN_URL"))

# Código por e-mail para navegador novo. Ligado por padrão em todos os ambientes (em dev o
# e-mail cai no Mailpit, http://localhost:8025). Para desligar em dev: ADMIN_CODIGO_EMAIL=False
# no .env. Em produção NUNCA desligar (docs/SEGURANCA.md).
ADMIN_CODIGO_EMAIL = env.bool("ADMIN_CODIGO_EMAIL", default=True)
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

# --- Arquivos estáticos e mídia -----------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Mídia (fotos de anúncios, logos): ARMAZENAMENTO=local (dev, pasta media/) ou s3 (produção,
# Cloudflare R2 ou outro S3 compatível). Decisão em docs/adr/0002-armazenamento-midia.md.
ARMAZENAMENTO = env("ARMAZENAMENTO", default="local")
STORAGES, MEDIA_URL, MEDIA_ROOT = armazenamento_de_midia(ARMAZENAMENTO, env, BASE_DIR)

# --- Cache ---------------------------------------------------------------------
# No Redis (e não na memória de cada processo): os limites por IP precisam valer para
# todos os processos do Gunicorn ao mesmo tempo. Prefixo para não misturar com o Celery.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "KEY_PREFIX": "nd",
    }
}

# --- Celery (tarefas assíncronas e agendadas) ---------------------------------
# Fila e resultados no Redis. Tarefas de exemplo e de e-mail em core/tasks.py.
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_RESULT_EXPIRES = 60 * 60  # resultados só servem para conferência; somem em 1 hora
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 5 * 60  # nenhuma tarefa trava o worker por mais de 5 minutos
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Se o Redis cair, a página desiste de enfileirar em ~2 s em vez de ficar presa.
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}
CELERY_BEAT_SCHEDULE = {
    # Exemplo: prova que o agendador está vivo (aparece no log do worker a cada 5 minutos).
    "batimento": {"task": "core.tasks.batimento", "schedule": 5 * 60},
    # Todo dia às 6h (Cuiabá): vencidas além da carência viram "em atraso" (anúncios pausados).
    "atrasos": {"task": "planos.tasks.verificar_atrasos", "schedule": crontab(hour=6, minute=0)},
    "expiracao": {"task": "anuncios.tasks.expirar_anuncios", "schedule": crontab(hour=3, minute=0)},
}

# --- E-mail --------------------------------------------------------------------
# Todo e-mail vai para a fila do Celery (core.email.CeleryEmailBackend) e o worker envia
# com o backend real: SMTP. Em dev, o SMTP é o Mailpit (http://localhost:8025); em produção,
# o provedor (Brevo, Amazon SES...) pelas variáveis abaixo. Nunca envia dentro da página.
EMAIL_BACKEND = "core.email.CeleryEmailBackend"
EMAIL_BACKEND_REAL = env("EMAIL_BACKEND_REAL", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)  # STARTTLS na porta 587 (Brevo, SES)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)  # TLS direto na porta 465
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"{SITE_NOME} <nao-responda@negociosdiarios.com.br>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

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
