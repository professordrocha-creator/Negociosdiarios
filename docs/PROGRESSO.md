# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Pronto, sem commit: lote de correções do admin.** Destaque editável; Pausar/Reativar/Remover anúncio no admin
  (anuncios/0015); caixa "Pendências" no admin; menus "Configurações do site" e "Faturas e pagamentos" (core/0019);
  "mostrar botão Renovar"; estáticos versionados (ESTATICOS_VERSIONADOS); nd_nginx com resolver (fim do 502);
  ajuda do criar_dados_demo; manual atualizado.
- **No GitHub:** Sprints 0 a 7, Guia G1 a G3, Manual do Administrador, preparação para o servidor (deploy).
- **Falta, em ordem:** 1) Daniel confere e faz o commit; 2) subir no servidor seguindo docs/DEPLOY.md; 3) amigos
  testando; 4) revisão geral; G4 opcional; Sprint 8 só se pedirem; 5) lançamento (docs/DEPLOY.md §12).
- **Pendências:** aviso por e-mail de Termos novos do site; relatório ao patrocinador (V2); limite da pausa por
  denúncias; advogado (termos, guia, lista de convites).
- **Pela metade:** nada.
- **Último teste que passou:** suíte completa `pytest -n auto -q` → 1051 passed, 1 skipped; ruff limpo;
  compose de produção válido; `nginx -t` ok; imagem de produção com estáticos versionados.
