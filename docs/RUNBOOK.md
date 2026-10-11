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

| Onde | O que pede |
|---|---|
| Dev (`DJANGO_DEBUG=True`) | E-mail e senha. |
| Produção com `ADMIN_CODIGO_EMAIL=False` (até a etapa 6) | E-mail e senha. |
| Produção com `ADMIN_CODIGO_EMAIL=True` (depois da etapa 6) | E-mail e senha. Em **navegador novo**, uma segunda tela pede o **código de 6 dígitos** enviado ao e-mail (vale 10 minutos, uma vez só). Acertou: aquele navegador fica **confiável por 30 dias** e não pede código de novo. |

Trocar a senha invalida todos os navegadores confiáveis (todos voltam a pedir código).

Os comandos abaixo são para dev. No servidor, os mesmos comandos rodam com o
compose de produção (etapa 8): `docker compose -f docker-compose.prod.yml exec web python manage.py ...`.

### 1. Primeiro acesso
```bash
docker compose exec web python manage.py createsuperuser
```
Abra o admin e entre com o e-mail e a senha. Em produção com código ligado, confira o
e-mail, digite o código na tela "Confirme que é você" e pronto.

### 2. O código não chegou
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
