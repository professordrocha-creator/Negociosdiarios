# Segurança — Negócios Diários

Checklist vivo. Cada item marcado deve ter teste ou configuração verificável.
Referência: OWASP Top 10 e "Deployment checklist" do Django
(`python manage.py check --deploy` deve passar sem avisos em produção).

## 1. Aplicação (Django)

### Autenticação e contas
- [ ] Login por e-mail; senhas com **Argon2** (`argon2-cffi`) e validadores de força
- [x] **Segundo fator** para equipe/admin. **Decisão de 2026-10-11:** em vez de app
      autenticador (TOTP), considerado complicado, o admin usa e-mail + senha e, em
      **navegador novo**, um código de 6 dígitos por e-mail (`django-otp`/`otp_email`:
      10 min, uso único, espera progressiva após erros, 1 min entre envios). Acertando,
      o navegador fica confiável por 30 dias (cookie assinado, HttpOnly, Secure, SameSite=Lax,
      só no caminho do admin, ligado ao usuário e invalidado ao trocar a senha).
      Ligado por padrão em todos os ambientes (`ADMIN_CODIGO_EMAIL=True`; em dev o e-mail cai
      no Mailpit). Desligar só em dev, se quiser; **em produção nunca**. O e-mail sai pela fila
      do Celery (etapa 6). Teste: `contas/tests/test_acesso_admin.py`.
      Risco que permanece: quem invadir o e-mail da equipe passa no código (por isso o
      e-mail precisa de senha forte e 2FA no provedor).
      Para anunciantes: opcional (Sprint 1)
- [x] Bloqueio por tentativas de login (`django-axes`): 5 erros (mesmo e-mail + IP) → 1 hora
      bloqueado. Teste: `contas/tests/test_bloqueio.py`. *Pendente:* espera progressiva
      (hoje é fixa) e, na etapa 8, ler o IP real do `X-Forwarded-For` atrás do Nginx
- [x] Admin do Django em URL não óbvia (`ADMIN_URL` no `.env`, `/admin/` = 404); link no
      rodapé só em dev ou para a equipe logada
- [x] Grupos sem caminho para virar superusuário (`is_superuser` só leitura para não superusuário)
- [ ] Sessão: `SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE=Lax`, expira em 2 semanas
- [ ] Confirmação de e-mail no cadastro; reset de senha com token de uso único

### Autorização
- [ ] Toda queryset do painel do anunciante filtrada pelo dono (`anunciante=request.user.anunciante`)
- [ ] IDs públicos de anúncio não sequenciais na URL (`slug-curto` ou hashid) para evitar varredura
- [ ] Teste automatizado: anunciante A **não** edita, vê rascunho ou apaga anúncio de B

### Entrada de dados
- [ ] Formulários Django para tudo (validação no servidor, nunca só no JS)
- [ ] CSRF ativo em todas as views (inclusive HTMX — enviar header `X-CSRFToken`)
- [ ] Sem `|safe` / `mark_safe` em conteúdo do usuário; descrição do anúncio é texto puro
- [ ] **Uploads:** validar com Pillow (abre e re-salva), checar tamanho, renomear com UUID,
      **remover EXIF**, nunca servir o arquivo original, storage sem execução
- [ ] Validação de CNPJ (dígitos verificadores) e de formato de CRECI

### Cabeçalhos e navegador
- [ ] `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` (começar com 1 dia, subir para 1 ano)
- [ ] CSP com `django-csp` (liberar só tiles do OpenStreetMap e o domínio do Mercado Pago)
- [ ] `X_FRAME_OPTIONS = "DENY"`, `SECURE_CONTENT_TYPE_NOSNIFF`, `Referrer-Policy: strict-origin-when-cross-origin`

### Abuso
- [ ] Rate limit no Nginx (`limit_req`) para login, cadastro, denúncia e busca
- [ ] reCAPTCHA **não**: usar Cloudflare Turnstile ou hCaptcha só no cadastro e denúncia
- [ ] Telefone/WhatsApp do anunciante não aparece em texto no HTML (redirect contado)

### Pagamentos
- [ ] **Nenhum dado de cartão passa pelo nosso servidor** (checkout do Mercado Pago)
- [ ] Webhook: validar header `x-signature` com a chave secreta; rejeitar se inválido
- [ ] Webhook idempotente: guardar `id` do evento; processar uma vez só
- [ ] Nunca confiar no corpo do webhook: **consultar o pagamento na API** antes de liberar plano

## 2. Segredos
- [ ] `.env` fora do Git (`.gitignore`); `.env.example` sem valores reais
- [ ] `SECRET_KEY`, senhas do banco e tokens do Mercado Pago diferentes em dev e produção
- [ ] Access token de produção do Mercado Pago **só** no servidor
- [ ] `pre-commit` com `detect-secrets` ou `gitleaks`

## 3. Infraestrutura (VPS)
- [ ] Acesso SSH só por chave; `PasswordAuthentication no`; root sem login
- [ ] Firewall (`ufw`): só 22, 80, 443 abertas
- [ ] `fail2ban` no SSH
- [ ] Atualizações automáticas de segurança (`unattended-upgrades`)
- [ ] Postgres e Redis **sem** porta publicada; Redis com senha
- [ ] Containers com usuário não-root, imagens com versão fixa (nada de `:latest`)
- [ ] TLS com Let's Encrypt (renovação automática)

## 4. Backups e recuperação
- [ ] `pg_dump` diário + mídia, **criptografados** (restic ou borg), enviados para fora do VPS
- [ ] Retenção: 7 diários, 4 semanais, 6 mensais
- [ ] **Teste de restauração mensal** documentado (backup que nunca foi restaurado não é backup)

## 5. Monitoramento
- [ ] Sentry (ou GlitchTip self-hosted) com `send_default_pii=False`
- [ ] Uptime monitor externo (UptimeRobot / Better Stack) no `/saude/`
- [ ] Logs em JSON, sem CPF/telefone/e-mail; IP truncado
- [ ] `pip-audit` e Dependabot/Renovate semanal

## 6. Resposta a incidentes
Ver `docs/LGPD.md` §7 — prazo legal de comunicação à ANPD.
