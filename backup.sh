#!/usr/bin/env bash
# =====================================================================================================
# backup.sh — cópia do banco (pg_dump compactado) e da mídia, com retenção de 7 dias (docs/DEPLOY.md).
#
# Grava em /opt/backups/negocios-diarios/AAAA-MM-DD_HHMM/:
#   banco.sql.gz   pg_dump no formato texto, compactado (restaurar.sh sabe ler)
#   media.tar.gz   volume "media" (fotos e logos públicos)
#   privado.tar.gz volume "privado" (comprovantes e fotos de termos: dados pessoais; pasta só do root)
# Apaga as pastas com mais de 7 dias. Pronto para o cron (docs/DEPLOY.md, "Backup automático").
#
# Uso: ./backup.sh            (na pasta do projeto; o deploy.sh chama sozinho antes de atualizar)
# =====================================================================================================
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)
DESTINO_BASE="${BACKUP_DIR:-/opt/backups/negocios-diarios}"
DIAS="${BACKUP_DIAS:-7}"
AGORA="$(date +%Y-%m-%d_%H%M)"
DESTINO="$DESTINO_BASE/$AGORA"

# Backups têm dados pessoais: pasta acessível só pelo dono (umask 077 = arquivos 600, pastas 700).
umask 077
mkdir -p "$DESTINO"

echo "Backup em $DESTINO"
# Banco: lê usuário e nome do próprio container (sem senha na linha de comando).
"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip -9 > "$DESTINO/banco.sql.gz"
gzip -t "$DESTINO/banco.sql.gz"   # confere que o arquivo não ficou truncado

# Volumes de arquivos, por um container descartável (só leitura).
PROJETO="negocios-diarios-prod"
for volume in media privado; do
  docker run --rm -v "${PROJETO}_${volume}:/dados:ro" -v "$DESTINO:/saida" alpine:3.20 \
    tar -czf "/saida/${volume}.tar.gz" -C /dados .
done

# Retenção: apaga as pastas de backup mais velhas que $DIAS dias.
find "$DESTINO_BASE" -mindepth 1 -maxdepth 1 -type d -mtime +"$DIAS" -print -exec rm -rf {} +

du -sh "$DESTINO"
echo "Backup concluído."
