# Roadmap

## Antes da Sprint 0 — validar o negócio
- [ ] Mostrar o protótipo a 5–10 imobiliárias e revendas de Tangará da Serra.
- [ ] Fechar 2–3 "planos fundadores" (desconto vitalício em troca de entrar no lançamento).
- [ ] Planilha de custos mensais e ponto de equilíbrio (quantos assinantes pagam a operação).
- [ ] Contador: abertura de CNPJ e emissão de nota. Advogado: termos de uso e contrato do anunciante.
- [ ] Estratégia de lançamento: só Tangará da Serra primeiro, com as lojas fundadoras já com estoque.

## V1 — Lançar e validar (sprints de 2 semanas)
| Sprint | Entrega |
|---|---|
| 0 | Git/GitHub, Docker, Django, PostGIS, CI, cidades IBGE, grupos de permissão, admin com 2FA, deploy de "olá mundo" no VPS com HTTPS e backup testado |
| 1 | Contas, cadastro de anunciante, verificação CRECI/CNPJ no admin |
| 2 | **Vitrine do anunciante** `/loja/<slug>/` + planos e limite de anúncios |
| 3 | Anúncio de imóvel + fotos (Celery, WebP, sem EXIF) + moderação |
| 4 | Anúncio de veículo (catálogo FIPE) + busca com filtros |
| 5 | Mapa Leaflet, WhatsApp com contagem de cliques, home com vitrine de lojas |
| 6 | Pagamento Pix via API + faturas + bloqueio por inadimplência |
| 7 | Banners/patrocinadores, LGPD (meus dados, exclusão, cookies), termos |
| 8 | **Importador de anúncios**: XML padrão ZAP/VivaReal (imóveis) e planilha CSV/Excel (veículos e imóveis) |
| 9 | Testes, `check --deploy`, backup testado, SEO (sitemap, OG), carga das lojas fundadoras → **lançamento** |

Dica: se o tempo apertar, lance **um vertical primeiro** (onde já houver clientes interessados).

## V2 — Monetizar e crescer
Assinatura no cartão + renovação, destaques, estatísticas para o anunciante,
favoritos, busca por raio, novos verticais (máquinas agrícolas, gado, empregos).

## V3 — Marketplace do agro
API pública (DRF), app mobile, parceiros logísticos.
