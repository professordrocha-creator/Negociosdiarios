# Deploy — servidor de teste (e depois produção)

Passo a passo para colocar o Negócios Diários numa VPS Ubuntu 24.04 com Docker que **já roda outros sistemas**.
Escrito para quem não é da área: siga na ordem e copie os comandos.

**Como o servidor fica:**

```
Visitante ──HTTPS──> nginx do OUTRO projeto (portas 80/443, certificado)
                         │  rede Docker "drocha_solucoes_default"
                         ▼
                    nd_nginx (nosso; /static, /media)  ──rede "nd_interna"──>  web (Django/Gunicorn)
                                                                                worker e beat (Celery)
                                                                                db (PostGIS) e redis
```

- Nosso sistema **não abre nenhuma porta** no servidor. Só o `nd_nginx` entra na rede do outro projeto.
- Por enquanto é **servidor de TESTE**: fora do Google (`SITE_NOINDEX=True`), com dados fictícios.
- Arquivos: `docker-compose.prod.yml`, `Dockerfile.prod`, `deploy/` (nginx interno e healthcheck),
  `.env.prod.example`, `deploy.sh`, `backup.sh`, `restaurar.sh`.

> Os comandos abaixo com `$` rodam no terminal do servidor (SSH). Troque `seu-usuario` pelo seu usuário.

---

## 1. Preparar o servidor

### 1.1 Usuário e pastas

1. Entre no servidor com o seu usuário (não o root). Se ele ainda não estiver no grupo do Docker:
   `$ sudo usermod -aG docker seu-usuario` e saia e entre de novo.
2. Pasta do sistema e dos backups:
   ```
   $ sudo mkdir -p /opt/negocios-diarios /opt/backups/negocios-diarios
   $ sudo chown seu-usuario: /opt/negocios-diarios /opt/backups/negocios-diarios
   $ chmod 700 /opt/backups/negocios-diarios
   ```

### 1.2 Clonar com chave só de leitura (deploy key)

1. Crie a chave do servidor: `$ ssh-keygen -t ed25519 -f ~/.ssh/nd_deploy -N "" -C "deploy negocios-diarios"`
2. Mostre a chave pública: `$ cat ~/.ssh/nd_deploy.pub` e copie.
3. No GitHub: repositório › **Settings** › **Deploy keys** › **Add deploy key**, cole e **NÃO** marque "Allow
   write access" (só leitura).
4. Diga ao SSH para usar essa chave com o GitHub:
   ```
   $ cat >> ~/.ssh/config <<'FIM'
   Host github-nd
     HostName github.com
     User git
     IdentityFile ~/.ssh/nd_deploy
     IdentitiesOnly yes
   FIM
   ```
5. Clone: `$ git clone git@github-nd:SEU-USUARIO-GITHUB/negocios-diarios.git /opt/negocios-diarios`
6. Scripts executáveis: `$ cd /opt/negocios-diarios && chmod +x deploy.sh backup.sh restaurar.sh`

### 1.3 Criar o `.env.prod`

1. `$ cp .env.prod.example .env.prod && chmod 600 .env.prod`
2. Gere os segredos (cada comando imprime um valor novo; use um para cada campo):
   ```
   $ python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY e GUIA_CPF_CHAVE
   $ python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # senhas do banco, redis, DEMO_SENHA
   $ python3 -c "import secrets; print('painel-' + secrets.token_urlsafe(24).replace('_', '-'))"  # ADMIN_URL
   ```
3. `$ nano .env.prod` e troque **todos** os `troque-...`. Atenção:
   - a senha do banco aparece duas vezes (`POSTGRES_PASSWORD` e dentro do `DATABASE_URL`), e a do redis também
     (`REDIS_PASSWORD` e `REDIS_URL`);
   - `ADMIN_URL` diferente do usado no seu PC; anote num lugar seguro;
   - preencha o SMTP de verdade: o código de acesso do admin chega por e-mail;
   - `GUIA_CPF_CHAVE` nunca mais pode mudar depois de usada.
4. Confira se a rede do outro projeto existe: `$ docker network ls | grep drocha_solucoes_default`.

### Se der errado

- "Permission denied (publickey)" no clone: a deploy key não foi adicionada ou o `~/.ssh/config` está errado.
- A rede não existe: o outro projeto precisa estar no ar (é ele que cria a rede).

---

## 2. Primeira subida

1. `$ cd /opt/negocios-diarios && ./deploy.sh`
2. O script constrói a imagem, sobe tudo, roda as migrations e o collectstatic e checa a saúde. No fim, todos os
   serviços devem aparecer "healthy" ou "running".
