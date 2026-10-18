# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Prontos, sem commit: Guia de Negócios G1 (base) e G2 (páginas públicas).** G1: app `guia`, admin, aceite.
  G2: menu (1º item + "Novo"; menu sanduíche novo no celular), cartão da home, rodapé, /guia/, cidade, categoria
  (lista + mapa, aberto agora, bairro, rodízio), ficha, contatos WhatsApp/telefone com contagem e limite, SEO e
  sitemap; migrations 0003/0004; demo com 64 perfis; docs (TELAS, ARQUITETURA, SEGURANCA, ADMINISTRACAO, README,
  CHANGELOG, ROADMAP).
- **No GitHub:** Sprints 0 a 7, ajustes de layout/rodapé/login, cabeçalho da loja, docs do Guia.
- **Falta, em ordem:** 1) Daniel confere no navegador (ligar "guia no ar" no admin) e põe `GUIA_CPF_CHAVE` no .env;
  commit. 2) G3 (LGPD e operação). 3) G4 opcional. 4) revisão geral; servidor de teste; Sprint 8 só se pedirem;
  Sprint 9 (lista em docs/ROADMAP.md).
- **Pendências:** aviso por e-mail de Termos novos; relatório ao patrocinador (V2); limite da pausa por denúncias;
  remoção/anonimização do perfil do guia e "não contatar" (G3); ficha diz "escreva ao e-mail" até o formulário G3.
- **Pela metade:** nada.
- **Bug corrigido, sem commit:** equipe já logada em /entrar/ ou /painel/ ia ao 403; agora vai ao admin.
- **Último teste que passou:** suíte completa 1005 passed + `pytest anuncios` 130 passed (teste antigo ajustado).
