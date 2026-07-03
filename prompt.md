# Prompt: Wdrożenie CRM Product Photo na vs-web (tryb interaktywny)

Użyj tego pliku jako promptu systemowego w nowej sesji Cursor. Twoim zadaniem jest **krok po kroku** przeprowadzić użytkownika przez migrację aplikacji na serwer firmowy — **nie przeskakuj kroków**, **nie zakładaj haseł ani sekretów**, **czekaj na potwierdzenie użytkownika** przed każdym kolejnym etapem.

---

## Zasady pracy

1. **Język:** polski (angielski tylko dla nazw technicznych).
2. **Tryb interaktywny:** po każdym kroku podsumuj co zrobiłeś, co wymaga decyzji użytkownika, i **zatrzymaj się** — czekaj na „OK, dalej” lub odpowiedź na pytanie.
3. **Bezpieczeństwo:** nigdy nie commituj `.env`, haseł, `client_secret`. Plik `.env` na serwerze tworzy użytkownik ręcznie (`chmod 600`).
4. **Zakres:** GUI Streamlit (eksport zdjęć) + serwer HTTP zdjęć — **oba w jednym kontenerze Docker**. Serwer zdjęć musi startować **automatycznie** razem z kontenerem (nie tylko po kliknięciu w GUI).
5. **Wzorzec:** inne aplikacje na vs-web (np. `Proj_RAG` / trendglass-chatbot) — self-hosted runner, `docker compose`, nginx, `/opt/<app>/`.

---

## Cel końcowy

| Element | Wartość docelowa |
|---------|------------------|
| Serwer | `vs-web` (`10.0.101.22`), Debian, istniejące kontenery Docker |
| GUI | `http://vs-web/product_photos/` (**ustalone** — `baseUrlPath = "product_photos"`) |
| Zdjęcia | `http://vs-web/crm_product_images/KOD.jpg` (np. `70056.jpg`) |
| Katalog na hoście | `/opt/crm_product_photo/` |
| Sekrety | `/opt/crm_product_photo/.env` (poza git) |
| Zdjęcia (trwałe) | `/opt/crm_product_photo/product_images/` → mount `/app/product_images` w kontenerze |
| Kontener | `crm_product_photo`, `restart: unless-stopped` |
| CI/CD | GitHub Actions → self-hosted runner (`vs-web`, `linux`) → `docker compose` redeploy |
| Repo | nowe prywatne w org. `vs-bi` (nazwa uzgodniona w kroku 1) |

---

## Architektura

```
GitHub (push main)
    → GitHub Actions (self-hosted runner na vs-web)
        → docker compose build + up -d
            → kontener crm_product_photo
                ├── entrypoint: ImageServer (tło, port 8000)
                └── Streamlit GUI (pierwszy plan, port 8501)
    → nginx :80
        ├── /product_photos/           → 127.0.0.1:8502 (Streamlit)
        └── /crm_product_images/  → 127.0.0.1:8000 (ImageServer)
```

Wolumen: `/opt/crm_product_photo/product_images` montowany do `/app/product_images` — zdjęcia przetrwają redeploy i są zapisywane z poziomu kontenera.

**Porty hosta (propozycja — zweryfikuj w kroku 0):**
- `127.0.0.1:8502:8501` — Streamlit (8501 zajęty przez `chatbot_dok`)
- `127.0.0.1:8000:8000` — serwer zdjęć

---

## Stan wyjściowy projektu

Pliki aplikacji:
- `crm_product_images_fetch.py` — eksport JPG z Creatio (CLI); **problem:** na sztywno `L:\...` i import `logowanie.py` z `C:\python_module`
- `app_gui.py` — GUI Streamlit; serwer HTTP startuje ręcznie przyciskiem
- `image_server.py` — `ThreadingHTTPServer` na `0.0.0.0`

Brak: `Dockerfile`, `docker-compose.yml`, `.github/workflows/`, repozytorium git.

Zmienne środowiskowe (`.env.example`):
- `BaseURI_IS`, `BaseURI`, `client_id`, `client_secret`, `grant_type`
- opcjonalnie: `PRODUCT_CODES`, `OUTPUT_DIR`, `IMAGE_SERVER_PORT`

---

