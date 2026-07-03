# CRM Product Photo

Eksport zdjęć produktów z Creatio CRM do PNG 800×800 oraz hosting HTTP pod linki w Excelu.

**Produkcja:** `http://vs-web/product_photos/` (GUI) · `http://vs-web/crm_product_images/KOD.png` (zdjęcia)

## Uruchomienie lokalne

```bash
uv sync
cp .env.example .env   # uzupełnij Creatio OAuth
uv run streamlit run app_gui.py
```

CLI (jednorazowy eksport):

```bash
uv run python crm_product_images_fetch.py
```

## Wdrożenie na vs-web

| Element | Ścieżka / wartość |
|---------|-------------------|
| Katalog na hoście | `/opt/crm_product_photo/` |
| Sekrety | `/opt/crm_product_photo/.env` (`chmod 600`) |
| Zdjęcia (wolumen) | `/opt/crm_product_photo/product_images/` |
| Repo / compose | `/opt/crm_product_photo/repo/` |
| Kontener | `crm_product_photo` |
| Porty hosta | `127.0.0.1:8502` (GUI), `127.0.0.1:8001` (zdjęcia) |

### Pierwsze wdrożenie

```bash
sudo mkdir -p /opt/crm_product_photo/{product_images,logs}
sudo chown $USER:$USER /opt/crm_product_photo
# skopiuj .env z maszyny deweloperskiej (tylko Creatio + OUTPUT_DIR, bez haseł DB)
git clone git@github.com:vs-bi/crm-product-photo.git /opt/crm_product_photo/repo
cd /opt/crm_product_photo/repo
docker compose build && docker compose up -d
```

Nginx: fragment z `deploy/nginx-crm_product_photo.conf` w `/etc/nginx/sites-available/apps`.

### CI/CD

- Workflow: `.github/workflows/deploy.yml` — push na `main` → redeploy na vs-web
- Runner: `vs-web-crm-product-photo` (etykiety: `self-hosted`, `vs-web`, `linux`)
- Skrypt deploy: `deploy/ci-deploy.sh`

## Operacje

**Zmiana sekretów (.env):**

```bash
nano /opt/crm_product_photo/.env
cd /opt/crm_product_photo/repo && docker compose up -d --force-recreate
```

**Logi:**

```bash
cd /opt/crm_product_photo/repo
docker compose logs -f
```

**Health check:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8502/product_photos/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/
```

**Linki do zdjęć w Excelu:** `http://vs-web/crm_product_images/KOD.png` (np. `70056.png`)

## Zmienne środowiskowe

Zobacz `.env.example` — wymagane: `BaseURI_IS`, `BaseURI`, `client_id`, `client_secret`, `grant_type`.

Produkcja dodatkowo: `OUTPUT_DIR=/app/product_images`, `PUBLIC_IMAGE_BASE_URL=http://vs-web/crm_product_images`, `STREAMLIT_BASE_URL_PATH=product_photos`.
