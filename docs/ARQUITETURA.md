# Arquitetura — Negócios Diários

## 1. Estilo arquitetural

**Monólito modular em Django**, renderizado no servidor (Django Templates + HTMX).

Por quê:
- Classificados vivem de **SEO** (Google). Página renderizada no servidor indexa
  melhor e abre mais rápido no celular 4G do interior.
- Um desenvolvedor só. Microsserviços e SPA (React) multiplicam o trabalho sem
  ganho nesta fase.
- Django REST Framework entra **apenas** onde há consumo por JavaScript
  (pontos do mapa, autocomplete) e, na V3, para o app mobile / API pública.

## 2. Containers (Docker Compose)

```
                 Internet (443)
                      │
                ┌─────▼─────┐
                │   nginx   │  TLS, arquivos estáticos, limite de upload, rate limit
                └─────┬─────┘
                      │
                ┌─────▼─────┐        ┌──────────┐
                │    web    │───────►│  redis   │  fila Celery + cache
                │ gunicorn  │        └────▲─────┘
                └─────┬─────┘             │
                      │             ┌─────┴─────┐
                ┌─────▼─────┐       │  worker   │  Celery: imagens, e-mails,
                │    db     │◄──────┤  + beat   │  expiração, cobranças
                │ PostGIS   │       └─────┬─────┘
                └───────────┘             │
                                    ┌─────▼─────┐
                                    │  storage  │  pasta media/ (dev) / Cloudflare R2 (prod)
                                    └───────────┘
```

Regras: só o `nginx` expõe porta para fora. `db` e `redis` ficam na rede
interna. Containers rodam com usuário não-root.

- **Celery** (`config/celery.py`): fila e resultados no Redis; tarefas em `<app>/tasks.py`;
  agenda no `CELERY_BEAT_SCHEDULE`. Em dev o `worker` roda com `-B` (beat junto).
- **E-mail:** todo `send_mail()` passa pelo backend `core.email.CeleryEmailBackend`, que só
  enfileira; o worker envia com SMTP (Mailpit em dev, Brevo/SES em produção) e tenta de
  novo se falhar. Nenhuma página espera servidor de e-mail.
- **Mídia:** `ARMAZENAMENTO=local|s3` (ADR 0002).

## 3. Apps Django

| App | Responsabilidade |
|---|---|
| `core` | Configurações comuns, cidades/bairros de MT, páginas institucionais, auditoria |
| `contas` | Usuário customizado (login por e-mail), 2FA para staff, recuperação de senha |
| `anunciantes` | Cadastro, verificação (CRECI/CNPJ), **vitrine pública** (`/loja/<slug>/`) |
| `anuncios` | Anúncio base + detalhes de imóvel e veículo, fotos, busca, expiração |
| `catalogo` | Tabelas de referência: marcas/modelos (FIPE), tipos de imóvel |
| `planos` | Planos, assinatura do anunciante, regra de limite de anúncios |
| `pagamentos` | Faturas, integração Mercado Pago (camada de gateway), webhooks |
| `publicidade` | Banners, cards de patrocinador, anúncio nativo; contagem de impressões |
| `moderacao` | Filas de aprovação, denúncias de anúncios, histórico de decisões |
| `estatisticas` | Visualizações e cliques no WhatsApp por anúncio (sem dado pessoal) |
| `importacao` | Importação em massa de anúncios (XML ZAP/VivaReal, planilha CSV/Excel) |
| `privacidade` | LGPD: consentimento de cookies, exportação e exclusão de dados |

Na V2, novos verticais (máquinas agrícolas, gado, empregos) entram como **novos
tipos de detalhe** do anúncio, sem mexer no núcleo.

## 4. Modelo de dados (núcleo)

```
Usuario 1──1 Anunciante 1──N Anuncio 1──N Foto
                 │                │
                 │                ├──1 DetalheImovel   (tipo, quartos, área, ponto geo…)
                 │                └──1 DetalheVeiculo  (marca/modelo FIPE, ano, km…)
                 │
                 ├──N Assinatura N──1 Plano
                 │        └──N Fatura ──N EventoPagamento (webhooks brutos, idempotência)
                 └──N Denuncia (via anúncio)
```

