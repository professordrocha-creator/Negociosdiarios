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
| `catalogo` | Catálogo de veículos da Tabela FIPE: marca → modelo → versão, por tipo (carro, caminhonete, moto, caminhão) |
| `planos` | Planos, assinatura do anunciante, regra de limite de anúncios |
| `pagamentos` | Faturas, Pix estático, comprovantes, régua de cobrança (V1, Sprint 6); gateway Mercado Pago e webhooks na V2 |
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
                 ├──1 Assinatura N──1 Plano
                 │        └──N Fatura   (Sprint 6; EventoPagamento dos webhooks só na V2)
                 ├──N PedidoTrocaPlano
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
admin (Aprovar/Suspender, com motivo).
Sprint 2 (página da loja), editados pelo anunciante em `/painel/loja/` com prévia ao vivo: `sobre` (500),
`endereco_publico` + `mostrar_no_mapa`, `horario`, `instagram`, `site`, `logo` (WebP 400) + `logo_mini` (96),
`capa` (WebP 1600, 4:1) + `capa_media` (800). O envio fica em `logo_original`/`capa_original` até o Celery
gerar os WebP (`anunciantes.tasks.processar_imagem_loja`); depois o original é apagado.
Sprint 5: `ponto` (PointField WGS 84, opcional), marcado no mapa do painel (perto da cidade da loja). Só é
público com `mostrar_no_mapa`: mapa da busca de veículos e mapa da página da loja (corretor autônomo pode
ter marcado a própria casa).
Planejado: `telefone`.
- `status`: + inadimplente (Sprint 6) e encerrado (Sprint 7)

### Plano, Assinatura e PedidoTrocaPlano — app `planos` (Sprint 2, parte B)
- `Plano`: `nome`, `slug` (únicos), `limite_anuncios`, `preco_mensal`, `preco_anual` (Decimal), `ativo` (à venda),
  `ordem`, histórico. Os 3 planos iniciais vêm da migration `planos/0002` (valores que estavam no settings);
  daí em diante só mudam no admin. Não se apaga plano: desmarca "à venda".
- `Assinatura` (1:1 com `Anunciante`): `plano` (PROTECT), `periodicidade` (mensal | anual), `inicio`,
  `vencimento`, `situacao` (ativa | em_atraso | cancelada), `demo`, histórico (quem mudou e por quê).
- `PedidoTrocaPlano`: `anunciante`, `plano_atual`, `plano_novo`, `periodicidade`, `status`
  (pendente | aprovado | recusado), `motivo`, `decidido_por`, `decidido_em`, `demo`. Um pendente por loja.
- `Configuracao.carencia_dias` (padrão 5): dias depois do vencimento até a assinatura virar em_atraso.
- Sinais `planos.sinais.assinatura_em_atraso` / `assinatura_regularizada`: o app de anúncios (Sprint 3)
  se conecta para pausar/reativar, sem o app planos conhecer o modelo de anúncio.

### Fatura e ModeloEmailCobranca — app `pagamentos` (Sprint 6; docs/PAGAMENTOS.md)
- `Fatura`: `assinatura` (PROTECT), `codigo` (`ND-FT-00001`, do id), `competencia` (início do período) e
  `periodo_fim`, `descricao` ("Profissional · mensal"), `valor` (Decimal), `vencimento`, `situacao` (aberta |
  aguardando_confirmacao | paga | vencida | cancelada), `pago_em`, `forma` (pix | boleto | transferencia |
  dinheiro | outro), `link_boleto` (opcional), `comprovante` (armazenamento **privado**, nome aleatório),
  `comprovante_enviado_em`, `observacao`, `motivo_recusa`, `confirmado_por`, `avisos_enviados` (régua; fora
  do histórico), `demo`, histórico. Única por assinatura + competência (cancelada não conta). Nada se apaga.
- `ModeloEmailCobranca`: `chave` (fatura_disponivel, lembrete_3_dias, vence_hoje, vencida_1_dia,
  vencida_3_dias, pagamento_confirmado, comprovante_recusado), `assunto`, `corpo` (variáveis entre chaves,
  conferidas no `clean`), `ativo`, histórico. Os registros vêm da migration `pagamentos/0002`.
- `Configuracao` ganhou `fatura_antecedencia_dias` (padrão 10) e `limite_comprovante_kb` (padrão 5120).

