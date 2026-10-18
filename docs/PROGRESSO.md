# Progresso (checkpoint — sobrescrever, sem histórico; máx. 15 linhas)
- **Prontos, sem commit:** 7B parte 2 (denúncias, app `moderacao`) e os ajustes de layout, rodapé e login da
  equipe (grupos de opções da busca, rodapé sem "Admin", equipe entra pela Área do anunciante com a mesma
  verificação do admin, "Como denunciar", CNPJ e frase do rodapé na Configuracao).
- **Feito e no GitHub:** Sprints 0 a 6, 7A (publicidade) e 7B parte 1 (termos, cookies, Meus dados).
- **Falta, em ordem:** 1) testar no navegador (busca em 360/768/1200 px, login da equipe com e sem código,
  denúncias) e commitar; 2) Sprint 8 (importador XML ZAP/VivaReal e planilha; usar o Opus); 3) Sprint 9.
- **Sprint 9:** VPS, domínio, HTTPS e backup; ligar `ADMIN_CODIGO_EMAIL`; `S3_BUCKET_PRIVADO`; apagar os dados
  demo; advogado revisa termos e política (dúvida: fatura com valores e datas depois dos 5 anos, sem dados
  pessoais); CNPJ; busca de marca no INPI; estáticos versionados (`ManifestStaticFilesStorage`) para o navegador não usar CSS antigo. (Link do Admin no rodapé: já removido.)
- **Pendências:** e-mail de aviso de versão nova dos Termos/Política; relatório mensal ao patrocinador (V2).
- **Pela metade:** nada.
- **Último teste que passou:** `pytest -n auto -q core contas anunciantes busca moderacao` → 516 passed, 1 skipped
  (+ login: 23 passed). Suíte completa antes dos ajustes: 931 passed.