### Usuario (app `contas`, `AUTH_USER_MODEL`)
- Login por `email` (único, sempre em minúsculas); **sem** `username`, `first_name` e `last_name`
- `nome`, `is_active`, `is_staff`, `is_superuser`, grupos/permissões, `last_login`, `criado_em`
- Senha em hash Argon2. Mesmo modelo para anunciantes e equipe; o que cada um acessa vem dos grupos
- Grupos Administrador, Moderador, Financeiro e Comercial (migration `contas/0002`, ver `docs/ADMINISTRACAO.md`)
- `demo` (de `core.models.MarcaDemo`): conta fictícia criada pelo `criar_dados_demo`
- `email_confirmado_em`: quando clicou no link de confirmação (vazio = não confirmou; sem isso a loja não vai
  para aprovação). `AceiteDocumento` (usuário, documento termos | privacidade, versão, data) guarda os aceites
- Código de navegador novo do admin em tabelas do django-otp ligadas ao usuário:
  `EmailDevice` (código por e-mail) e `StaticDevice`/`StaticToken` (código de emergência
  gerado no servidor). Navegador confiável = cookie assinado (sem tabela). Tentativas de
  login com erro em `axes.AccessAttempt` (temporárias)

### Anunciante (a "loja") — app `anunciantes` (Sprint 1, parte 1)
Implementado: `usuario` (1:1, PROTECT), `tipo`, `nome_publico`, `slug` (único), `sigla`, `cor` (1 a 6, paleta do site;
classe CSS, sem estilo inline), `documento_tipo` + `documento_numero` (CNPJ só dígitos com dígitos verificadores;
CRECI no padrão `CRECI/UF 12345-F`; corretor autônomo = CRECI, demais = CNPJ; único), `whatsapp` (E.164),
`email_publico`, `cidade` (FK, só liberada), `status` pendente | ativo | suspenso, `motivo_status`, `demo`
(MarcaDemo), `criado_em`, `atualizado_em` e histórico (django-simple-history). O status só muda pelas ações do
admin (Aprovar/Suspender, com motivo). Planejado para as próximas sprints:
- `tipo`: corretor_autonomo | imobiliaria | revenda | concessionaria | garagem
- `logo`, `capa`, `sobre`,
  editados pelo próprio anunciante em `/painel/loja/` com prévia ao vivo, `whatsapp`, `telefone`, `email_publico`
- `endereco_publico`, `ponto` (PointField opcional), `horario`, `redes_sociais`
- `status`: + inadimplente (Sprint 6) e encerrado (Sprint 7)

### Anuncio
- `anunciante`, `categoria` (imovel | veiculo), `titulo`, `descricao`, `preco`
- `cidade`, `bairro`, `status`: rascunho | em_moderacao | publicado | pausado | expirado | removido
- `publicado_em`, `expira_em` (anúncio expira em 60 dias; renova com 1 clique)
- `destaque_ate` (V2)

### DetalheImovel
- `tipo` (casa, apartamento, kitnet, terreno, chácara, sítio, fazenda, sala comercial)
- `modalidade` (venda | aluguel), `quartos`, `banheiros`, `vagas`
- `area_total`, `area_construida`, `endereco` (privado), `ponto` (PointField)
- `exibir_localizacao`: exata | aproximada | só bairro (padrão: **aproximada**)

### DetalheVeiculo
- `marca`, `modelo`, `versao` (FK para catálogo FIPE), `ano_fabricacao`, `ano_modelo`
- `quilometragem`, `combustivel`, `cambio`, `cor`, `final_placa` (opcional, só 1 dígito)

## 5. Regras de negócio críticas

1. **Limite do plano:** publicar só se `anuncios_ativos < plano.limite`.
   Implementar em `planos/services.py` com `select_for_update()` dentro de
   transação para evitar corrida (dois cliques simultâneos).
