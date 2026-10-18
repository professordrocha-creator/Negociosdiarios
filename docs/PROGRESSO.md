# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Prontos, sem commit:** 7B parte 2 (denúncias), ajustes de layout/rodapé/login da equipe, cabeçalho da loja
  (nome abaixo da capa, botão WhatsApp com ícone novo) e guias movidos para `docs/GUIA*.md` e `docs/guia/`.
- **Feito e no GitHub:** Sprints 0 a 6, 7A e 7B parte 1.
- **Falta, em ordem (decisão de 18/10/2026):** 1) conferir no navegador (Ctrl+F5) e commitar; 2) Guia de Negócios:
  G1 base, G2 público, G3 LGPD e operação, G4 opcional (autocadastro); 3) revisão geral + correção em lote;
  4) servidor de teste (subdomínio, noindex) com amigos; 5) Sprint 8 (importador, Opus) **só se pedirem**; 6) Sprint 9.
- **Antes de abrir ao público:** VPS, domínio, HTTPS, backup testado, SEO; `ADMIN_CODIGO_EMAIL` ligado e `ADMIN_URL`
  longa só no .env do servidor; `S3_BUCKET_PRIVADO`; SMTP; apagar dados demo; advogado (termos, política, termo do
  Guia, convite; fatura após 5 anos); CNPJ e contador; INPI; lojas fundadoras; `ManifestStaticFilesStorage`.
- **Pendências:** aviso por e-mail de Termos/Política novos; relatório mensal ao patrocinador (V2); nome da aba do
  guia (padrão "Guia de Negócios", editável); limite de pausa automática por denúncias (abuso por concorrente).
- **Pela metade:** nada.
- **Último teste que passou:** `pytest -n auto -q core contas anunciantes busca moderacao` → 516 passed, 1 skipped
  (+ login: 23 passed). Suíte completa antes dos ajustes: 931 passed.
