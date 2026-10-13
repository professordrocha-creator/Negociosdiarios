# App `privacidade`

**Responsabilidade:** LGPD (Sprint 7B; docs/LGPD.md): Termos de Uso e Política de Privacidade com versão e aceite,
cookies (só essenciais, sem banner), "Meus dados" do anunciante (baixar e excluir) e os pedidos dos titulares.

**Modelos:** `DocumentoLegal` (tipo, versão, vigência, "o que mudou", texto, publicado, revisão jurídica pendente;
histórico; em vigor = texto travado) e `PedidoTitular` (conta ou contato, tipo, origem, situação, prazo, resposta;
histórico). O aceite é o `contas.AceiteDocumento` (usuário, documento, versão, data e hora).

**Serviços (`services.py`):** `documento_vigente`, `documentos_vigentes`, `pendencias_de_aceite`, `registrar_aceites`,
`blocos_do_texto` (texto do admin → blocos escapados), `COOKIES` (lista única dos cookies; um teste confere),
`exportar_dados`/`exportar_json`, `faturas_em_aberto`, `anonimizar_conta`, `registrar_pedido`, `responder_pedido`,
`limpar_dados_vencidos` (tarefa diária às 4h: guarda fiscal), `criar_pedido_demo`/`apagar_pedidos_demo`.

**Telas:** `/termos/` e `/privacidade/` (views do core chamam `views.documento`), `/painel/termos-atualizados/`,
`/painel/meus-dados/` (+ `baixar/`, `excluir/`). O decorator `anunciantes.views.anunciante_ativo` manda para o aceite
quando há versão nova (menos nas telas de Meus dados: `exigir_aceite=False`); o login (`contas.views.EntrarView`) também.

**Admin:** Privacidade › Documentos legais e Pedidos dos titulares (só o grupo Administrador).

**Testes:** `tests/test_lgpd.py`.
