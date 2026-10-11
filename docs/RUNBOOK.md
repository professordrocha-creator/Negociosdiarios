# Runbook — procedimentos

> Passo a passo para quando algo precisar ser feito (ou der errado).
> Os comandos são preenchidos na Sprint 0, quando o servidor existir.

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