### Anuncio — app `anuncios` (Sprint 3, parte A; índices de busca na 4B)
- `anunciante` (PROTECT), `categoria` (imovel | veiculo), `codigo` público único (`ND-IM-00001`, gerado do id
  na primeira gravação, nunca muda), `titulo` (limites na `Configuracao`), `slug`, `descricao`, `preco` (Decimal)
- `cidade` (FK, só liberada), `bairro` (FK, opcional), `situacao`: rascunho | em_moderacao | publicado |
  pausado | expirado | removido (exclusão lógica, com `removido_em`)
- `pausado_por` (cliente | atraso | downgrade: só a pausa por atraso volta sozinha com o pagamento),
  `motivo_moderacao`, `moderado_por`
- `publicado_em` (primeira publicação; não muda ao renovar), `expira_em` (prazo da `Configuracao`, padrão
  60 dias; Renovar), `destaque_ate` (V2), `demo`, `criado_em`, `atualizado_em`, histórico
- Proxy `AnuncioEmModeracao`: a "Fila de moderação" do admin
- Contam no plano: publicado + em_moderacao
- Busca (Sprint 4B): `busca` (SearchVectorField) e `texto_busca` (trigram), fora do histórico; ver §6

### DetalheImovel (1:1 com Anuncio, chave = o anúncio)
- `tipo` (casa, apartamento, kitnet, terreno, chácara, sítio, fazenda, sala comercial, barracão)
- `modalidade` (venda | aluguel), `quartos`, `banheiros`, `vagas`
- `area_total`, `area_construida` (m², Decimal), `iptu` (anual, opcional), `endereco` (**privado**),
  `ponto` (PointField WGS 84, **privado**: o público vê conforme a opção abaixo), histórico
- `exibir_localizacao`: exata | aproximada | so_bairro (padrão: **aproximada**)
- `ponto_publico` (Sprint 5; PointField, não editável, fora do histórico, índice GiST): o ponto que o
  público pode ver, recalculado no `save()` por `anuncios/localizacao.py` (exata = o ponto; aproximada =
  o ponto deslocado, 4 casas; só o bairro ou sem ponto = vazio). O mapa da busca e o filtro de área
  usam só ele. Migration `0011` calculou o dos anúncios que já existiam.

### Foto
- `anuncio`, `ordem` (a menor é a capa), `original` (envio; apagado depois do processamento),
  `imagem` (WebP 1600), `miniatura` (WebP 400), `compartilhamento` (JPEG 1200×630 para o Open Graph:
  WhatsApp e Facebook não mostram WebP de forma confiável na prévia), `criado_em`. Foto excluída pelo
  anunciante é apagada de verdade (arquivo e registro).

### EstatisticaDiaria — app `estatisticas` (Sprint 3, parte B)
- `anuncio` (CASCADE), `dia` (fuso do site), `visualizacoes`, `cliques_whatsapp`, `demo`; único por anúncio
  e dia. Só totais: a contagem "1 por visitante por dia" usa um hash com sal aleatório do dia guardado
  apenas no cache (`estatisticas.services.registrar`); robôs, prévias de link e o dono não contam.

### DetalheVeiculo
Implementado na Sprint 4A (1:1 com Anuncio, chave = o anúncio, histórico):
- `versao` (FK PROTECT para `catalogo.Versao`; marca, modelo e tipo vêm dela), `ano_fabricacao`, `ano_modelo`
  (o mesmo ou o seguinte), `quilometragem`, `combustivel`, `cambio`, `cor`, `portas` (opcional; moto sem),
  `final_placa` (opcional, só 1 dígito: nunca a placa inteira), `opcionais` (ArrayField de escolhas fixas:
  ar, direção, vidros, travas, ABS, multimídia, 4x4...)
- Anúncio de veículo: código `ND-VE-00001`, sem mapa e sem etapa de localização (a cidade fica nos dados);
  a página mostra o endereço da loja só se ela marcou "mostrar no mapa". Título em branco = marca +
  modelo + versão + ano.

### Catálogo de veículos — app `catalogo` (Sprint 4A)
`Marca` (nome, slug único, ativo) → `Modelo` (marca, tipo: carro | caminhonete | moto | caminhao, nome,
slug, ativo; único por marca+tipo+slug) → `Versao` (modelo, nome, código FIPE, ativo; única por
modelo+nome). Carga de `catalogo/dados/fipe.csv` (Tabela FIPE de outubro/2026, 11.422 versões) pelo
`carregar_catalogo` (idempotente, em lote, nunca apaga); `atualizar_catalogo_fipe` regera o CSV pela API
pública da FIPE. A FIPE junta modelo e versão e lista picapes como carro: as regras de separação estão em
`catalogo/services.py` (ver `catalogo/README.md`). Selects encadeados no painel via HTMX (`anuncios:catalogo`).

