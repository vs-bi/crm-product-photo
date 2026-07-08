import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import anyio
import requests
from asyncer import asyncify, create_task_group
from dotenv import load_dotenv
from loguru import logger
from PIL import Image
from tqdm import tqdm

_firmowy_modul = Path(r'C:\python_module')
if _firmowy_modul.is_dir():
    sys.path.append(str(_firmowy_modul))
try:
    from logowanie import Job_failed, Job_success
except ImportError:
    from job_logging import Job_failed, Job_success

EMPTY_GUID = '00000000-0000-0000-0000-000000000000'
MANIFEST_FILENAME = 'export_manifest.json'
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(Path(__file__).parent / 'product_images')))
MAX_RETRIES = 3
REQUEST_TIMEOUT = 60
MAX_CONCURRENT = 8
IMAGE_TARGET_WIDTH = 800
IMAGE_TARGET_HEIGHT = 800
IMAGE_BACKGROUND_COLOR = (255, 255, 255)
IMAGE_JPEG_QUALITY = 85

TOKEN_CACHE = {
    'access_token': None,
    'expires_at': None,
}

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
})

load_dotenv()

base_uri_is = os.getenv('BaseURI_IS')
base_uri = os.getenv('BaseURI')
client_id = os.getenv('client_id')
client_secret = os.getenv('client_secret')
grant_type = os.getenv('grant_type')

time_s = datetime.now()


def get_token_url():
    """Pobiera URL endpointu tokenu z konfiguracji OpenID."""
    logger.info('Sprawdzanie konfiguracji Identity Service...')
    openid_config_url = f'{base_uri_is}/.well-known/openid-configuration'

    try:
        config_response = HTTP_SESSION.get(openid_config_url)
        if config_response.status_code == 200:
            config_data = config_response.json()
            logger.success('Identity Service jest dostepny')
            return config_data.get('token_endpoint')
        logger.warning(f'Nie mozna pobrac konfiguracji OpenID (status: {config_response.status_code})')
    except Exception as e:
        logger.warning(f'Blad podczas sprawdzania konfiguracji: {e}')

    return f'{base_uri_is}/connect/token'