2. **Inadimplência:** fatura vencida + 5 dias de carência → anúncios
   **pausados** (nunca apagados). Pagou → reativa automaticamente.
3. **Downgrade de plano:** o anunciante escolhe quais anúncios manter; o
   excedente fica pausado.
4. **Expiração:** tarefa Celery diária expira anúncios vencidos e avisa por e-mail.
5. **Contato por WhatsApp:** botão aponta para `/contato/<id>/whatsapp/`, que
   registra o clique (estatística para o anunciante) e redireciona para `wa.me`.
   O número não fica em texto no HTML (dificulta robôs que coletam telefones).

## 6. Busca

- V1: PostgreSQL `SearchVector` + extensões `unaccent` e `pg_trgm`
  ("apartamento" acha "Apartamento", "sinop" acha "Sinop"). Sem Elasticsearch.
- Mapa: endpoint JSON com anúncios dentro do retângulo visível (`bbox`) usando
  PostGIS. Busca por raio na V2.

## 7. Vitrine do anunciante (estilo "loja" do Mercado Livre / revendas do Usado Fácil)

- URL: `/loja/<slug>/` (subdomínio `<slug>.negociosdiarios.com.br` fica para V2+).
- Capa, logo, selo "Verificado", sobre, endereço, mapa, horário, botão WhatsApp.
- Lista de anúncios da loja com filtros próprios.
- SEO: `<title>`, meta description, Open Graph (prévia bonita ao compartilhar
  no WhatsApp), schema.org `RealEstateAgent` / `AutoDealer`, entrada no `sitemap.xml`.
- Vitrine de lojas na home (logos), como no Usado Fácil.

## 8. Imagens

Upload → Celery redimensiona (1600px + miniatura 400px), converte para WebP,
**remove EXIF** e grava no storage (pasta local em dev, R2 em produção). Original é descartado.
Limites: 10 fotos por anúncio, 8 MB por arquivo, só JPEG/PNG/WebP/HEIC.

## 9. Abrangência geográfica (pronto para vários estados)

Hoje: só Mato Grosso. Amanhã: qualquer estado, **sem mudar código nem URLs**.

```
Estado (uf, nome, liberado)            ← 27 estados, carga IBGE
  └─N Cidade (codigo_ibge, nome, slug, uf→Estado.uf, liberada, ponto)   ← 5.571 cidades, carga IBGE
        ├─N Bairro (nome, slug, ativo)
        └─N Regiao (nome, slug) via M2M  ← agrupamentos criados pelo admin
SolicitacaoCidade (anunciante, cidade, status, decidido_por, motivo)   ← app anunciantes
```
Implementado na Sprint 1 (parte 3): `Regiao` (nome, slug, cidades M2M; demo), `Bairro` (cidade, nome,
slug único por cidade, ativo; demo) no app `core`; `SolicitacaoCidade` (status pendente | liberada |
recusada, motivo, decidido_por/em, criado_em; demo) no app `anunciantes`. Liberar a cidade atende todas
as solicitações pendentes dela; loja só é aprovada (ativa) em cidade liberada.

Regras:
1. Site, filtros e cadastro mostram **só** cidades `liberada=True` de estados `liberado=True`.
2. **Um estado liberado** → seletor de estado oculto (MT fixo). **Dois ou mais** → seletor aparece sozinho.
3. Anunciante de cidade não liberada pode se cadastrar; vira `SolicitacaoCidade` para o admin.
4. Cidade com anúncios ativos não pode ser desligada sem antes pausar ou transferir os anúncios.
5. **A UF está na URL desde o primeiro dia**: `/imoveis/mt/tangara-da-serra/`. Existem cidades
   com o mesmo nome em estados diferentes; com a UF, crescer não quebra links nem o Google.
