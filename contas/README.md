# App `contas`

**Responsabilidade:** contas de acesso ao sistema (anunciantes e equipe), com
login por e-mail. Visitantes não têm conta.

**Modelos:**
- `Usuario` (`AUTH_USER_MODEL = "contas.Usuario"`): `email` (login, único, sempre
  em minúsculas), `nome`, `is_active`, `is_staff`, `is_superuser`, grupos,
  `last_login`, `criado_em`. Sem `username`, `first_name` ou `last_name`.
  Senhas em hash **Argon2**.

**Serviços (`services.py`):**
- `normalizar_email(email)`: tira espaços e passa para minúsculas. Usado na
  criação, no `save()` e no login, para que "Joao@X.com" e "joao@x.com" sejam a mesma conta.

**Admin:** `UsuarioAdmin`, adaptado do admin de usuários do Django (busca por
e-mail e nome, filtro por equipe, grupos).

**Próximos passos (Sprint 1):** cadastro e confirmação de e-mail, recuperação de
senha, exclusão e anonimização pela LGPD. O 2FA da equipe entra na etapa 5 da Sprint 0.