def get_access_token(token_url, force_refresh=False):
    """Pobiera token dostępu OAuth 2.0 z cache'owaniem."""
    if not force_refresh and TOKEN_CACHE['access_token'] and TOKEN_CACHE['expires_at']:
        if datetime.now() < TOKEN_CACHE['expires_at']:
            return TOKEN_CACHE['access_token']
        logger.info('Token w cache wygasl, pobieram nowy...')

    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': (grant_type or '').strip(),
    }

    response = HTTP_SESSION.post(
        token_url,
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    response.raise_for_status()

    token_data = response.json()
    access_token = token_data.get('access_token')
    expires_in = token_data.get('expires_in', 3600)

    TOKEN_CACHE['access_token'] = access_token
    TOKEN_CACHE['expires_at'] = datetime.now() + timedelta(seconds=expires_in - 60)
    logger.success('Token OAuth pobrany pomyslnie')

    return access_token


def odata_headers(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate',
    }


def fetch_all_products_with_pictures(token_url, scan_progress=None, product_codes=None):
    """Pobiera produkty z PictureId przez OData z paginacja.

    product_codes: opcjonalna kolekcja kodow do filtrowania; None = filtr z env PRODUCT_CODES.
    """
    access_token = get_access_token(token_url)
    products = []
    # Creatio nie obsluguje $filter na PictureId (blad 500) — filtrujemy po stronie klienta
    url = f'{base_uri}/0/odata/Product?$select=Id,Code,PictureId'

    while url:
        response = HTTP_SESSION.get(url, headers=odata_headers(access_token), timeout=REQUEST_TIMEOUT)

        if response.status_code == 401:
            access_token = get_access_token(token_url, force_refresh=True)
            response = HTTP_SESSION.get(url, headers=odata_headers(access_token), timeout=REQUEST_TIMEOUT)

        response.raise_for_status()
        data = response.json()

        for record in data.get('value', []):
            code = (record.get('Code') or '').strip()
            picture_id = record.get('PictureId')
            if not code or not picture_id or picture_id == EMPTY_GUID:
                continue
            products.append({
                'Id': record.get('Id'),
                'Code': code,
                'PictureId': picture_id,
            })
            if scan_progress is not None:
                scan_progress.update(1)

        url = data.get('@odata.nextLink')

    if product_codes is None:
        product_codes_filter = os.getenv('PRODUCT_CODES', '').strip()
        product_codes = [c.strip() for c in product_codes_filter.split(',')] if product_codes_filter else None

    if product_codes:
        allowed = {c.strip() for c in product_codes if c.strip()}
        products = [p for p in products if p['Code'] in allowed]
        logger.info(f'Filtr kodow produktow: {len(products)} produktow')

    logger.info(f'Znaleziono {len(products)} produktow ze zdjeciami')
    return products, access_token


def load_previous_codes(output_dir):
    """Zwraca zbior kodow z poprzedniego eksportu (pusty gdy brak/blad)."""
    path = Path(output_dir) / MANIFEST_FILENAME
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return set(data.get('codes', []))
    except Exception as e:
        logger.warning(f'Nie udalo sie wczytac manifestu {path}: {e}')
        return set()


def save_export_manifest(output_dir, codes):
    """Zapisuje aktualny zbior kodow z timestampem."""
    path = Path(output_dir) / MANIFEST_FILENAME
    payload = {
        'exported_at': datetime.now().isoformat(timespec='seconds'),
        'codes': sorted(codes),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def sanitize_filename(code):
    """Usuwa znaki niedozwolone w nazwach plikow Windows."""
    return re.sub(r'[\\/:*?"<>|]', '_', code).strip()


def deduplicate_products(products):
    """Usuwa duplikaty Code — zostawia ostatni rekord, loguje ostrzezenia."""
    by_code = {}
    for product in products:
        code = product['Code']
        if code in by_code:
            logger.warning(
                f'Duplikat Code={code}: '
                f'{by_code[code]["PictureId"]} -> {product["PictureId"]} (uzyty ostatni)'
            )
        by_code[code] = product
    return list(by_code.values())


def fetch_image_bytes(picture_id, token_url, access_token):
    """Pobiera binaria obrazu z endpointu SysImage/.../Data."""
    url = f'{base_uri}/0/odata/SysImage({picture_id})/Data'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/octet-stream',
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = HTTP_SESSION.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 401:
                access_token = get_access_token(token_url, force_refresh=True)
                headers['Authorization'] = f'Bearer {access_token}'
                response = HTTP_SESSION.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()

            if not response.content:
                raise ValueError('Pusta odpowiedz z endpointu /Data')

            return response.content, access_token

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                logger.warning(f'Proba {attempt}/{MAX_RETRIES} nieudana dla {picture_id}: {e}. Ponawiam za {wait}s...')
                time.sleep(wait)

    raise last_error


def resize_with_letterbox(img):
    """Skaluje obraz z zachowaniem proporcji i wyśrodkowuje na białym tle docelowego rozmiaru."""
    target_w, target_h = IMAGE_TARGET_WIDTH, IMAGE_TARGET_HEIGHT
    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new('RGB', (target_w, target_h), IMAGE_BACKGROUND_COLOR)
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    if resized.mode == 'RGBA':
        canvas.paste(resized, (offset_x, offset_y), resized)
    else:
        canvas.paste(resized, (offset_x, offset_y))
    return canvas


def save_as_jpg(content, code, output_dir):
    """Konwertuje binaria obrazu do JPEG i zapisuje na dysk."""
    img = Image.open(BytesIO(content))
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
    else:
        img = img.convert('RGB')

    img = resize_with_letterbox(img)

    safe_code = sanitize_filename(code)
    out_path = output_dir / f'{safe_code}.jpg'
    img.save(out_path, 'JPEG', quality=IMAGE_JPEG_QUALITY, optimize=True)
    return out_path


@asyncify
def process_product(product, token_url, access_token_holder, stats, semaphore, progress_bar):
    """Pobiera i zapisuje pojedyncze zdjecie produktu."""
    code = product['Code']
    picture_id = product['PictureId']

    with semaphore:
        try:
            content, new_token = fetch_image_bytes(picture_id, token_url, access_token_holder['token'])
            access_token_holder['token'] = new_token
            out_path = save_as_jpg(content, code, OUTPUT_DIR)
            stats['saved'] += 1
            return True, None
        except Exception as e:
            stats['errors'] += 1
            msg = f'Code={code}, PictureId={picture_id}: {e}'
            tqdm.write(f'BŁĄD: {msg}')
            return False, msg
        finally:
            remaining = progress_bar.total - progress_bar.n - 1
            progress_bar.set_postfix(
                zapisane=stats['saved'],
                bledy=stats['errors'],
                pozostalo=max(remaining, 0),
                refresh=False,
            )
            progress_bar.update(1)


async def main():
    job_name = 'crm_product_images_fetch'

    try:
        logger.info('=' * 60)
        logger.info('CREATIO - EKSPORT ZDJEC PRODUKTOW')
        logger.info('=' * 60)

        if not all([base_uri, base_uri_is, client_id, client_secret, grant_type]):
            raise RuntimeError('Brak wymaganych zmiennych srodowiskowych w pliku .env')

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f'Folder wyjsciowy: {OUTPUT_DIR}')
        logger.info(
            f'Docelowy rozmiar zdjec: {IMAGE_TARGET_WIDTH}x{IMAGE_TARGET_HEIGHT} (letterbox, biale tlo)'
        )

        token_url = get_token_url()

        logger.info('Skanowanie listy produktow w Creatio...')
        with tqdm(desc='Skanowanie produktow', unit=' zdj.', dynamic_ncols=True) as scan_bar:
            products, access_token = fetch_all_products_with_pictures(token_url, scan_bar)

        products = deduplicate_products(products)

        if not products:
            logger.warning('Brak produktow ze zdjeciami do pobrania')
            Job_success(job_name)
            return

        stats = {'saved': 0, 'errors': 0}
        access_token_holder = {'token': access_token}
        errors = []
        saved_codes = []
        previous_codes = load_previous_codes(OUTPUT_DIR)
        semaphore = threading.Semaphore(MAX_CONCURRENT)
        total = len(products)

        logger.info(f'Rozpoczynam pobieranie {total} zdjec (max {MAX_CONCURRENT} rownolegle)...')

        with tqdm(
            total=total,
            desc='Pobieranie JPG',
            unit=' plik',
            dynamic_ncols=True,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}',
        ) as download_bar:
            async with create_task_group() as task_group:
                soon_values = []
                for product in products:
                    soon_value = task_group.soonify(process_product)(
                        product,
                        token_url,
                        access_token_holder,
                        stats,
                        semaphore,
                        download_bar,
                    )
                    soon_values.append((product['Code'], soon_value))

        for code, soon_value in soon_values:
            try:
                success, error_msg = soon_value.value
                if success:
                    saved_codes.append(code)
                elif error_msg:
                    errors.append(error_msg)
            except Exception as e:
                stats['errors'] += 1
                errors.append(f'Code={code}: {e}')

        new_codes = sorted(set(saved_codes) - previous_codes)
        if saved_codes:
            save_export_manifest(OUTPUT_DIR, previous_codes | set(saved_codes))

        logger.info('=' * 60)
        logger.info('PODSUMOWANIE EKSPORTU ZDJEC')
        logger.info('=' * 60)
        logger.info(f'Produkty ze zdjeciami: {len(products)}')
        logger.success(f'Zapisane pliki JPG: {stats["saved"]}')
        logger.info(f'Nowe zdjecia (KKT): {len(new_codes)}')
        if new_codes:
            logger.info(f'Nowe kody produktow: {", ".join(new_codes)}')
        if stats['errors']:
            logger.error(f'Bledy: {stats["errors"]}')
        logger.info(f'Czas wykonania: {datetime.now() - time_s}')

        if stats['errors'] and stats['saved'] == 0:
            raise RuntimeError(f'Nie udalo sie pobrac zadnego zdjecia ({stats["errors"]} bledow)')

        if stats['errors']:
            logger.warning('Eksport zakonczony z czesciowymi bledami')

        Job_success(job_name)

    except Exception as e:
        logger.error(f'Error: {e}')
        Job_failed(job_name, e)
        raise


if __name__ == '__main__':
    anyio.run(main)