## 5. Regras de negócio críticas

1. **Limite do plano:** publicar só se `anuncios_ativos < plano.limite`.
   Implementado em `planos.services.reservar_vaga(anunciante, contar, publicar)`: trava a linha da
   assinatura com `select_for_update()` numa transação (dois cliques simultâneos: só um publica;
   teste de concorrência com duas conexões). `pode_publicar` é só a resposta rápida para a tela.
2. **Inadimplência (Sprint 6: ligada à fatura):** a rotina diária `pagamentos.services.rotina_de_cobranca`
   (Celery beat, 6h) gera a fatura do próximo ciclo `Configuracao.fatura_antecedencia_dias` antes do
   vencimento, marca como vencida a fatura não paga no dia seguinte ao vencimento e, com fatura a pagar
   vencida há mais que `Configuracao.carencia_dias` (padrão 5), põe a assinatura `em_atraso`
   (`planos.services.processar_atrasos`): sinal para **pausar** os anúncios (nunca apagar) e e-mail.
   Comprovante aguardando confirmação não pausa (a equipe decide; recusado, volta a vencida). Pagamento
   confirmado (`pagamentos.services.confirmar_pagamento`: ação do admin ou "Registrar pagamento manual")
   → fatura paga, assinatura renovada uma vez (`planos.services.renovar_assinatura`) e, se estava em
   atraso, volta a ativa e o sinal reativa os anúncios.
3. **Downgrade de plano:** `aplicar_downgrade(assinatura, plano_novo, anuncios, manter, pausar)`: o
   anunciante escolhe quais manter (no máximo o novo limite, só dentre os dele); o excedente fica
   pausado. Tela `/painel/plano/escolher-anuncios/`: a escolha fica no `PedidoTrocaPlano.anuncios_manter`
   e é aplicada na aprovação (publicado → pausado por downgrade; em análise → rascunho). Sem escolha, o
   admin não aprova.
   Sinais: `anuncios.receptores` liga `assinatura_em_atraso` → `pausar_por_atraso` e
   `assinatura_regularizada` → `reativar_apos_pagamento`.
4. **Expiração:** `anuncios.tasks.expirar_anuncios` (Celery beat, 3h) passa os publicados com prazo
   vencido para `expirado` (nunca apagados) e manda um e-mail por loja. "Renovar" aparece a partir de
   `Configuracao.aviso_expiracao_dias` (padrão 5) e no expirado (que precisa de vaga no plano).
4a. **Moderação:** `Configuracao.moderacao` = só o primeiro anúncio da loja (padrão) | todos | nenhum.
   Em análise conta no plano. Recusa volta para rascunho com o motivo (e-mail); aprovação publica (ou
   deixa pausado por atraso, se a assinatura não estiver ativa). Com "todos", editar um publicado o
   devolve para a análise.
4b. **Publicar/reativar/renovar expirado** passam por `planos.services.reservar_vaga` (trava da
   assinatura): `anuncios.services.enviar_para_publicacao`, `reativar`, `renovar`.
5. **Contato por WhatsApp:** botão aponta para `/anuncio/<codigo>/whatsapp/` (Sprint 3B), que
   registra o clique (estatística para o anunciante) e redireciona para `wa.me` com a mensagem pronta
   citando o código. O número não fica em texto no HTML (dificulta robôs que coletam telefones);
   o robots.txt bloqueia esses redirecionamentos.
6. **Visibilidade pública** (`anuncios.services.anuncios_visiveis`): publicado, de loja visível (ativa, área
   atendida; demo só com MOSTRAR_DEMO) e em cidade liberada de estado liberado. Vale para a página do
   anúncio, a home, a vitrine da loja, "Mais desta loja", os parecidos e o sitemap.
6a. **Ramo da loja** (`anuncios.services.categorias_permitidas` / `conferir_categoria`): corretor autônomo e
   imobiliária anunciam só imóveis; revenda, concessionária e garagem, só veículos. Vale no serviço que
   cria o anúncio (não só na tela), então URL montada à mão também é recusada.
