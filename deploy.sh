#!/usr/bin/env bash
# =====================================================================================================
# deploy.sh — atualiza o Negócios Diários no servidor (docs/DEPLOY.md, "Rotina de atualização").
#
# O que faz, em ordem (para no primeiro erro):
#   1. confere que está na branch main e sem alterações locais;
#   2. guarda o commit atual (para voltar, se precisar) e faz backup do banco (backup.sh);
#   3. git pull --ff-only (só avança; nunca mistura histórico);
#   4. build da imagem, up -d, migrate e collectstatic;
#   5. checa a saúde (/saude/ pelo nd_nginx) e mostra o status e os últimos logs.
# Se algo falhar, mostra como voltar à versão anterior.
#
# Uso (na pasta do projeto, no servidor):  ./deploy.sh
# =====================================================================================================
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)
ANTERIOR=""

falhou() {
  # Chamado em qualquer erro: explica como voltar ao commit anterior.
  echo ""
  echo "ERRO: o deploy parou. Nada mais foi feito depois deste ponto."
  if [[ -n "$ANTERIOR" ]]; then
    echo "Para voltar à versão anterior (commit $ANTERIOR):"
    echo "  git checkout $ANTERIOR && ${COMPOSE[*]} build web && ${COMPOSE[*]} up -d --no-build"
    echo "  (depois volte para a main com: git checkout main)"
    echo "Se a migration já tinha rodado e o banco precisa voltar: ./restaurar.sh (use o backup de agora há pouco)."
  fi
  echo "Logs: ${COMPOSE[*]} logs --tail 100 web"
}
trap falhou ERR

echo "== 1/6 Conferindo o repositório"
[[ -f .env.prod ]] || { echo "Falta o .env.prod (copie de .env.prod.example). Veja docs/DEPLOY.md."; exit 1; }
RAMO="$(git rev-parse --abbrev-ref HEAD)"
[[ "$RAMO" == "main" ]] || { echo "Está na branch '$RAMO'. Rode: git checkout main"; exit 1; }
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Há alterações locais (o servidor não deve ter edições). Veja: git status"
  exit 1
fi
ANTERIOR="$(git rev-parse --short HEAD)"
echo "Versão atual: $ANTERIOR (guardada para voltar, se precisar)"

echo "== 2/6 Backup do banco antes de atualizar"
if "${COMPOSE[@]}" ps --status running db | grep -q db; then
  ./backup.sh
else
  echo "Banco ainda não está rodando (primeira subida?): sem backup agora."
fi

echo "== 3/6 Baixando a versão nova (git pull --ff-only)"
git pull --ff-only
echo "Versão nova: $(git rev-parse --short HEAD)"

echo "== 4/6 Construindo e subindo"
"${COMPOSE[@]}" build web
"${COMPOSE[@]}" up -d --no-build --remove-orphans

echo "== 5/6 Migrations e arquivos estáticos"
"${COMPOSE[@]}" exec -T web python manage.py migrate --noinput
"${COMPOSE[@]}" exec -T web python manage.py collectstatic --noinput --clear

echo "== 6/6 Checagem de saúde"
SAUDE="falhou"
for _ in $(seq 1 20); do
  if "${COMPOSE[@]}" exec -T web python deploy/saude.py && \
     docker exec nd_nginx wget -qO- http://127.0.0.1/nginx-saude >/dev/null 2>&1; then
    SAUDE="ok"
    break
  fi
  sleep 3
done
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail 30 web worker beat
if [[ "$SAUDE" != "ok" ]]; then
  echo "A checagem de saúde não passou."
  false  # dispara o trap: mostra como voltar
fi
echo ""
echo "Deploy concluído: $ANTERIOR -> $(git rev-parse --short HEAD)."
