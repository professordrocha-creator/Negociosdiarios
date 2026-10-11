# Negócios Diários

> "Os melhores negócios da sua região, todos os dias."

Plataforma de classificados regionais de **imóveis e veículos** para Mato Grosso.
Anunciantes profissionais verificados (corretores com CRECI, imobiliárias,
revendas com CNPJ) assinam um plano e ganham uma **vitrine própria**
(`negociosdiarios.com.br/loja/<nome-da-loja>`). Visitantes pesquisam sem
cadastro e falam com o anunciante pelo WhatsApp.

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Regras de código para o Claude Code (leia antes de programar) |
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | Visão técnica, apps Django, modelo de dados, containers |
| [`docs/SEGURANCA.md`](docs/SEGURANCA.md) | Checklist de segurança da aplicação e do servidor |
| [`docs/LGPD.md`](docs/LGPD.md) | Mapeamento de dados, bases legais, direitos do titular |
| [`docs/PAGAMENTOS.md`](docs/PAGAMENTOS.md) | Mercado Pago, assinaturas, Pix, webhooks, fiscal |
| [`docs/PUBLICIDADE.md`](docs/PUBLICIDADE.md) | Banners vendidos direto: vagas, regras, métricas |
| [`docs/TELAS.md`](docs/TELAS.md) | Todas as telas, para que servem, tamanhos de foto e limites |
| [`docs/ADMINISTRACAO.md`](docs/ADMINISTRACAO.md) | Quem administra, perfis de acesso, painel do admin |
| [`docs/BOAS_PRATICAS.md`](docs/BOAS_PRATICAS.md) | Decisões que evitam retrabalho (dados, URLs, contas, rotina) |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Deploy, rollback, backup, site fora do ar |
| [`CHANGELOG.md`](CHANGELOG.md) | O que mudou em cada versão |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | V1 revisada em sprints, V2, V3 |
| [`docs/adr/`](docs/adr/) | Registro de decisões de arquitetura |

## Rodando localmente

Pré-requisitos: Docker Desktop (ou Docker Engine + Compose), VS Code e
[uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv` no Windows).

```bash
uv tool install pre-commit && pre-commit install   # uma vez: ganchos de commit
uv sync                       # opcional: venv local para o editor (autocomplete)
cp .env.example .env          # ajuste os valores
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Dependências: `uv add <pacote>` (ou `uv add --dev <pacote>`) e depois
`docker compose up -d --build` para refazer a imagem.

- Site: http://localhost:8000 (saúde: http://localhost:8000/saude/)
- Mailpit (todos os e-mails de dev, inclusive o código do admin): http://localhost:8025
- Mídia em dev: pasta `media/` (`ARMAZENAMENTO=local`); em produção, Cloudflare R2 (`docs/adr/0002`)
- Celery: `docker compose logs -f worker`; teste rápido `docker compose exec web python manage.py testar_celery`

## Licença e confidencialidade
Projeto privado — © D'Rocha Soluções. Todos os direitos reservados.