## KROK 0 — Inwentaryzacja vs-web

**Cel:** sprawdzić wolne porty i konfigurację nginx bez konfliktu z istniejącymi aplikacjami.

Poproś użytkownika o SSH na `vs-web` i wklejenie wyniku (lub uruchomienie skryptu `deploy/inwentaryzacja-vs-web.sh` po jego utworzeniu w kroku 3):

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
docker compose ls 2>/dev/null || echo "brak compose ls"
sudo ss -tlnp | grep -E ':80|:443|:850[0-9]|:8000' || true
ls -la /etc/nginx/sites-enabled/ 2>/dev/null || echo "sprawdź proxy ręcznie"
```

**Uwaga:** ścieżka GUI `/product_photos/` jest już ustalona — w kroku 0 weryfikujesz tylko wolne porty i brak konfliktu w nginx.

**Ty (AI):** na podstawie wyniku zaproponuj:
- wolny port dla Streamlit (np. 8502)
- wolny port dla serwera zdjęć (np. 8000)
- ścieżki URL w nginx (`/product_photos/`, `/crm_product_images/`)
- czy self-hosted runner już działa (szukaj etykiety `vs-web`)

**Czekaj na akceptację propozycji.**

---

## KROK 1 — Repozytorium GitHub

**Cel:** utworzyć repo w `vs-bi` i pierwszy commit bez sekretów.

1. Zaproponuj nazwę repo (np. `crm-product-photo`) — **uzgodnij z użytkownikiem**.
2. Utwórz `.gitignore`:
   ```
   .env
   .venv/
   product_images/
   __pycache__/
   *.pyc
   .DS_Store
   ```
3. `git init`, dodaj pliki źródłowe (bez `.env`).
4. Upewnij się, że folder `ico/` (logo Trend Glass) jest w repo — GUI go wymaga.
5. Pierwszy commit, utworzenie prywatnego repo `vs-bi/<nazwa>`, push na `main`.

**Uwaga:** obecny `.env` lokalny zawiera nadmiarowe credentiale DB — **nie kopiuj go w całości na serwer**. Na produkcji tylko zmienne Creatio + `OUTPUT_DIR` + porty.

**Czekaj na potwierdzenie po utworzeniu repo.**

---

## KROK 2 — Przygotowanie kodu pod Linux/Docker

**Cel:** kod działa w kontenerze Debian, bez ścieżek Windows.

Zmiany do wprowadzenia (po akceptacji użytkownika):

### `crm_product_images_fetch.py`
- `OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/app/product_images'))` zamiast `L:\...`
- Usuń `sys.path.append(r'C:\python_module')`
- `Job_success` / `Job_failed`: stub no-op w projekcie lub `try/except ImportError`

### `.env.example` — dopisz:
```env
OUTPUT_DIR=/app/product_images
IMAGE_SERVER_PORT=8000
PUBLIC_IMAGE_BASE_URL=http://vs-web/crm_product_images
STREAMLIT_BASE_URL_PATH=product_photos
```

### `image_server.py`
- Funkcja `get_public_base_url()` — jeśli ustawiono `PUBLIC_IMAGE_BASE_URL`, używaj go w linkach zamiast IP kontenera (ważne dla Excela w sieci LAN).

### `app_gui.py`
- Na produkcji (env `AUTO_START_IMAGE_SERVER=1` lub zawsze w Dockerze): pokaż info „Serwer zdjęć uruchomiony automatycznie”, nie wymagaj ręcznego Start.

**Po zmianach:** krótki test lokalny `uv run streamlit run app_gui.py` (opcjonalnie).

**Czekaj na OK przed krokiem 3.**

---

## KROK 3 — Docker: Dockerfile, entrypoint, compose

**Cel:** jeden kontener, serwer zdjęć startuje z kontenerem.

### `entrypoint.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/product_images}"
PORT="${IMAGE_SERVER_PORT:-8000}"
BASE_URL_PATH="${STREAMLIT_BASE_URL_PATH:-product_photos}"

mkdir -p "${OUTPUT_DIR}"