7. **Localização pública** (`anuncios/localizacao.py`, a única regra; `localizacao_publica` para a página):
   exata → o ponto; aproximada → círculo de 300 m com o centro deslocado de 60 a 150 m de forma fixa por
   anúncio (HMAC do código com a SECRET_KEY: recarregar não revela o ponto pela média); só o bairro → sem
   mapa. O deslocado fica gravado em `DetalheImovel.ponto_publico`. O ponto exato e o endereço nunca vão
   para o HTML nem para o JSON do mapa no modo aproximado, e o filtro "Buscar nesta área" também olha só o
   ponto público (perguntar "está neste retângulo?" várias vezes não revela o ponto real).

## 6. Busca

- V1: PostgreSQL `SearchVector` + extensões `unaccent` e `pg_trgm`
  ("apartamento" acha "Apartamento", "sinop" acha "Sinop"). Sem Elasticsearch.
- **Implementado na Sprint 4B (app `busca`)**: `/imoveis/`, `/veiculos/` e por cidade
  (`/imoveis/<uf>/<cidade>/`, UF minúscula, só cidade liberada; o resto é 404). Filtros na query string
  (imóvel: `modalidade`, `tipo` (vários), `bairro`, `preco_min`/`preco_max`, `quartos`, `vagas`,
  `area_min`/`area_max`; veículo: `tipo`, `marca`, `modelo` (slugs do catálogo), `ano_min`/`ano_max`,
  preço, `km_max`, `cambio`, `combustivel`), `q`, `ordem` (recentes | menor_preco | maior_preco; com texto
  e sem ordem, por relevância) e `pagina` (24 por página). Valor inválido é descartado; sem JavaScript, a
  URL "suja" do formulário (campos vazios, `?cidade=mt/...`) redireciona (302) para a limpa; com HTMX, a
  view responde direto e manda a limpa em `HX-Push-Url`.
- Índice de texto: `Anuncio.busca` (SearchVectorField, configuração `pt_unaccent` = português com radicais e
  sem acento; título peso A, o resto peso B: descrição, cidade, bairro, tipo, negócio, marca, modelo,
  versão, cor, combustível) e `Anuncio.texto_busca` (texto curto sem acento, índice GIN `gin_trgm_ops`
  para erro de digitação). Recalculados a cada gravação do anúncio ou da ficha (`anuncios.receptores` →
  `anuncios/indice.py`); `reindexar_busca` refaz tudo. Consulta: `websearch` no vetor OU
  `trigram_word_similar` no texto.
- Índices dos filtros: `anuncio_vitrine` (situação, categoria, cidade, -publicado_em), `anuncio_preco`,
  `imovel_tipo_modalidade`, `imovel_quartos`, `imovel_area`, `veiculo_ano`, `veiculo_km`, mais os GIN.
  Teste de desempenho com 2.000 anúncios gerados no próprio teste (`busca/tests/test_desempenho.py`).
- SEO: title/description por cidade e tipo ("Casas à venda em Tangará da Serra – MT"), canonical sem
  `ordem`/`pagina`, `noindex, follow` com texto ou mais de 2 filtros de conteúdo; páginas de cidade,
  cidade + negócio + tipo (imóvel) e cidade + tipo (veículo) com anúncio entram no sitemap.
- **Mapa (Sprint 5)**: na página da busca, `Lista | Mapa` no celular/tablet (só CSS) e mapa ao lado da lista
  no computador (≥ 1200 px), Leaflet + Leaflet.markercluster servidos pelo site (`static/vendor/`), tiles
  do OpenStreetMap, sem script inline (`static/js/mapa-busca.js`).
  - JSON: `/imoveis/mapa.json`, `/imoveis/<uf>/<cidade>/mapa.json` (e o mesmo para veículos), com os mesmos
    filtros da lista (`busca.services.dados_do_mapa`; `url_do_mapa` tira `ordem`/`pagina`). Por ponto só
    `id`, `titulo` (60), `preco` (curto: "420 mil", "1,6 mil/mês"), `lat`, `lng`; mais `total`,
    `sem_localizacao` e `cortado`. No máximo `MAPA_LIMITE_PONTOS` (settings/env, padrão 500), os mais
    novos. Cache público de 60 s e `X-Robots-Tag: noindex`.
  - Imóvel: um ponto por anúncio, do `ponto_publico` (só o bairro fica fora e entra em
    `sem_localizacao`: "X anúncios sem localização no mapa"). Veículo: um ponto por **loja** com
    `mostrar_no_mapa` e `ponto`, com quantos veículos dela atendem aos filtros.
  - Ao clicar no marcador, o card vem do servidor (`/mapa/cartao/anuncio/<codigo>/`,
    `/mapa/cartao/loja/<slug>/`; só anúncio/loja visível, HTML escapado): foto, preço, título e link.
  - "Buscar nesta área": aparece ao mover o mapa; grava `area=oeste,sul,leste,norte` (5 casas) no campo
    oculto do formulário e envia pelo HTMX, mantendo os outros filtros. Filtro com PostGIS
    (`ponto_publico__within` / `anunciante__ponto__within` de `Polygon.from_bbox`); vira chip "Área do
    mapa" e a página fica `noindex`. Área inválida é descartada.
  - Busca por raio na V2.

