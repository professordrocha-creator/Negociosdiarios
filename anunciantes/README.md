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
- `criar_anunciantes_demo(lojas, senha)` / `apagar_anunciantes_demo()`: chamados pelo
  `criar_dados_demo` / `apagar_dados_demo` do core.

**Cadastro e confirmação:** `cadastrar_anunciante(dados)` (conta + loja pendente + aceites, e-mails
"confirme" e "recebemos"), `link_confirmacao`/`confirmar_email(token)` (assinado, 48 h, uso único;
avisa a equipe), `reenviar_confirmacao(email)`, `destinatarios_equipe()`. `aprovar` exige e-mail
confirmado e manda "Sua loja foi aprovada"; `suspender` manda "Sua loja foi suspensa" com o motivo.
Formulário `CadastroForm` com campo-armadilha `site_empresa` (honeypot).

**Cidades não atendidas:** o cadastro aceita qualquer cidade de estado liberado; se a cidade não é
atendida, cria `SolicitacaoCidade` (pendente). `liberar_cidade_da_solicitacao` libera a cidade e atende
todos os pedidos dela; `recusar_solicitacao` exige motivo e manda e-mail. `aprovar` exige cidade liberada.

**Página da loja (Sprint 2):** `PaginaLojaForm` (dados públicos + logo/capa validados em `core/imagens.py`),
`processar_imagem_loja(anunciante, tipo)` (tarefa Celery `tasks.processar_imagem_loja`: WebP nos tamanhos
do TELAS, sem EXIF, apaga o original e as versões antigas), `lojas_visiveis()`, `loja_para_vitrine()`,
`lojas_verificadas()` (home), `listar_lojas(tipo, cidade)`, `gerar_imagens_demo()`.

**Telas:** `/painel/loja/`, `/loja/<slug>/` (+ `/whatsapp/`), `/lojas/`, `/cadastro/`, `/cadastro/obrigado/`, `/cadastro/confirmar/<token>/` (e `.../reenviar/`), `/painel/` (`views.painel`, protegido por `anunciante_ativo`: o anunciante vem sempre
de `request.user.anunciante`, nunca da URL). Login do cliente em `/entrar/` (app `contas`).

**Admin:** lista com filtro por status/tipo/demo; status e motivo só mudam pelas ações
"Aprovar" (motivo opcional) e "Suspender" (motivo obrigatório), com tela intermediária;
ninguém apaga anunciante. Permissões dos grupos na migration `0002_permissoes_grupos`.