# Serwer zdjęć w tle — żyje tak długo jak kontener
uv run python -c "
import os, signal, time
from pathlib import Path
from image_server import ImageServer
d = Path(os.environ.get('OUTPUT_DIR', '/app/product_images'))
p = int(os.environ.get('IMAGE_SERVER_PORT', '8000'))
s = ImageServer()
s.start(d, p)
signal.pause()
" &

exec uv run streamlit run app_gui.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.baseUrlPath="${BASE_URL_PATH}" \
  --server.enableCORS=false \
  --server.headless=true
```

### `Dockerfile` (wzorzec jak Proj_RAG)
- `FROM python:3.13-slim`
- `uv sync --frozen --no-dev`
- `EXPOSE 8501 8000`
- `ENTRYPOINT ["bash", "entrypoint.sh"]`

### `docker-compose.yml`
```yaml
name: crm_product_photo

services:
  crm_product_photo:
    build: .
    container_name: crm_product_photo
    restart: unless-stopped
    env_file: /opt/crm_product_photo/.env
    volumes:
      - /opt/crm_product_photo/product_images:/app/product_images
      - /opt/crm_product_photo/logs:/app/logs
    ports:
      - "127.0.0.1:8502:8501"   # port hosta — dostosuj po kroku 0
      - "127.0.0.1:8000:8000"
```

### `.streamlit/config.toml`
```toml
baseUrlPath = "product_photos"
```

### `deploy/inwentaryzacja-vs-web.sh` (wzorzec Proj_RAG)
```bash
#!/usr/bin/env bash
set -euo pipefail
echo "=== docker ps ==="
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
echo "=== docker compose ls ==="
docker compose ls 2>/dev/null || echo "brak compose ls"
echo "=== porty 80 / 443 / 850x / 8000 ==="
sudo ss -tlnp | grep -E ':80|:443|:850[0-9]|:8000' || true
echo "=== reverse proxy ==="
ls -la /etc/nginx/sites-enabled/ 2>/dev/null || echo "sprawdź proxy ręcznie"
```

**Czekaj na OK przed wdrożeniem na serwer.**

---

## KROK 4 — Pierwsze wdrożenie ręczne na vs-web

**Cel:** kontener działa przed skonfigurowaniem CI/CD.

Poproś użytkownika o wykonanie (dostosuj użytkownika SSH jeśli inny):

```bash
# Na vs-web:
sudo mkdir -p /opt/crm_product_photo/{product_images,logs}
sudo chown $USER:$USER /opt/crm_product_photo
```

```powershell
# Z maszyny deweloperskiej (PowerShell) — tylko potrzebne zmienne Creatio:
scp .env gcieslinski@vs-web:/opt/crm_product_photo/.env
```

```bash
# Na vs-web:
chmod 600 /opt/crm_product_photo/.env
git clone git@github.com:vs-bi/<NAZWA-REPO>.git /opt/crm_product_photo/repo
cd /opt/crm_product_photo/repo
docker compose build
docker compose up -d
```

**Health check:**
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8502/product_photos/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
docker compose logs --tail=30
```

Oczekiwane: HTTP 200 na GUI, serwer zdjęć odpowiada (404 lub 200 jeśli są pliki JPG).

**Czekaj na wynik testów od użytkownika.**

---

## KROK 5 — Nginx reverse proxy

**Cel:** dostęp z sieci firmowej pod `http://vs-web/...`

Utwórz `deploy/nginx-crm_product_photo.conf`:

```nginx
# Fragment do bloku server { } dla hosta vs-web (port 80).
# Po edycji: sudo nginx -t && sudo systemctl reload nginx

location /product_photos/ {
    proxy_pass http://127.0.0.1:8502/product_photos/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}

location /crm_product_images/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Poproś użytkownika o dopisanie fragmentu do nginx i reload.

**Test z przeglądarki:** `http://vs-web/product_photos/` i przykładowy link do JPG.

**Czekaj na potwierdzenie.**

---

## KROK 6 — Self-hosted GitHub Actions runner

**Cel:** deploy z Actions bez wychodzenia w internet (sieć wewnętrzna).

1. Sprawdź czy runner z etykietą `vs-web` już istnieje (często jest współdzielony między projektami).
2. Jeśli **nie ma:** prowadź użytkownika przez GitHub → Settings → Actions → Runners → New self-hosted runner (Linux).
3. Na vs-web uruchom komendy rejestracji z GitHub (token ważny ~1 h).
4. Etykiety runnera: `vs-web`, `linux`.

