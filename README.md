# CRM Product Photo

Eksport zdjęć produktów z Creatio CRM do JPG 800×800 oraz hosting pod linki w Excelu.

**Produkcja:** `https://vs-web/product_photos/` (GUI) · zdjęcia: `http://vs-web/crm_product_images/KOD.jpg` (Excel) lub `https://...` (przeglądarka — patrz sekcja *Certyfikat a Excel*)

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

Nginx: fragment z `deploy/nginx-crm_product_photo.conf` w `/etc/nginx/sites-available/apps` — **w bloku port 80 i w bloku `listen 443 ssl`** (patrz sekcja HTTPS poniżej).

### HTTPS

TLS terminuje nginx na hoście (port 443). Kontener Docker pozostaje na HTTP wewnętrznym (`127.0.0.1:8001` / `8502`).

**1. Diagnostyka (na vs-web):**

```bash
curl -k -s -o /dev/null -w "HTTPS root: %{http_code}\n" https://vs-web/
curl -k -s -o /dev/null -w "HTTPS zdjęcia: %{http_code}\n" https://vs-web/crm_product_images/
curl -s -o /dev/null -w "HTTP zdjęcia: %{http_code}\n" http://vs-web/crm_product_images/
sudo grep -nE 'listen 443|ssl_certificate|crm_product_images|product_photos' /etc/nginx/sites-available/apps | head -40
```

Oczekiwane po konfiguracji: **HTTPS zdjęcia: 200** (lub 404 gdy folder pusty).

**2. Nginx — location w bloku SSL:**

Jeśli `https://vs-web/chatbot_dok/` działa, ale `https://vs-web/crm_product_images/` nie — skopiuj oba `location` z `deploy/nginx-crm_product_photo.conf` do bloku `server { listen 443 ssl; ... }` (często są już tylko w bloku port 80).

```bash
sudo nano /etc/nginx/sites-available/apps
sudo nginx -t && sudo systemctl reload nginx
```

**3. Aplikacja — adres w linkach (`.env` na serwerze):**

```bash
nano /opt/crm_product_photo/.env
# ustaw:
# PUBLIC_IMAGE_BASE_URL=https://vs-web/crm_product_images

cd /opt/crm_product_photo/repo && docker compose up -d --force-recreate
```

### Certyfikat a Excel

Excel na Windows **nie ładuje obrazów z HTTPS**, jeśli certyfikat nie jest **zaufany w systemie** (jak przeglądarka nie ma przycisku „zaakceptuj wyjątek”). Na vs-web domyślnie jest certyfikat **snakeoil** (self-signed) — `curl -k` i przeglądarka mogą działać, **Excel nie pokaże zdjęcia** przy linku `https://vs-web/crm_product_images/...`.

| Scenariusz | Link w Excelu | Uwagi |
|----------|---------------|--------|
| **Sieć wewnętrzna (teraz)** | `http://vs-web/crm_product_images/KOD.jpg` | Działa bez certyfikatu. Ustaw w `.env`: `PUBLIC_IMAGE_BASE_URL=http://vs-web/crm_product_images` |
| **HTTPS w przeglądarce** | `https://vs-web/product_photos/` | OK przy snakeoil (ostrzeżenie certyfikatu) |
| **HTTPS w Excelu** | `https://...` | Wymaga certyfikatu **zaufanego na PC użytkownika** |

**Co działa na dłuższą metę (HTTPS w Excelu):**

1. **Certyfikat z firmowego CA (zalecane)** — np. Active Directory Certificate Services. IT wystawia cert dla `vs-web` (lub firmowej FQDN), zaufanie CA rozdaje się przez GPO na komputery w domenie.
2. **Certyfikat komercyjny na publiczną domenę** — tylko jeśli w Excelu używasz **tej samej nazwy** co w certyfikacie (np. `https://photos.trendglass.pl/...`). Publiczne CA **nie wydadzą** certyfikatu na samo wewnętrzne `vs-web` bez zweryfikowalnej domeny DNS.
3. **Kupno certyfikatu „osobiście”** — ma sens wyłącznie przy **własnej domenie** i linkach w Excelu pod tą domeną; **nie naprawi** adresów `https://vs-web/...`.

**Rekomendacja:** do czasu certyfikatu od IT — linki w arkuszach: **HTTP**; po wdrożeniu firmowego CA — **HTTPS** i aktualizacja `PUBLIC_IMAGE_BASE_URL` na `https://...`.

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

**Linki do zdjęć w Excelu:** `http://vs-web/crm_product_images/KOD.jpg` (np. `70056.jpg`). Po wdrożeniu zaufanego certyfikatu firmowego: `https://vs-web/crm_product_images/KOD.jpg`.

**Usunięcie pobranych zdjęć (SSH):**

Zdjęcia leżą na hoście w `/opt/crm_product_photo/product_images/` (wolumen — kontener **nie wymaga** restartu po skasowaniu plików). Po usunięciu linki w Excelu przestaną działać do czasu ponownego eksportu.

```bash
# Zaloguj się na serwer
ssh gcieslinski@vs-web

# Podgląd — ile plików i przykładowe nazwy
ls -la /opt/crm_product_photo/product_images/
ls /opt/crm_product_photo/product_images/*.jpg 2>/dev/null | wc -l

# Usuń jeden plik po kodzie produktu
rm /opt/crm_product_photo/product_images/70056.jpg

# Usuń wszystkie pobrane JPG (ostrożnie — bez cofania)
rm /opt/crm_product_photo/product_images/*.jpg

# Alternatywa: opróżnij folder, zostaw katalog
find /opt/crm_product_photo/product_images/ -maxdepth 1 -name '*.jpg' -delete
```

Sprawdzenie, że plik zniknął (oczekiwane **404**):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://vs-web/crm_product_images/70056.jpg
```

## Zmienne środowiskowe

Zobacz `.env.example` — wymagane: `BaseURI_IS`, `BaseURI`, `client_id`, `client_secret`, `grant_type`.

Produkcja dodatkowo: `OUTPUT_DIR=/app/product_images`, `PUBLIC_IMAGE_BASE_URL=http://vs-web/crm_product_images` (Excel; przy firmowym CA można `https://`), `STREAMLIT_BASE_URL_PATH=product_photos`.
