# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Pronto, sem commit: Guia de Negócios G3 (LGPD e operação).** Migrations 0005/0006; "Esta é minha empresa"
  (/guia/pedido/<slug>/) e fila de pedidos; remoção + limpeza diária; termo novo (links, prazo de 30 dias, pausa,
  painel "quem falta"); lista de convites (CSV com prévia, convidar, não contatar, criar perfil); fila/lotes/CSV/
  estatísticas no admin; estabelecimentos regulados com horário; demo G3; rotina Celery `guia` (4:30); docs.
- **No GitHub:** Sprints 0 a 7, Guia G1 e G2, correção do acesso da equipe ao admin.
- **Falta, em ordem:** 1) Daniel confere no navegador e põe `GUIA_CPF_CHAVE` no .env; commit. 2) G4 opcional.
  3) revisão geral; servidor de teste; Sprint 8 só se pedirem; Sprint 9 (lista em docs/ROADMAP.md).
- **Pendências:** aviso por e-mail de Termos novos do site; relatório ao patrocinador (V2); limite da pausa por
  denúncias; advogado: base legal da lista de convites e guarda do "não contatar".
- **Manual do Administrador, sem commit:** docs/MANUAL_ADMIN.md + /painel/ajuda/ (link "Ajuda" no admin); testes core ok.
- **Pela metade:** nada.
- **Último teste que passou:** suíte completa 1024 passed, 1 skipped; depois de regerar a 0005 (só help_text):
  `pytest guia contas/tests/test_grupos.py` 86 passed; ruff e makemigrations --check limpos.
