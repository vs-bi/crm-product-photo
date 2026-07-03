#!/usr/bin/env bash
# Jednorazowa rejestracja self-hosted runnera GitHub Actions na vs-web.
# Uruchom na serwerze jako gcieslinski (poza katalogiem repo).
#
# 1. W GitHub: repo → Settings → Actions → Runners → New self-hosted runner → Linux
# 2. Skopiuj token z instrukcji GitHub i uruchom:
#      GITHUB_RUNNER_TOKEN=<token> bash setup-github-runner.sh
set -euo pipefail

RUNNER_NAME="${GITHUB_RUNNER_NAME:-vs-web-crm-product-photo}"
RUNNER_LABELS="${GITHUB_RUNNER_LABELS:-vs-web,linux}"
RUNNER_DIR="${HOME}/actions-runner-crm-product-photo"
REPO="https://github.com/vs-bi/crm-product-photo"

if [[ -z "${GITHUB_RUNNER_TOKEN:-}" ]]; then
  echo "Ustaw GITHUB_RUNNER_TOKEN (token z GitHub → Settings → Actions → Runners → New runner)." >&2
  exit 1
fi

mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

if [[ ! -f ./config.sh ]]; then
  curl -fsSL -o actions-runner-linux-x64.tar.gz \
    https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-linux-x64-2.321.0.tar.gz
  tar xzf actions-runner-linux-x64.tar.gz
  rm actions-runner-linux-x64.tar.gz
fi

./config.sh --url "${REPO}" --token "${GITHUB_RUNNER_TOKEN}" \
  --name "${RUNNER_NAME}" --labels "${RUNNER_LABELS}" --unattended

sudo ./svc.sh install
sudo ./svc.sh start

echo "Runner ${RUNNER_NAME} zarejestrowany (etykiety: ${RUNNER_LABELS})."
echo "Sprawdź status w GitHub → Settings → Actions → Runners."
