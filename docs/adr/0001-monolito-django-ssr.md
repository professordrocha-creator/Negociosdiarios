# ADR 0001 — Monólito Django com renderização no servidor
**Status:** aceito
**Contexto:** 1 desenvolvedor, classificados dependem de SEO, público no celular.
**Decisão:** Django Templates + HTMX; DRF só para mapa/autocomplete; PostGIS desde a V1.
**Consequência:** menos código e deploy simples; app mobile (V3) exigirá API DRF.