6. Textos com o nome da região (ex.: slogan "de Mato Grosso") vêm de `Configuracao`, não do HTML.
7. Lista de cidades liberadas fica em cache (Redis) e é limpa quando o admin muda algo.
8. Carga por `python manage.py carregar_municipios` (CSV em `core/dados/`), idempotente: atualiza
   dados do IBGE e nunca altera `liberado`/`liberada`. Slug da cidade é único **dentro da UF**.

### Identidade do site e páginas institucionais (app `core`)
- `Configuracao` (registro único pk=1, sem `django-solo`: `save()` força o pk e `core.services.configuracao()`
  cria o registro a partir dos `SITE_*` do settings): nome, linha da região, slogan, empresa, cidade-sede,
  símbolos claro/escuro, imagem Open Graph, favicons gerados (ico, 32, 180, 512), contatos (WhatsApp,
  e-mails, endereço, CNPJ, Instagram), textos da Sobre (quem somos, missão, visão) e limites de mídia.
  A `PaginaInstitucional` prevista virou campos da `Configuracao` (uma página só, a Sobre).
- `ValorEmpresa` (ordem, ícone, título, texto, ativo) e `TextoAjuda` (chave da tela, texto: um item por linha).
- Templates usam `{{ site.* }}` via context processor (`core.services.dados_do_site`, em cache no Redis,
  limpo no `save()`). Sem símbolo enviado, cai no SVG padrão em `static/img/`.
- Imagens (`core/imagens.py`): tipo real conferido pelo Pillow, SVG sem script/eventos/links externos
  (defusedxml), PNG/JPG regravados sem EXIF, nome UUID. Favicon gerado do símbolo claro (cairosvg para SVG).

### Dados de demonstração
Todo modelo com dados criados pelo `criar_dados_demo` herda `core.models.MarcaDemo`
(campo `demo`, indexado, não editável); `apagar_dados_demo` remove tudo com `demo=True`.
`Cidade.liberada_pela_demo` marca as cidades que a demonstração ligou, para desfazer só
essas. Fonte única dos dados fictícios: `core/dados/demo.json`.

### Home: o que aparece
1. Destaques (pagos, rótulo "Patrocinado"). 2. **Recém-anunciados** de todas as lojas,
   mais novos primeiro, **máx. 2 por loja** (rodízio justo). 3. Vitrine de lojas verificadas.

## 10. Importação de anúncios

Objetivo: a loja entra com o estoque inteiro no primeiro dia.

| Origem | Formato | Quem usa |
|---|---|---|
| Sistema da imobiliária | XML no padrão ZAP/VivaReal (arquivo ou URL do feed) | Imobiliárias |
| Planilha | CSV/Excel com modelo baixável no painel | Revendas, corretores |

Fluxo (tudo no Celery, nunca na requisição web):
1. Anunciante envia arquivo ou cadastra a URL do feed no painel.
2. **Pré-visualização**: o sistema lê, valida e mostra "32 prontos, 5 com erro (linha 12: cidade não encontrada)".
3. Anunciante confirma → anúncios criados em `em_moderacao` (ou direto `publicado` para lojas confiáveis).
4. **Respeita o limite do plano**: o excedente entra como rascunho e o painel oferece upgrade.
5. Fotos baixadas das URLs do feed e tratadas como upload normal (WebP, sem EXIF).
6. Cada anúncio guarda `codigo_externo` (código no sistema da imobiliária): reimportar **atualiza** em vez de duplicar; item que sumiu do feed é pausado.
7. Feed por URL pode ser sincronizado 1×/dia (V2).

Segurança: limite de tamanho do arquivo, parser XML seguro (`defusedxml`, contra XXE),
download de fotos só de URLs http(s) públicas, com timeout e tamanho máximo.

## 11. Ambientes

| Ambiente | Onde | Observação |
|---|---|---|
| dev | Docker no seu PC | Mídia na pasta `media/`, Mailpit, worker Celery com beat, `DEBUG=True` |
| produção | VPS (4 GB RAM é suficiente no início) | Nginx + Let's Encrypt, backups diários off-site |

Staging pode ser o mesmo VPS com outro compose project até haver clientes.
