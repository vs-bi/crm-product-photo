#!/usr/bin/env bash
# Redeploy po pushu do main — używany przez GitHub Actions (self-hosted runner na vs-web).
# Wymaga pierwszego wdrożenia: /opt/crm_product_photo/.env, git clone w /opt/.../repo (opcjonalnie).
set -euo pipefail

OPT_DIR="/opt/crm_product_photo"
REPO_DIR="${GITHUB_WORKSPACE:-${OPT_DIR}/repo}"

[[ -f "${OPT_DIR}/.env" ]] || { echo "Brak ${OPT_DIR}/.env" >&2; exit 1; }
[[ -d "${REPO_DIR}" ]] || { echo "Brak katalogu ${REPO_DIR}" >&2; exit 1; }

if [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  [[ -d "${REPO_DIR}/.git" ]] || { echo "Brak ${REPO_DIR}/.git" >&2; exit 1; }
fi

cd "${REPO_DIR}"

if [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  git fetch origin main
  git reset --hard origin/main
fi

docker compose build
docker stop crm_product_photo 2>/dev/null || true
docker rm crm_product_photo 2>/dev/null || true
docker compose up -d --force-recreate

HTTP_CODE="000"
for _ in $(seq 1 20); do
  HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8502/product_photos/ || true)"
  [[ "${HTTP_CODE}" == "200" ]] && break
  sleep 3
done
echo "HTTP ${HTTP_CODE}"
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "Oczekiwano HTTP 200 po redeploy." >&2
  docker compose logs --tail=30 >&2
  exit 1
fi

docker ps --filter name=crm_product_photo