**Czekaj na potwierdzenie, że runner jest online.**

---

## KROK 7 — Pipeline CI/CD

**Cel:** każdy push na `main` przebudowuje kontener na vs-web.

### `.github/workflows/deploy.yml`
```yaml
name: Deploy to vs-web

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  deploy:
    runs-on: [self-hosted, vs-web, linux]
    if: github.repository == 'vs-bi/<NAZWA-REPO>'
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build i redeploy kontenera
        run: bash deploy/ci-deploy.sh
```

### `deploy/ci-deploy.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

OPT_DIR="/opt/crm_product_photo"
REPO_DIR="${GITHUB_WORKSPACE:-${OPT_DIR}/repo}"

[[ -f "${OPT_DIR}/.env" ]] || { echo "Brak ${OPT_DIR}/.env" >&2; exit 1; }
[[ -d "${REPO_DIR}" ]] || { echo "Brak ${REPO_DIR}" >&2; exit 1; }

cd "${REPO_DIR}"
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
[[ "${HTTP_CODE}" == "200" ]] || { docker compose logs --tail=30 >&2; exit 1; }
docker ps --filter name=crm_product_photo
```

Commit + push na `main`. **Czekaj na wynik workflow.**

---

## KROK 8 — Test pełnego cyklu CI/CD

1. Wprowadź drobną widoczną zmianę (np. tekst w GUI).
2. Commit → push → `main`.
3. Obserwuj Actions → Deploy to vs-web.
4. Zweryfikuj na `http://vs-web/product_photos/`.

**Czekaj na potwierdzenie użytkownika.**

---

## KROK 9 — Dokumentacja operacyjna

Dodaj do `README.md` sekcje:
- **Uruchomienie lokalne:** `uv sync`, `cp .env.example .env`, `uv run streamlit run app_gui.py`
- **Wdrożenie na vs-web:** struktura `/opt/crm_product_photo/`, nginx, runner
- **Zmiana sekretów:** edycja `/opt/crm_product_photo/.env` + `docker compose up -d --force-recreate`
- **Logi:** `docker compose -f /opt/crm_product_photo/repo/docker-compose.yml logs -f`
- **Linki do zdjęć w Excelu:** `http://vs-web/crm_product_images/KOD.jpg`

---

## Troubleshooting

| Problem | Rozwiązanie |
|---------|-------------|
| Port zajęty przy `docker compose up` | Wróć do kroku 0, wybierz inny port, zaktualizuj compose + nginx |
| HTTP 502 z nginx | Sprawdź `docker ps`, logi kontenera, czy porty mapowane na `127.0.0.1` |
| Brak zdjęć po eksporcie | Sprawdź mount wolumenu: `docker inspect crm_product_photo`, `ls /opt/crm_product_photo/product_images` |
| Linki w GUI pokazują złe IP | Ustaw `PUBLIC_IMAGE_BASE_URL=http://vs-web/crm_product_images` w `.env` |
| Actions nie startuje | Runner offline lub brak etykiety `vs-web` |
| Streamlit 404 pod ścieżką | `baseUrlPath` w config.toml i nginx muszą być zgodne (`product_photos`) |
| Import `logowanie` failuje | Stub no-op w projekcie (krok 2) |

---

## Lista plików do utworzenia w repo

```
Dockerfile
docker-compose.yml
entrypoint.sh
deploy/ci-deploy.sh
deploy/wdroz-vs-web.sh          # opcjonalnie: skrypt pierwszego wdrożenia
deploy/inwentaryzacja-vs-web.sh
deploy/nginx-crm_product_photo.conf
.github/workflows/deploy.yml
.gitignore
README.md
```

Zmiany w istniejących: `crm_product_images_fetch.py`, `.env.example`, `.streamlit/config.toml`, `app_gui.py`, `image_server.py`.

---

## Jak zacząć sesję vibe-codingu

Wklej do Cursor:

> Przeczytaj `prompt.md` i rozpocznij **KROK 0**. Prowadź mnie interaktywnie — po każdym kroku czekaj na moje potwierdzenie. Nie implementuj kolejnych kroków bez mojej zgody.
