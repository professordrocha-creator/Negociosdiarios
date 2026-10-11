# App `contas`

**Responsabilidade:** contas de acesso ao sistema (anunciantes e equipe), com
login por e-mail. Visitantes não têm conta.

**Modelos:**
- `Usuario` (`AUTH_USER_MODEL = "contas.Usuario"`): `email` (login, único, sempre
  em minúsculas), `nome`, `is_active`, `is_staff`, `is_superuser`, grupos,
  `last_login`, `criado_em`. Sem `username`, `first_name` ou `last_name`.
  Senhas em hash **Argon2**. `demo` marca as contas fictícias do `criar_dados_demo`.

**Serviços (`services.py`):**
- `normalizar_email(email)`: tira espaços e passa para minúsculas. Usado na
  criação, no `save()` e no login, para que "Joao@X.com" e "joao@x.com" sejam a mesma conta.
- `usuario_para_axes(request, credentials)`: e-mail normalizado como "usuário" do
  django-axes (maiúsculas não dão tentativas extras; `axes_reset_username` acha sempre).
- Acesso ao admin (navegador novo, quando `ADMIN_CODIGO_EMAIL` está ligado; padrão: ligado):
  `codigo_admin_exigido()`, `acesso_verificado(request)`, `marcar_acesso_verificado(request)`,
  `enviar_codigo_email(usuario)` (6 dígitos, 10 min, uso único, 1 min entre envios),
  `verificar_codigo(usuario, codigo)` (código do e-mail ou de emergência),
  `gravar_navegador_confiavel(resposta, usuario)` e `navegador_confiavel(request, usuario)`
  (cookie assinado de 30 dias, inválido ao trocar a senha), `mascarar_email(email)`.
- `redefinir_acesso(usuario)`: emergência; desbloqueia o login e gera um código de
  emergência de uso único.

**Grupos:** Administrador, Moderador, Financeiro e Comercial, criados pela migration de
dados `0002_grupos_permissao` (ver `docs/ADMINISTRACAO.md`).

**Admin:** `UsuarioAdmin`, adaptado do admin de usuários do Django (busca por
e-mail e nome, filtro por equipe, grupos). Quem não é superusuário não liga
`is_superuser`, não dá permissões avulsas e não edita a conta do superusuário.
O site do admin (`config/admin_site.py`) faz o login com e-mail e senha e, quando
exigido, a tela "Confirme que é você" (`admin/verificar_acesso.html`, formulário
`CodigoAcessoForm` em `forms.py`).

**Comandos** (procedimentos completos em `docs/RUNBOOK.md`):
```bash
docker compose exec web python manage.py redefinir_acesso <email>     # emergência
docker compose exec web python manage.py axes_reset_username <email>  # desbloquear (do django-axes)
```

**Próximos passos (Sprint 1):** cadastro e confirmação de e-mail, recuperação de
senha, exclusão e anonimização pela LGPD.