## 7. Vitrine do anunciante (estilo "loja" do Mercado Livre / revendas do Usado Fácil)

- URL: `/loja/<slug>/` (subdomínio `<slug>.negociosdiarios.com.br` fica para V2+).
- Capa, logo, selo "Verificado", sobre, endereço, mapa, horário, botão WhatsApp.
- Lista de anúncios da loja com filtros próprios (filtros na Sprint 4).
- Implementado na Sprint 2: `anunciantes.views.loja` (só `lojas_visiveis()`: ativa, cidade liberada; demo só com
  MOSTRAR_DEMO; o resto é 404), canonical, Open Graph, JSON-LD (`|json_ld`, escapado como o `json_script`),
  `/sitemap.xml` (`config/sitemaps.py`) e `/robots.txt`. WhatsApp via `/loja/<slug>/whatsapp/` (302 para o
  wa.me; o número não vai no HTML). `/lojas/` com filtro por tipo e cidade; a vitrine da home lê do banco.
- SEO: `<title>`, meta description, Open Graph (prévia bonita ao compartilhar
  no WhatsApp), schema.org `RealEstateAgent` / `AutoDealer`, entrada no `sitemap.xml`.
- Vitrine de lojas na home (logos), como no Usado Fácil.

## 8. Imagens

Logo e capa da loja (Sprint 2) já seguem este fluxo (`core/imagens.py`: tipo real, dimensões mínimas,
limites da `Configuracao`, rotação do EXIF aplicada e EXIF descartado, recorte pelo centro, WebP sem ampliar).
Fotos de anúncio (Sprint 3, parte A; "fotos fáceis" depois da Sprint 6, `anuncios.services`):
1. **No navegador** (`static/js/reduzir-fotos.js`): foto maior que 2560 px ou 3 MB vira JPEG de até 2560 px
   (orientação do celular aplicada) antes do envio: rápido no 4G e sem esbarrar no limite. Falhou ou não
   abriu (ex.: HEIC fora do Safari), vai o arquivo original. Sem JavaScript, também vai o original.
2. **No servidor** (rede de segurança, `core.imagens.validar_foto`): tipo real pelo Pillow (JPEG, PNG, WebP e
   HEIC/HEIF pelo `pillow-heif`), até `Configuracao.limite_foto_anuncio_kb` (15 MB) e mínimo aceito
   `foto_min_*` (200×150: só recusa ícone/miniatura). Foto abaixo de `foto_aviso_*` (800×600) é aceita e o
   painel mostra "Foto pequena" (`Foto.largura`/`altura`, `marcar_fotos_pequenas`).
3. **No Celery** (`anuncios.tasks.processar_foto`): aplica a rotação, descarta EXIF (GPS), gera WebP 1600 +
   miniatura 400 (nunca amplia), grava as dimensões e apaga o original (inclusive o HEIC).
Logo e capa da loja não mudaram: só JPG/PNG/WebP e os mínimos de antes (a página da loja precisa de
qualidade).
Mapa do painel: Leaflet 1.9.4 servido pelo site (`static/vendor/leaflet/`, sem CDN) e tiles do OpenStreetMap.

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
essas. Fonte única dos dados fictícios: `core/dados/demo.json`. Desde a Sprint 3B os imóveis do
demo.json viram anúncios publicados no banco (`anuncios.demo`), com 3 a 5 fotos desenhadas pelo Pillow
(mesmo processamento das reais), pontos em Tangará (um exato, dois aproximados, um só bairro) e
estatísticas fictícias de 30 dias. Os veículos entram no banco na Sprint 4.

### Home: o que aparece
1. Destaques (`destaque_ate` no futuro). 2. **Recém-anunciados** de todas as lojas,
   mais novos primeiro, **máx. 2 por loja** (rodízio justo). 3. Vitrine de lojas verificadas (por anúncios
   visíveis). Desde a Sprint 3B as três leem do banco (`core.services.destaques`/`recem_anunciados` e
   `anunciantes.services.lojas_verificadas`, só o corpo mudou), sempre só com anúncios visíveis.

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
