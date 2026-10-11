# CLAUDE.md — Regras do projeto Negócios Diários

> Este arquivo é lido automaticamente pelo Claude Code em toda sessão.
> Ele define COMO o código deste projeto deve ser escrito. Leia também `docs/`.

## Contexto rápido
- Plataforma de classificados regionais (Mato Grosso) de **imóveis e veículos**.
- Anunciantes são **profissionais verificados** (CRECI / CNPJ) que pagam assinatura.
- Cada anunciante tem uma **vitrine pública própria** (`/loja/<slug>/`).
- Visitantes navegam **sem cadastro** e falam com o anunciante via **WhatsApp**.
- Documentos de referência: `docs/ARQUITETURA.md`, `docs/SEGURANCA.md`,
  `docs/LGPD.md`, `docs/PAGAMENTOS.md`, `docs/ROADMAP.md`, `docs/adr/`.

## Stack (não trocar sem criar um ADR em `docs/adr/`)
- Python 3.12 + Django 5 (monólito modular, templates renderizados no servidor)
- HTMX + Bootstrap 5 no frontend (sem SPA); Leaflet + OpenStreetMap nos mapas
- PostgreSQL 16 + PostGIS (imagem `postgis/postgis`) desde a V1
- Redis + Celery para tarefas assíncronas (imagens, e-mails, expiração, cobranças)
- Docker Compose (dev e produção), Nginx na frente do Gunicorn
- Mídia por `ARMAZENAMENTO=local|s3`: pasta local em dev; S3 compatível (Cloudflare R2) em produção (ADR 0002)
- E-mail sempre pela fila do Celery (`core.email.CeleryEmailBackend`); Mailpit em dev, SMTP em produção

## Regras de código
1. **Idioma:** nomes de modelos, campos e funções em português sem acento
   (`anunciante`, `limite_anuncios`). Comentários e docstrings em **português**.
2. **Todo módulo, classe e função pública tem docstring** explicando o que faz,
   por quê, e efeitos colaterais. Comente o *porquê*, não o óbvio.
3. Regra de negócio fica em `services.py` de cada app — **nunca** dentro de views
   ou templates. Views só orquestram.
4. Toda alteração de modelo vem com migration e com atualização de
   `docs/ARQUITETURA.md` (seção Modelo de Dados) se mudar a estrutura.
5. Testes com `pytest` + `pytest-django`. Nenhuma regra de negócio sem teste
   (limite do plano, bloqueio por inadimplência, webhook de pagamento, LGPD).
6. Formatação: `ruff format` + `ruff check`. Tipagem nas funções de `services.py`.
7. Cada app Django tem um `README.md` curto: responsabilidade, modelos, serviços.

## Regras de dados (ver `docs/BOAS_PRATICAS.md`)
- Cidade = FK para tabela IBGE; bairro = FK; veículo = FK para catálogo FIPE. Nunca texto livre.
- Dinheiro em `DecimalField`; nunca `float`. Telefone em E.164. CPF/CNPJ só dígitos.
- `TIME_ZONE = "America/Cuiaba"`, `USE_TZ = True`.
- Preços, limites e prazos vêm do banco (admin), nunca fixos no código.
- Nada é apagado de verdade pelo usuário: exclusão lógica + `django-simple-history`.
- Migration já aplicada nunca é editada.
- Permissões por grupos do Django (Administrador, Moderador, Financeiro, Comercial);
  Daniel é o único superusuário. Ver `docs/ADMINISTRACAO.md`.

## Regras de telas (ver `docs/TELAS.md`)
- Toda tela inclui o parcial `_ajuda.html` ("Sobre esta tela") com texto do modelo `TextoAjuda`.
- Todo campo com limite/formato tem `help_text`. Limites (tamanho de foto, nº de fotos,
  caracteres) vêm de `Configuracao`, nunca fixos no código ou no template.
- Cidades/estados exibidos = só os liberados (`Cidade.liberada`, `Estado.liberado`).
  Seletor de estado só aparece com 2+ estados liberados. URLs sempre com a UF.

## Regras de segurança (obrigatórias — ver `docs/SEGURANCA.md`)
- **Nunca** commitar segredos. Tudo vem de variáveis de ambiente (`.env`).
- **Nunca** usar `|safe`, `mark_safe` ou SQL cru com dados do usuário.
- Todo upload de imagem: validar tipo real (Pillow), limitar tamanho,
  **reprocessar e remover EXIF** (GPS das fotos é dado pessoal).
- Toda view de anunciante filtra por `request.user.anunciante` (sem IDOR).
- Webhooks de pagamento: validar assinatura e ser **idempotentes**.
- Logs **sem** dados pessoais (CPF, telefone, e-mail, IP completo).

## Regras de LGPD (ver `docs/LGPD.md`)
- Coletar só o necessário. Antes de criar um campo com dado pessoal,
  registrar finalidade e base legal na tabela de `docs/LGPD.md`.
- Dados pessoais novos devem entrar na exportação ("Meus dados") e na rotina
  de exclusão/anonimização.

## Economia de tokens (como trabalhar com o Claude Code)
- Este arquivo fica **curto**. Detalhes ficam em `docs/` e só são lidos quando a tarefa pedir.
- Uma tarefa por sessão (ex.: "Sprint 3: model DetalheImovel + testes"). Ao terminar, `/clear`.
- Em conversas longas use `/compact`. Use `/cost` para acompanhar o consumo.
- Peça mudanças citando o arquivo exato (`anuncios/services.py`), não "procure no projeto".
- Não ler `migrations/`, `staticfiles/`, `media/`, `node_modules/` nem arquivos `.lock`.
- Respostas: mostrar só o diff/trecho alterado, sem repetir arquivos inteiros.
- Planejar antes de tarefas grandes (modo plano) e executar em passos pequenos.

## Comandos úteis
```bash
docker compose up -d --build            # sobe o ambiente
docker compose exec web python manage.py migrate
docker compose exec web pytest
docker compose exec web ruff check .
```
