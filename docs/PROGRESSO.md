# Progresso (checkpoint)

**Em andamento:** Parte 4 CONCLUÍDA (etapas 1, 2 e 3), aguardando teste e commit do Daniel. Decisões dele na
memória parte4-decisoes.

**Etapa 1 (A+D):** fluxo único cadastro com plano → Pix → Aprovar 1 clique (lista, ficha, Painel de hoje).
**Etapa 2 (B):** topo "Entrar"/"Meu painel"/"Painel administrativo"; ficha da loja: "Link da loja no site",
"Avançado" (sigla e cor), confiança só com a situação; "Sobre esta tela" compacta e fechada no painel do cliente;
Faturas com mensagem única sem histórico; "Ações recentes" (5, repetidas juntas: core.services.acoes_recentes).
**Etapa 3 (C):** "Outro bairro" no anúncio (anuncios/forms.py OUTRO_BAIRRO, static/js/bairros.js);
core.services normalizar_nome_bairro/bairro_informado/juntar_bairros; Bairro.criado_por + criado_em e
Configuracao.bairros_novos_por_dia (migration core 0022); admin de Bairros com filtros e "Juntar". Demo com 1 bairro
criado por loja. Testes: core/tests/test_telas_parte4.py, core/tests/test_bairros_da_loja.py.

**Correção depois:** login de loja pendente com e-mail confirmado era recusado (contas/forms.py
confirm_login_allowed); agora entra e cai no Pix. Erros do login em vermelho. Teste com login de verdade.

**Falta:** Daniel conferir no navegador e fazer o(s) commit(s).

**Último comando que passou:** suíte completa da etapa 3: 1202 passed + 6 falhas de teste (campo novo da Configuração
e contagem da demo), corrigidas: `pytest -n auto core/tests/test_identidade.py core/tests/test_demo.py` → 84 passed; ruff limpo.