3. Carregue cidades e categorias (uma vez):
   ```
   $ docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py carregar_municipios
   $ docker compose -f docker-compose.prod.yml --env-file .env.prod exec web python manage.py carregar_categorias_guia
   ```
   Depois, no admin, libere as cidades atendidas ("Núcleo" › "Cidades").

Para não repetir o comando longo, crie um atalho: `$ alias ndc='docker compose -f docker-compose.prod.yml --env-file .env.prod'`
(ponha no `~/.bashrc`). Os exemplos abaixo usam `ndc`.

### Se der errado

- `deploy.sh` para com erro: leia a mensagem; ele mostra como voltar e onde ver os logs (`ndc logs --tail 100 web`).
- "network drocha_solucoes_default not found": veja o passo 1.3.4.

---

## 3. Criar o superusuário

No **seu** terminal do servidor (a senha não aparece em lugar nenhum):

```
$ ndc exec web python manage.py createsuperuser
```

Entre em `https://negociosdiarios.com.br/<ADMIN_URL>/`. O primeiro acesso pede o código por e-mail (o SMTP precisa
estar certo). Sem e-mail: `$ ndc exec web python manage.py redefinir_acesso SEU-EMAIL` mostra um código de
emergência.

---

## 4. Carregar os dados de demonstração (só no servidor de TESTE)

Só funciona com `SITE_NOINDEX=True` e `DEMO_NO_SERVIDOR=True` no `.env.prod` (o sistema recusa de outro jeito).

```
$ ndc exec web python manage.py criar_dados_demo
```

Cria lojas, anúncios com fotos, faturas, campanhas, denúncias, pedidos e o guia, tudo marcado como demonstração,
com a faixa "Dados de demonstração" no site. Os usuários demo usam a senha `DEMO_SENHA`.

---

## 5. nginx externo (do outro projeto): o bloco do domínio

No nginx que já tem as portas 80/443, acrescente (no arquivo de configuração de sites dele) os blocos abaixo e
recarregue aquele nginx. **Só o domínio do Negócios Diários**: não mexa nos outros sites.

```nginx
# Negócios Diários: HTTP só para o certbot e para mandar ao HTTPS.
server {
    listen 80;
    server_name negociosdiarios.com.br www.negociosdiarios.com.br;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://negociosdiarios.com.br$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name negociosdiarios.com.br www.negociosdiarios.com.br;

    ssl_certificate     /etc/letsencrypt/live/negociosdiarios.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/negociosdiarios.com.br/privkey.pem;

    # www → sem www (um endereço só para o Google e para os cookies).
    if ($host = www.negociosdiarios.com.br) { return 301 https://negociosdiarios.com.br$request_uri; }

    # Formulário de fotos: até 10 fotos de até 15 MB numa requisição (igual ao ND_LIMITE_UPLOAD do .env.prod).
    client_max_body_size 160m;

    location / {
        # Resolve o nome do container na hora (o nd_nginx pode ser recriado com outro IP).
        resolver 127.0.0.11 valid=30s;
        set $nd_nginx http://nd_nginx:80;
        proxy_pass $nd_nginx;

        proxy_set_header Host $host;
        # $proxy_add_x_forwarded_for ACRESCENTA o IP de quem conectou; o nd_nginx pega o último confiável.
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        # SOBRESCREVE (o visitante não consegue fingir https).
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_read_timeout 90s;
    }
}
```

Se o nginx externo roda em Docker, o caminho dos certificados e da pasta do certbot depende de como **aquele**
projeto montou os volumes: use os mesmos que os outros sites dele usam.

### Se der errado

- 502 Bad Gateway: o `nd_nginx` não está na rede (`docker network inspect drocha_solucoes_default`) ou não subiu
  (`ndc ps`).
- "Request Entity Too Large" ao mandar fotos: falta o `client_max_body_size` no nginx externo.
- Laço de redirecionamento: falta o `X-Forwarded-Proto $scheme`.

---

## 6. Certificado HTTPS (certbot)

1. Antes, o bloco da porta 80 (acima) já deve estar ativo e o DNS do domínio apontando para o IP da VPS.
2. Emita (ajuste a pasta `-w` para a que o nginx externo usa no `/.well-known/acme-challenge/`):
   ```
   $ sudo certbot certonly --webroot -w /var/www/certbot -d negociosdiarios.com.br -d www.negociosdiarios.com.br
   ```
3. Ative o bloco 443 e recarregue o nginx externo. A renovação automática do certbot já existe no servidor; teste:
   `$ sudo certbot renew --dry-run`.

---

## 7. Atualizar (rotina de deploy)

No seu PC: commit e push na `main`. No servidor:

```
$ cd /opt/negocios-diarios && ./deploy.sh
```

O script confere a branch e se não há edições no servidor, guarda o commit atual, faz **backup**, `git pull
--ff-only`, constrói, sobe, migra, coleta os estáticos e checa a saúde. No fim mostra o status e os últimos logs.

