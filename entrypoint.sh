#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/product_images}"
BASE_URL_PATH="${STREAMLIT_BASE_URL_PATH:-product_photos}"

mkdir -p "${OUTPUT_DIR}"

# Serwer zdjęć w tle — żyje tak długo jak kontener
uv run python -c "
import os, signal
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
