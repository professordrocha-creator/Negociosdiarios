# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Pronto, sem commit: preparação para o servidor de teste/produção.** Dockerfile.prod, docker-compose.prod.yml
  (sem porta no host; nd_nginx na rede drocha_solucoes_default), deploy/nginx (realip), .env.prod.example,
  deploy.sh, backup.sh, restaurar.sh (marcados executáveis no índice do Git), docs/DEPLOY.md; SITE_NOINDEX,
  IP real só do proxy (core/middleware.py), HSTS configurável, DEMO_NO_SERVIDOR, apagar_dados_demo com texto.
- **No GitHub:** Sprints 0 a 7, Guia G1 a G3, Manual do Administrador (/painel/ajuda/).
- **Falta, em ordem:** 1) Daniel confere e faz o commit; 2) subir no servidor seguindo docs/DEPLOY.md (DNS,
  bloco do nginx externo, certbot, .env.prod, deploy.sh, superusuário, demo); 3) amigos testando; 4) revisão
  geral; G4 opcional; Sprint 8 só se pedirem; 5) lançamento (docs/DEPLOY.md §12 e docs/ROADMAP.md).
- **Pendências:** aviso por e-mail de Termos novos do site; relatório ao patrocinador (V2); limite da pausa por
  denúncias; advogado (termos, guia, lista de convites); estáticos versionados (ManifestStaticFilesStorage).
- **Pela metade:** nada.
- **Último teste que passou:** suíte completa `pytest -n auto -q` → 1038 passed, 1 skipped; ruff limpo;
  `docker compose -f docker-compose.prod.yml --env-file .env.prod.example config` ok; check --deploy só W005/W021.
