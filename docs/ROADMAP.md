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
| 6 | Pagamento Pix via API + faturas + bloqueio por inadimplência |
| 7 | Banners/patrocinadores, LGPD (meus dados, exclusão, cookies), termos |
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

## V2 — Monetizar e crescer
Assinatura no cartão + renovação, destaques, estatísticas para o anunciante,
favoritos, busca por raio, novos verticais (máquinas agrícolas, gado, empregos).

## V3 — Marketplace do agro
API pública (DRF), app mobile, parceiros logísticos.
