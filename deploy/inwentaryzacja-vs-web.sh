#!/usr/bin/env bash
# Inwentaryzacja serwera vs-web przed wdrożeniem crm_product_photo.
set -euo pipefail

echo "=== docker ps ==="
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"

echo
echo "=== docker compose ls ==="
docker compose ls 2>/dev/null || docker-compose ls 2>/dev/null || echo "brak compose ls"

echo
echo "=== porty 80 / 443 / 850x / 800x ==="
sudo ss -tlnp | grep -E ':80|:443|:850[0-9]|:800[0-9]' || true

echo
echo "=== reverse proxy ==="
ls -la /etc/nginx/sites-enabled/ 2>/dev/null \
  || ls -la /etc/caddy/ 2>/dev/null \
  || echo "sprawdź proxy ręcznie"
