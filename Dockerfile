# Imagem da aplicação (web e worker). Mesma imagem em dev e produção;
# em dev o docker-compose.yml liga INSTALAR_DEV para trazer pytest e ruff.
FROM python:3.12.12-slim-bookworm

# uv com versão fixa, copiado da imagem oficial (sem curl | sh).
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

# GDAL/GEOS/PROJ: bibliotecas nativas exigidas pelo GeoDjango (engine PostGIS).
# libcairo2: usada pelo cairosvg para gerar o favicon PNG a partir do símbolo SVG do site.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Virtualenv fora de /app: em dev o código é montado em /app e não pode escondê-lo.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG INSTALAR_DEV=false
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALAR_DEV" = "true" ]; then \
        uv sync --locked --no-install-project; \
    else \
        uv sync --locked --no-install-project --no-dev; \
    fi

COPY . .

# Usuário sem privilégios (docs/SEGURANCA.md §3). O venv fica do root: o app não altera pacotes.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
