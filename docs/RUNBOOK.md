# Runbook — procedimentos

> Passo a passo para quando algo precisar ser feito (ou der errado).
> Os comandos de servidor são preenchidos na Sprint 0, quando o servidor existir.

## Banco de dev: não apagar sem querer
- **Nunca** use `docker compose down -v` em dev, a não ser que queira **apagar o banco**:
  o `-v` remove o volume `negocios-diarios_pgdata` (usuários, cidades liberadas, tudo).
- Para parar ou reiniciar sem perder nada: `docker compose down` (sem `-v`) ou `docker compose restart`.
- O nome do projeto é fixo (`name: negocios-diarios` no `docker-compose.yml`), então o
  volume é o mesmo mesmo que a pasta mude de nome.
- Se o banco for recriado de propósito: `migrate`, `carregar_municipios`, `createsuperuser`
  e liberar as cidades no admin.

## Acesso ao admin (login, bloqueio e emergência)

O admin fica em `https://<site>/<ADMIN_URL>/` (valor no `.env`; em dev,
`http://localhost:8000/<ADMIN_URL>/`, ou o link "Admin" no rodapé). `/admin/` dá 404 de propósito.

Como o login funciona:

| `ADMIN_CODIGO_EMAIL` | O que pede |
|---|---|
| `True` (padrão; obrigatório em produção) | E-mail e senha. Em **navegador novo**, uma segunda tela pede o **código de 6 dígitos** enviado ao e-mail (vale 10 minutos, uma vez só). Acertou: aquele navegador fica **confiável por 30 dias** e não pede código de novo. Em dev o e-mail chega no **Mailpit**: http://localhost:8025 |
| `False` (só em dev, se quiser) | E-mail e senha. |

Trocar a senha invalida todos os navegadores confiáveis (todos voltam a pedir código).
O e-mail com o código sai pela fila do Celery: se o `worker` estiver parado, o código
não chega (veja "E-mails e tarefas do Celery" abaixo).

Os comandos abaixo são para dev. No servidor, os mesmos comandos rodam com o
compose de produção (etapa 8): `docker compose -f docker-compose.prod.yml exec web python manage.py ...`.

