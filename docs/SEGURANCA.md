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
- [x] Confirmação de e-mail no cadastro (link assinado, 48 h, uso único); reset de senha com token
      de uso único (2 h), que encerra as outras sessões; reset público só para clientes (equipe:
      `changepassword`). Testes: `anunciantes/tests/test_confirmacao.py`, `contas/tests/test_senha.py`

### Autorização
- [x] Ações sensíveis do titular (baixar os dados, excluir a conta) pedem a senha de novo, com 10 tentativas/hora
      por IP; a exclusão pede ainda a palavra EXCLUIR. Redirecionamento depois do aceite só para o próprio site.
- [ ] Toda queryset do painel do anunciante filtrada pelo dono (`anunciante=request.user.anunciante`)
- [ ] IDs públicos de anúncio não sequenciais na URL (`slug-curto` ou hashid) para evitar varredura
- [ ] Teste automatizado: anunciante A **não** edita, vê rascunho ou apaga anúncio de B

### Entrada de dados
- [ ] Formulários Django para tudo (validação no servidor, nunca só no JS)
- [ ] CSRF ativo em todas as views (inclusive HTMX — enviar header `X-CSRFToken`)
- [ ] Sem `|safe` / `mark_safe` em conteúdo do usuário; descrição do anúncio é texto puro
- [ ] **Uploads** (*feito para identidade do site e logo/capa das lojas*, `core/imagens.py`; *falta*: fotos de anúncio, Sprint 3):
      validar com Pillow (abre e re-salva), checar tamanho, renomear com UUID,
      **remover EXIF**, nunca servir o arquivo original, storage sem execução
- [x] Validação de CNPJ (dígitos verificadores) e de formato de CRECI (`anunciantes/validators.py`, Sprint 1)

