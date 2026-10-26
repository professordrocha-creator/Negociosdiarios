# Progresso (checkpoint)

**Em andamento:** Lote 3 (A, B e C) CONCLUÍDO, aguardando conferência e commit do Daniel.

**Feito 3C:** "Painel de hoje" na home do admin (core.services.pendencias_da_equipe = cartões com urgência;
fazer_agora = 5 mais antigos com Aprovar); menu enxuto por grupo (config/menu_admin.py; "Mais opções" só para
Administrador/superusuário; AdminSiteND.get_app_list/index/aprovar_agora); filtro "tipo" em Cadastros
aguardando; renovação única por dias de vigência (planos.services.fim_da_vigencia); e-mail único na aprovação
de loja nova (templates/emails/loja_aprovada_plano_ativo.txt). Docs: MANUAL_ADMIN ("Minha rotina de todo dia"),
ARQUITETURA, RUNBOOK, CHANGELOG.

**Testes:** core/tests/test_painel_hoje.py (18), +2 em pagamentos/tests/test_pedido_pix.py; ajustes em
test_lote_admin, test_cobranca, planos/test_regras.

**Falta:** nada do lote 3. Próximo: a definir pelo Daniel.

**Último comando que passou:** `pytest -n auto core pagamentos planos anunciantes contas` → 623 passed; ruff limpo;
makemigrations --check sem mudanças. Suíte completa: 1148 passed + 1 do guia corrigido
(`pytest guia/tests/test_captacao.py` → 12 passed).
