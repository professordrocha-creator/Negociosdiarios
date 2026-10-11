# App `anunciantes`

**Responsabilidade:** as lojas (corretores com CRECI e empresas com CNPJ), a verificação
delas no admin e o painel do anunciante. A vitrine pública `/loja/<slug>/` chega na Sprint 2.

**Modelos:**
- `Anunciante` (1:1 com `contas.Usuario`): `tipo`, `nome_publico`, `slug`, `sigla`, `cor` (1 a 6),
  `documento_tipo` + `documento_numero` (corretor autônomo = CRECI; demais = CNPJ; único),
  `whatsapp` (E.164), `email_publico`, `cidade` (só liberada), `status` (pendente | ativo |
  suspenso), `motivo_status`, `demo` (MarcaDemo) e histórico (`HistoricalAnunciante`,
  django-simple-history: quem mudou, quando e por quê).

**Validação (`validators.py`, funções puras):** `normalizar_cnpj` (14 dígitos + dígitos
verificadores), `normalizar_creci` (`CRECI/UF 12345-F`, sufixo F ou J), `normalizar_whatsapp`
(E.164). O `clean()` do modelo usa as três e confere documento x tipo e cidade liberada.

**Serviços (`services.py`):**
- `motivo_sem_painel(usuario)`: por que não pode usar o painel (anônimo, equipe, sem loja,
  pendente, suspenso) ou `None`. Usado no login (`contas.forms.EntrarForm`) e no painel.
- `aprovar(anunciante, por, motivo)` / `suspender(anunciante, por, motivo)` (motivo obrigatório):
  mudam o status e registram motivo e autor no histórico.
- `anuncios_da_loja(anunciante)`: anúncios do painel (só lojas demo, do demo.json, até a Sprint 3).
- `plano_de_exemplo()`: plano mostrado no resumo do painel até existir assinatura (Sprint 2).
- `criar_anunciantes_demo(lojas, senha)` / `apagar_anunciantes_demo()`: chamados pelo
  `criar_dados_demo` / `apagar_dados_demo` do core.

**Telas:** `/painel/` (`views.painel`, protegido por `anunciante_ativo`: o anunciante vem sempre
de `request.user.anunciante`, nunca da URL). Login do cliente em `/entrar/` (app `contas`).

**Admin:** lista com filtro por status/tipo/demo; status e motivo só mudam pelas ações
"Aprovar" (motivo opcional) e "Suspender" (motivo obrigatório), com tela intermediária;
ninguém apaga anunciante. Permissões dos grupos na migration `0002_permissoes_grupos`.
