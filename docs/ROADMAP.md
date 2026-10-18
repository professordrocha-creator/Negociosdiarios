# Roadmap

## Antes da Sprint 0 — validar o negócio
- [ ] Mostrar o protótipo a 5–10 imobiliárias e revendas de Tangará da Serra.
- [ ] Fechar 2–3 "planos fundadores" (desconto vitalício em troca de entrar no lançamento).
- [ ] Planilha de custos mensais e ponto de equilíbrio (quantos assinantes pagam a operação).
- [ ] Contador: abertura de CNPJ e emissão de nota. Advogado: termos de uso e contrato do anunciante.
- [ ] Estratégia de lançamento: só Tangará da Serra primeiro, com as lojas fundadoras já com estoque.

## Regra: dados de demonstração (decisão de 2026-10-11)
O sistema é construído inteiro com dados fictícios até o lançamento. Toda sprint deve
ampliar o comando `criar_dados_demo` para cobrir o que foi criado nela (anunciantes,
lojas, anúncios com fotos de exemplo, planos, faturas, banners, denúncias etc.), para
que cada tela possa ser vista e testada no navegador. Regras:
- só roda com `DEBUG=True`;
- tudo marcado como demonstração;
- `apagar_dados_demo` remove tudo de uma vez;
- senhas dos usuários demo vêm de `DEMO_SENHA` no `.env`;
- na Sprint 9 (lançamento), os dados demo são apagados e não vão para produção.

**Ordem de trabalho:** 4c (home demo) → 4d (páginas institucionais do rodapé) → Sprint 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9,
parando no fim de cada etapa para teste no navegador.

## V1 — Lançar e validar (sprints de 2 semanas)
| Sprint | Entrega |
|---|---|
| 0 | Git/GitHub, Docker, Django, PostGIS, CI, cidades IBGE, layout base, grupos de permissão, admin protegido (URL secreta, código por e-mail, bloqueio), Celery, e-mail e mídia. *A etapa 8 (produção) foi adiada: ver "Produção" abaixo* |
| 1 | Contas, cadastro de anunciante, verificação CRECI/CNPJ no admin |
| 2 | **Vitrine do anunciante** `/loja/<slug>/` + planos e limite de anúncios + comando `criar_dados_demo` (1 corretor com CRECI e 5 revendas de veículos fictícios; não roda em produção; tudo marcado como demonstração) |
| 3 | Anúncio de imóvel + fotos (Celery, WebP, sem EXIF) + moderação |
| 4 | Anúncio de veículo (catálogo FIPE) + busca com filtros |
| 5 | Mapa Leaflet, WhatsApp com contagem de cliques, home com vitrine de lojas |
| 6 | **Cobrança manual assistida** (decisão de 2026-10-12): faturas geradas X dias antes, Pix estático (copia e cola + QR Code, sem API), "Já paguei" com comprovante, confirmação no admin (painel de cobrança), régua de e-mails editáveis e pausa por fatura vencida. Integração com gateway: V2 |
| 7 | **7A (feita):** publicidade vendida direto (patrocinadores, campanhas, banner/card/nativo, rodízio, métricas sem dado pessoal, painel/CSV, fatura Pix). **7B parte 1 (feita):** termos e política com versão e aceite, cookies (só essenciais, sem banner), Meus dados (baixar e excluir), pedidos dos titulares. **7B parte 2 (feita):** denúncia de anúncio |
| 8 | **Importador de anúncios**: XML padrão ZAP/VivaReal (imóveis) e planilha CSV/Excel (veículos e imóveis) |
| 9 | Testes, `check --deploy`, backup testado, SEO (sitemap, OG), **apagar os dados demo** (`apagar_dados_demo`), carga das lojas fundadoras → **lançamento** |

Dica: se o tempo apertar, lance **um vertical primeiro** (onde já houver clientes interessados).

### Produção (antiga etapa 8 da Sprint 0) — quando a VPS for contratada, antes do lançamento
Decisão de 2026-10-11: sem VPS ainda, a Sprint 0 termina no CI (etapa 7) e o trabalho
segue para as Sprints 1 e 2. Antes do lançamento (no máximo junto da Sprint 9):
`docker-compose.prod.yml` (Gunicorn, Nginx, Let's Encrypt, beat separado do worker),
VPS Ubuntu 24.04 endurecida (`docs/SEGURANCA.md` §3), R2 e SMTP reais, axes lendo o IP
real atrás do Nginx, `check --deploy` sem avisos, backup **restaurado em teste** e
"olá mundo" no ar com HTTPS.

### Guia de Negócios (registrado em 2026-10-12; ordem decidida em 2026-10-18)
Diretório **gratuito** de serviços, profissionais e comércios (app `guia`). Especificação completa em
`docs/GUIA.md` e `docs/GUIA_LGPD_E_TERMO.md`. Vem **antes** da Sprint 8, que ficou adiada (só volta se o teste
com amigos e as lojas fundadoras pedirem). Cada etapa termina com testes, TextoAjuda, docs, CHANGELOG e
`docs/PROGRESSO.md`; o commit é do Daniel.

| Etapa | Entrega |
|---|---|
| **G1 — Base** (feita) | Modelos e migrações, carga de categorias (`carregar_categorias_guia`), admin do guia (celular), cadastro assistido, termo, convite e aceite (`/guia/aceite/<token>/`), regras de publicação, grupo **Guia**, demo mínima |
| **G2 — Público** (feita) | Páginas de cidade, categoria e ficha, lista + mapa, busca (`unaccent`/`pg_trgm`), "aberto agora", SEO e sitemap, contagem de cliques |
| **G3 — LGPD e operação** (feita) | Pedidos do titular ("Esta é minha empresa"), revogação, termo novo (prazo de 30 dias), lista de convites e "não contatar", fila e ações em lote, demo completa (~60 perfis) |
| **G4 — Opcional** | Autocadastro com aprovação, selo de verificação, ajustes de uso (depois das primeiras 50 a 100 empresas) |

Depois do guia: revisão geral e correções em lote, servidor de teste (subdomínio, `noindex`) com amigos,
Sprint 8 se for necessária, e a Sprint 9.

## V2 — Monetizar e crescer
**Pagamento integrado (Mercado Pago)**: Pix com confirmação automática por webhook e assinatura no cartão com renovação (ver `docs/PAGAMENTOS.md`, V2), destaques, estatísticas para o anunciante,
favoritos, busca por raio, novos verticais (máquinas agrícolas, gado, empregos).

## V3 — Marketplace do agro
API pública (DRF), app mobile, parceiros logísticos.
