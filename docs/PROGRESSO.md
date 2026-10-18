# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Agora:** Sprint 7B parte 2 (denúncia de anúncio) — ainda não começada.
- **Feito:** Sprints 0 a 6; 7A (publicidade: patrocinador, campanha, peças, rodízio, clique, métricas, painel/CSV,
  fatura por link `/fatura/<token>/`); 7B parte 1 (termos/política com versão e aceite, cookies só essenciais,
  Meus dados: baixar e excluir, pedidos do titular). Tudo commitado (último: 17bdfb7).
- **Falta, em ordem:**
  1. 7B parte 2: denúncia de anúncio (formulário público, fila no admin, e-mail opcional do denunciante — ver LGPD.md).
  2. Sprint 8: importador de anúncios (XML ZAP/VivaReal e planilha CSV/Excel).
  3. Sprint 9: lançamento (check --deploy, backup testado, SEO, apagar dados demo, lojas fundadoras) + Produção (VPS).
- **Pela metade:** nada.
- **Último teste que passou:** `docker compose exec web pytest -n auto -q` → 920 passed.