### Cabeçalhos e navegador
- [ ] `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` (começar com 1 dia, subir para 1 ano)
- [x] CSP com `django-csp` 4.0 (Sprint 3B; `CONTENT_SECURITY_POLICY` no settings, `csp.middleware.CSPMiddleware`):
  `default-src`/`script-src`/`style-src`/`font-src`/`connect-src` só `'self'`, **sem `'unsafe-inline'`**;
  `img-src 'self' data: blob: https://tile.openstreetmap.org` (+ o domínio da mídia em produção, se for outro);
  `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.
  Regra para templates: nenhum `<script>` inline (dados vão por `json_script`/JSON-LD), nenhum `style=""`/`<style>`
  e nenhum `onclick=`: tudo em `static/`. O teste `core/tests/test_csp.py` varre as páginas públicas, do painel
  e do admin. Leaflet e Bootstrap são servidos do próprio site (sem CDN). Pendente: liberar o domínio do Mercado
  Pago na Sprint 6. Exceções conhecidas: as páginas de erro do Django em DEBUG e um `style` no histórico do
  django-simple-history (só perdem o estilo; nada de script).
- [ ] `X_FRAME_OPTIONS = "DENY"`, `SECURE_CONTENT_TYPE_NOSNIFF`, `Referrer-Policy: strict-origin-when-cross-origin`

### Abuso
- [ ] Rate limit no Nginx (`limit_req`) para login, cadastro, denúncia e busca. *Já na aplicação:*
      limite por IP no cadastro, no "esqueci minha senha" e no reenvio de confirmação (cache Redis,
      IP só como hash), campo-armadilha (honeypot) no cadastro, sem captcha de terceiros.
      Denúncia de anúncio (Sprint 7B parte 2): honeypot (robô vê sucesso e nada é gravado), limite de
      `Configuracao.denuncias_por_dia` por visitante (resumo do dia com sal aleatório, sem IP), a mesma
      origem não repete denúncia do mesmo anúncio no dia; X denúncias de golpe de origens diferentes
      tiram o anúncio do ar "em revisão" (o anunciante não reativa) até a equipe decidir.
      Aceite do Guia de Negócios (`/guia/aceite/<token>/`): token de 32 bytes, uso único e com validade
      (nunca o id), `noindex`, `Referrer-Policy: no-referrer`, sem cache, CSRF, campo-armadilha, limite por
      visitante por hora (`ConfiguracaoGuia`, IP só como resumo); usado, vencido ou inexistente dão a mesma
      resposta sem dados. Convite de WhatsApp montado no servidor e enviado um a um pela equipe.
- [ ] reCAPTCHA **não**. Hoje sem captcha nenhum (honeypot + limites); se o abuso aparecer, Cloudflare
      Turnstile só no cadastro e na denúncia
- [ ] Telefone/WhatsApp do anunciante não aparece em texto no HTML (redirect contado)
- [x] Guia de Negócios (G3): "Esta é minha empresa" (`/guia/pedido/<slug>/`) com CSRF, campo-armadilha (robô vê
      sucesso e nada é gravado), limite por visitante por hora (`ConfiguracaoGuia.pedidos_por_hora`, IP só como
      resumo) e `noindex`; o aviso à equipe não leva o contato. Lista de convites sem página pública, convite um
      a um (nada em massa) e "não contatar" bloqueando também o link de aceite. CSV exportado (perfis e
      estatísticas) com células neutralizadas (= + - @ ganham apóstrofo) e sem documento nem contato do
      responsável. Importação de CSV: até 1 MB e 2.000 linhas, prévia sem gravar, arquivo não fica no servidor.
- [x] Guia de Negócios (G2): WhatsApp e telefone fora do HTML (também fora do schema.org); WhatsApp por
      `/guia/contato/<id>/whatsapp/` (302 ao wa.me) e "Ver telefone" por HTMX ou página própria, ambos
      `noindex`, sem cache, `rel=nofollow`, contados uma vez por visitante por dia (sem IP nem cookie; robô e
      equipe não contam) e com limite por visitante por hora (`ConfiguracaoGuia.contatos_por_hora`, IP só
      como resumo). Perfil fora do ar dá 404 em tudo. Popup do mapa montado com `textContent` (sem HTML)

### Pagamentos
- [x] Link público da fatura de publicidade `/fatura/<token>/`: token de 32 bytes do `secrets` (nunca id nem código),
      URL só aceita o formato do token, `noindex`, `Referrer-Policy: no-referrer`, sem cache, fora do sitemap, só o
      necessário na página (paga: só "Fatura paga"), envio de comprovante com os mesmos limites e 10 tentativas/hora
      por IP.
- [x] Clique da publicidade: destino só do banco (pelo id da peça) e só http/https: sem redirecionamento aberto.
- [x] V1 (Sprint 6) sem gateway: Pix estático gerado no servidor, sem chave de API; nada de cartão.
- [x] Comprovantes em armazenamento **privado** (fora da mídia pública), entregues só ao dono da fatura
      ou à equipe com permissão; imagem regravada sem EXIF, PDF sem conteúdo ativo; resposta com
      `Content-Security-Policy: sandbox`, `nosniff` e sem cache. Pagamento só é confirmado por pessoa.
- V2 (gateway Mercado Pago):
- [ ] **Nenhum dado de cartão passa pelo nosso servidor** (checkout do Mercado Pago)
- [ ] Webhook: validar header `x-signature` com a chave secreta; rejeitar se inválido
- [ ] Webhook idempotente: guardar `id` do evento; processar uma vez só
- [ ] Nunca confiar no corpo do webhook: **consultar o pagamento na API** antes de liberar plano

## 2. Segredos
- [ ] `.env` fora do Git (`.gitignore`); `.env.example` sem valores reais
- [ ] `SECRET_KEY`, senhas do banco e tokens do Mercado Pago diferentes em dev e produção
- [ ] Access token de produção do Mercado Pago **só** no servidor
- [ ] `pre-commit` com `detect-secrets` ou `gitleaks`
- [ ] `GUIA_CPF_CHAVE` (chave do HMAC do CPF do guia) só no `.env`; obrigatória em produção (sem ela o
      cadastro de CPF falha). Trocar a chave invalida os resumos já gravados (perde a detecção de duplicidade)

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