### 1. Primeiro acesso
```bash
docker compose exec web python manage.py createsuperuser
```
Abra o admin e entre com o e-mail e a senha. Na tela "Confirme que é você", pegue o
código no e-mail (em dev: http://localhost:8025) e digite. Pronto: este navegador não
pede código por 30 dias.

### 2. O código não chegou
- Em dev, olhe o Mailpit (http://localhost:8025), não a sua caixa de e-mail real.
- O `worker` está de pé? `docker compose ps` e `docker compose logs --tail=50 worker`.
- Veja a caixa de spam e espere 1 minuto; depois use **reenviar o código** (há um
  intervalo mínimo de 1 minuto entre envios).
- Vale sempre o **último** código enviado; o anterior deixa de valer.
- Depois de vários códigos errados, o sistema faz esperar alguns segundos entre
  tentativas. Aguarde e tente de novo.
- O e-mail não sai de jeito nenhum (servidor de e-mail fora do ar)? Use o
  código de emergência (item 4).

### 3. Bloqueado por senha errada (django-axes)
5 senhas erradas seguidas com o mesmo e-mail, do mesmo IP, bloqueiam o login por
**1 hora** (aparece "Acesso bloqueado temporariamente"). Quem erra de outro IP não
tranca você. Para liberar na hora:
```bash
docker compose exec web python manage.py axes_reset_username seu@email.com
```
Outras opções: esperar 1 hora; ou outra pessoa do grupo Administrador apaga a linha
em **Axes → Access attempts**. Para ver quem está bloqueado:
`docker compose exec web python manage.py axes_list_attempts`.
Esqueceu a senha? `docker compose exec web python manage.py changepassword seu@email.com`.

### 4. Emergência: sem acesso ao e-mail (ou o e-mail não sai)
Só funciona com acesso ao servidor (SSH na VPS), e é por isso que é seguro.
1. Entrar no servidor por SSH e ir para a pasta do projeto.
2. Rodar:
   ```bash
   docker compose -f docker-compose.prod.yml exec web python manage.py redefinir_acesso seu@email.com
   ```
   O comando desbloqueia o login (axes) e mostra um **código de emergência** de
   8 letras e números, de **uso único**. Rodar de novo gera outro e invalida o anterior.
3. Entrar no admin com e-mail e senha e, na tela "Confirme que é você", digitar o
   código de emergência no lugar do código do e-mail.
4. Notebook ou celular roubado, ou senha vazada? Troque a senha: isso também
   derruba todos os navegadores confiáveis.
   `... python manage.py changepassword seu@email.com`
5. Perdeu também o acesso SSH? Usar o console web do provedor da VPS para entrar no
   servidor e seguir do item 2.

## Dados de demonstração (dev)
Regra do projeto (CLAUDE.md): tudo é construído com dados fictícios até o lançamento.
1. No `.env`: `MOSTRAR_DEMO=True` e `DEMO_SENHA=<uma senha forte só para a demo>`.
   Reinicie: `docker compose up -d web`.
2. Criar/atualizar (pode rodar quantas vezes quiser):
   ```bash
   docker compose exec web python manage.py criar_dados_demo
   ```
   Libera as cidades da demonstração e cria a equipe demo (`moderador@`, `financeiro@` e
   `comercial@demo.invalid`, senha = `DEMO_SENHA`), para testar os grupos no admin.
   O código de login deles cai no Mailpit.
3. A home mostra a faixa "Dados de demonstração", destaques, recém-anunciados e lojas.
4. Apagar tudo de uma vez (pede confirmação; contas reais e cidades liberadas à mão ficam):
   ```bash
   docker compose exec web python manage.py apagar_dados_demo
   ```
Fonte única dos dados: `core/dados/demo.json` (lojas, anúncios, equipe, cidades). Cada
sprint amplia o arquivo e o comando. Na Sprint 9 os dados demo são apagados antes do lançamento.

## E-mails e tarefas do Celery

Todo e-mail do sistema vai para a fila (Redis) e o container `worker` envia. A
página nunca espera o servidor de e-mail. O worker também roda as tarefas agendadas
(beat), como a de exemplo `batimento`, a cada 5 minutos.

- **O Celery está funcionando?**
  ```bash
  docker compose exec web python manage.py testar_celery
  ```
  Deve responder "Celery funcionando: o worker executou a tarefa às ...". No log do
  worker (`docker compose logs -f worker`) aparece "Batimento do Celery" a cada 5 minutos.
- **Ver os e-mails em dev:** http://localhost:8025 (Mailpit). Nada sai para a internet.
- **E-mail não chegou:** veja `docker compose logs --tail=100 worker`. Falha de SMTP
  faz a tarefa tentar de novo 5 vezes (30 s, 1, 2, 4 e 8 min; ~15 min no total). Confira as
  variáveis `EMAIL_*` do `.env`. O log nunca mostra endereços de e-mail (LGPD).
- **Worker parado:** `docker compose up -d worker`. Os e-mails que estavam na fila
  saem quando ele voltar.
- **Produção (SMTP do provedor):** no `.env`, `EMAIL_HOST`, `EMAIL_PORT=587`,
  `EMAIL_USE_TLS=True`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` e `DEFAULT_FROM_EMAIL`
  com um remetente do domínio (SPF, DKIM e DMARC configurados, `docs/BOAS_PRATICAS.md`).
  Brevo: `smtp-relay.brevo.com`. Amazon SES: `email-smtp.<região>.amazonaws.com`.

## Mídia (fotos e arquivos enviados)
- Dev: `ARMAZENAMENTO=local`, arquivos na pasta `media/` do projeto (fora do Git).
- Produção: `ARMAZENAMENTO=s3` com as variáveis `S3_*` do Cloudflare R2 (`.env.example`).
  Decisão e detalhes: `docs/adr/0002-armazenamento-midia.md`.

## Deploy de nova versão
1. Testes verdes no GitHub Actions.
2. No servidor: `./scripts/deploy.sh` (faz backup → baixa código → build → migrate → reinicia).
3. Abrir o site e o `/saude/`. Conferir o Sentry por 10 minutos.
4. Registrar no `CHANGELOG.md`.

## Voltar para a versão anterior
1. `./scripts/deploy.sh <tag-anterior>`
2. Se a migration nova quebrou dados: restaurar o backup feito pelo deploy (abaixo).

## Restaurar backup
1. Listar backups: `restic snapshots`
2. Restaurar banco em base temporária e conferir antes de trocar a principal.
3. Testar este procedimento **todo mês** e anotar a data aqui: ____

## Site fora do ar
1. `docker compose ps`: algum container parado? `docker compose logs --tail=100 <nome>`
2. Disco cheio? `df -h` (fotos e logs são os suspeitos).
3. Certificado vencido? `sudo certbot renew`
4. VPS inteira caiu? Painel do provedor → reiniciar.

## Pagamento não confirmou
1. Ver o evento em Admin → Pagamentos → Eventos (chegou o webhook?).
2. Consultar o pagamento no painel do Mercado Pago.
3. Se pago: botão "Reprocessar evento" ou baixa manual com motivo.

## Suspeita de vazamento de dados
Seguir `docs/LGPD.md` §7. Primeiro conter, depois avaliar, depois comunicar no prazo.