---

## 8. Voltar à versão anterior (rollback)

O `deploy.sh` mostra o commit anterior quando falha. Para voltar:

```
$ git checkout <commit-anterior>
$ ndc build web && ndc up -d --no-build
```

Se a versão nova já tinha migrado o banco e a antiga não funciona com ele, restaure o backup feito pelo deploy
(capítulo 9). Para seguir atualizando depois: `$ git checkout main`.

---

## 9. Backup e restauração

- **Manual:** `$ ./backup.sh` → `/opt/backups/negocios-diarios/AAAA-MM-DD_HHMM/` com `banco.sql.gz`,
  `media.tar.gz` e `privado.tar.gz`. Guarda 7 dias.
- **Restaurar:** `$ ./restaurar.sh` (lista os backups, pede a pasta e que você digite `RESTAURAR`; antes faz um
  backup de segurança do estado atual).
- **Teste de verdade:** uma vez por mês, restaure num servidor de teste ou numa cópia e confira o site. Backup que
  nunca foi restaurado não é backup.
- **Cópia fora da VPS:** copie `/opt/backups` para outro lugar (ex.: um bucket privado) com alguma frequência: se a
  VPS se perder, os backups vão junto.

### Backup automático (cron)

```
$ crontab -e
```
e acrescente (todo dia às 3h, horário do servidor):
```
0 3 * * * cd /opt/negocios-diarios && ./backup.sh >> /opt/backups/negocios-diarios/backup.log 2>&1
```

---

## 10. Arquivos privados

Comprovantes de pagamento e fotos de termos do guia **nunca** são servidos pelo nginx:

- `ARMAZENAMENTO=local`: ficam no volume `privado` (montado só no web/worker/beat, em `/app/privado`), fora de
  `/media`. Só saem pelas telas do sistema, que conferem quem pede.
- `ARMAZENAMENTO=s3`: vão para o bucket `S3_BUCKET_PRIVADO` (sem domínio público, URLs assinadas).
- Entram no backup (`privado.tar.gz`), que por isso fica numa pasta só do dono (`chmod 700`).

---

## 11. Segurança depois do deploy (checklist)

1. Firewall só com 22, 80 e 443 (o nosso sistema não abre nada):
   ```
   $ sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
   $ sudo ufw enable && sudo ufw status
   ```
   Atenção: portas publicadas por outros containers passam por fora do ufw (regra do Docker); confira com
   `$ docker ps --format '{{.Names}} {{.Ports}}'` que só o nginx externo publica 80/443.
2. Trabalhe com usuário comum (não root); SSH só com chave (`PasswordAuthentication no` no `/etc/ssh/sshd_config`).
3. Atualizações automáticas de segurança: `$ sudo apt install unattended-upgrades && sudo dpkg-reconfigure unattended-upgrades`.
4. `$ ndc exec web python manage.py check --deploy`: só podem aparecer os avisos W005 e W021 (HSTS de subdomínios e
   preload, desligados de propósito até o lançamento estável).
5. Teste no navegador: `https://negociosdiarios.com.br/robots.txt` deve mostrar `Disallow: /` (servidor de teste) e
   `/sitemap.xml` deve dar "não encontrado".
6. `.env.prod` com `chmod 600`; backups com `chmod 700`.
7. Monitor de uptime externo (gratuito) apontando para `https://negociosdiarios.com.br/saude/`.

---

## 12. Antes de abrir ao público (lançamento)

1. Apagar a demonstração (pede que você digite `APAGAR DEMONSTRACAO`):
   `$ ndc exec web python manage.py apagar_dados_demo`
   Só sai o que é demonstração; superusuário, contas reais e configurações ficam.
2. No `.env.prod`: `SITE_NOINDEX=False`, `DEMO_NO_SERVIDOR=False`, `MOSTRAR_DEMO=False`; depois `./deploy.sh`.
3. Advogado revisou e aprovou: Termos de Uso, Política de Privacidade, termo do Guia e convite. Publique as versões
   finais no admin e desmarque "rascunho: revisão jurídica pendente".
4. E-mail do Encarregado ("e-mail de privacidade (LGPD)") recebendo de verdade; nome do Encarregado preenchido.
5. SMTP real testado (cadastro, "esqueci minha senha", código do admin).
6. Backup automático rodando e **uma restauração testada**.
7. `ADMIN_CODIGO_EMAIL=True` e `ADMIN_URL` longa e só no `.env.prod`.
8. CNPJ e contador; busca de marca no INPI; Pix configurado (`PIX_*`).
9. Cadastrar as lojas fundadoras.
10. Depois de algumas semanas estável: `DJANGO_HSTS_SECONDS=31536000`.
