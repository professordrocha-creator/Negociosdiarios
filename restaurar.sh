#!/usr/bin/env bash
# =====================================================================================================
# restaurar.sh — restauração GUIADA de um backup feito pelo backup.sh (docs/DEPLOY.md, "Restauração").
#
# ATENÇÃO: substitui o banco atual (e, se escolhido, a mídia) pelo conteúdo do backup. O que foi gravado
# depois do backup se perde. Antes de restaurar, este script faz um backup de segurança do estado atual.
#
# Uso: ./restaurar.sh                     (mostra os backups e pergunta qual)
#      ./restaurar.sh 2026-10-18_0300     (restaura essa pasta, ainda pedindo confirmação)
# =====================================================================================================
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)
BASE="${BACKUP_DIR:-/opt/backups/negocios-diarios}"
PROJETO="negocios-diarios-prod"

echo "Backups disponíveis em $BASE:"
ls -1 "$BASE"
ESCOLHA="${1:-}"
if [[ -z "$ESCOLHA" ]]; then
  read -r -p "Qual pasta restaurar? " ESCOLHA
fi
PASTA="$BASE/$ESCOLHA"
[[ -f "$PASTA/banco.sql.gz" ]] || { echo "Não achei $PASTA/banco.sql.gz"; exit 1; }
gzip -t "$PASTA/banco.sql.gz"

echo ""
echo "Vai SUBSTITUIR o banco atual pelo backup $ESCOLHA."
read -r -p "Para confirmar, digite RESTAURAR: " CONFIRMA
[[ "$CONFIRMA" == "RESTAURAR" ]] || { echo "Cancelado. Nada mudou."; exit 1; }
read -r -p "Restaurar também a mídia e os arquivos privados? (s/N) " MIDIA

echo "== Backup de segurança do estado atual (antes de apagar)"
./backup.sh

echo "== Parando o site (web, worker, beat) para ninguém gravar durante a restauração"
"${COMPOSE[@]}" stop web worker beat

echo "== Recriando o banco e carregando o backup"
"${COMPOSE[@]}" exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
gunzip -c "$PASTA/banco.sql.gz" | "${COMPOSE[@]}" exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

if [[ "${MIDIA,,}" == "s" ]]; then
  for volume in media privado; do
    if [[ -f "$PASTA/${volume}.tar.gz" ]]; then
      echo "== Restaurando o volume $volume"
      docker run --rm -v "${PROJETO}_${volume}:/dados" -v "$PASTA:/entrada:ro" alpine:3.20 \
        sh -c "find /dados -mindepth 1 -delete && tar -xzf /entrada/${volume}.tar.gz -C /dados && chown -R 1000:1000 /dados"
    fi
  done
fi

echo "== Subindo de novo"
"${COMPOSE[@]}" up -d --no-build
"${COMPOSE[@]}" exec -T web python manage.py migrate --noinput
# Por garantia: o nd_nginx volta a procurar o web recriado (evita o 502 depois de restaurar).
"${COMPOSE[@]}" restart nginx
"${COMPOSE[@]}" ps
echo "Restauração concluída a partir de $ESCOLHA."
