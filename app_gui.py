"""GUI Streamlit dla eksportu zdjęć produktów z Creatio CRM.

Uruchamianie: uv run streamlit run app_gui.py
Identyfikacja wizualna: Trend Glass S.A. (brandbook / skill tg-guidelines).
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import streamlit as st

import crm_product_images_fetch as core
from crm_product_images_fetch import (
    MAX_CONCURRENT,
    deduplicate_products,
    fetch_all_products_with_pictures,
    fetch_image_bytes,
    get_token_url,
    save_as_jpg,
)
from image_server import ImageServer

LOGO_PATH = Path(__file__).parent / 'ico' / 'Trend-Glass-sygnet-accent-green-RGB.png'
DEFAULT_OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', str(Path(__file__).parent / 'product_images')))
DEFAULT_SERVER_PORT = int(os.getenv('IMAGE_SERVER_PORT', '8000'))
IS_PRODUCTION_HOST = os.path.exists('/.dockerenv') or os.getenv('AUTO_START_IMAGE_SERVER') == '1'
PUBLIC_IMAGE_BASE_URL = os.getenv('PUBLIC_IMAGE_BASE_URL', '').strip().rstrip('/')
DEFAULT_PUBLIC_IMAGE_BASE_URL = 'https://vs-web/crm_product_images'


def public_image_example_url():
    base = PUBLIC_IMAGE_BASE_URL or DEFAULT_PUBLIC_IMAGE_BASE_URL
    return f'{base}/KOD.jpg'

# Kolory Trend Glass (brandbook 2.1 + rozbarwienia 2.2)
BOTTLE_GREEN = '#134534'
CRISTAL_GREY = '#EDEDE8'
NIGHT_BLACK = '#141414'
ACCENT_GREEN = '#26A96C'
ACCENT_ORANGE = '#EB8B47'
INFO_GREY = '#718F85'
BG_SOFT = '#F8F8F6'
BOTTLE_GREEN_90 = '#2B5848'

TG_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700&display=swap');

html, body, [class^="st"], .stMarkdown, .stTextInput, .stButton, .stExpander {{
    font-family: 'Manrope', 'Segoe UI', Arial, sans-serif !important;
}}

[data-testid="stIconMaterial"],
[data-testid^="stExpanderIcon"],
.material-symbols-rounded {{
    font-family: 'Material Symbols Rounded' !important;
}}

h1, h2, h3, h4 {{
    color: {BOTTLE_GREEN} !important;
    text-align: left;
}}

.tg-header {{
    display: flex;
    align-items: center;
    gap: 1.1rem;
    padding-bottom: 0.9rem;
    border-bottom: 1.5pt solid {BOTTLE_GREEN};
    margin-bottom: 1.4rem;
}}
.tg-header img {{
    width: 64px;
    height: 64px;
}}
.tg-header h1 {{
    font-weight: 700;
    font-size: 1.7rem;
    line-height: 1.2;
    margin: 0;
    padding: 0;
    color: {BOTTLE_GREEN};
}}
.tg-header p {{
    font-weight: 500;
    font-size: 0.85rem;
    line-height: 1.3;
    margin: 0.15rem 0 0 0;
    color: {INFO_GREY};
}}

.stButton > button[kind="primary"] {{
    background-color: {BOTTLE_GREEN};
    color: {CRISTAL_GREY};
    border: none;
    border-radius: 4px;
    font-weight: 600;
    text-align: center;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {BOTTLE_GREEN_90};
    color: {CRISTAL_GREY};
}}

.tg-metrics {{
    display: flex;
    gap: 0.8rem;
    margin: 0.6rem 0 1rem 0;
    flex-wrap: wrap;
}}
.tg-metric {{
    flex: 1 1 140px;
    background: {BG_SOFT};
    border-left: 3px solid {ACCENT_GREEN};
    border-radius: 4px;
    padding: 0.7rem 0.9rem;
}}
.tg-metric .label {{
    font-size: 0.72rem;
    font-weight: 500;
    color: {INFO_GREY};
    line-height: 1.3;
}}
.tg-metric .value {{
    font-size: 1.45rem;
    font-weight: 700;
    color: {BOTTLE_GREEN};
    line-height: 1.2;
}}
.tg-metric.error-alert {{
    border-left-color: {ACCENT_ORANGE};
}}
.tg-metric.error-alert .value {{
    color: {ACCENT_ORANGE};
}}

.tg-info {{
    font-size: 0.8rem;
    color: {INFO_GREY};
}}
</style>
"""


class ScanCounter:
    """Adapter postępu skanowania zgodny z interfejsem tqdm (.update)."""

    def __init__(self, placeholder):
        self.count = 0
        self.placeholder = placeholder

    def update(self, n=1):
        self.count += n
        if self.count % 20 == 0:
            self.placeholder.write(f'Znalezione zdjęcia: {self.count}')


def parse_codes(text):
    codes = [c.strip() for c in text.split(',') if c.strip()]
    return codes or None


def download_one(product, token_url, token_holder, output_dir):
    content, new_token = fetch_image_bytes(product['PictureId'], token_url, token_holder['token'])
    token_holder['token'] = new_token
    return save_as_jpg(content, product['Code'], output_dir)


def run_export(product_codes, output_dir, progress_area):
    """Pełny przebieg eksportu; zwraca słownik z podsumowaniem."""
    started = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)

    with progress_area.status('Skanowanie produktów w Creatio…', expanded=True) as status:
        counter = ScanCounter(st.empty())
        token_url = get_token_url()
        products, access_token = fetch_all_products_with_pictures(
            token_url, scan_progress=counter, product_codes=product_codes
        )
        products = deduplicate_products(products)
        status.update(label=f'Skanowanie zakończone — produkty ze zdjęciami: {len(products)}', state='complete')

    total = len(products)
    saved = 0
    errors = []

    if total:
        token_holder = {'token': access_token}
        bar = progress_area.progress(0.0, text=f'Pobieranie: 0/{total}')

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
            futures = {
                executor.submit(download_one, product, token_url, token_holder, output_dir): product
                for product in products
            }
            done = 0
            for future in as_completed(futures):
                product = futures[future]
                done += 1
                try:
                    future.result()
                    saved += 1
                except Exception as e:
                    errors.append(f'Code={product["Code"]}, PictureId={product["PictureId"]}: {e}')
                bar.progress(
                    done / total,
                    text=f'Pobieranie: {done}/{total} · zapisane {saved} · błędy {len(errors)}',
                )

        bar.progress(1.0, text=f'Zakończono: {saved} zapisanych, {len(errors)} błędów')

    return {
        'total': total,
        'saved': saved,
        'errors': errors,
        'duration': datetime.now() - started,
        'output_dir': str(output_dir),
    }


def render_summary(result):
    st.subheader('Podsumowanie eksportu')

    duration = str(result['duration']).split('.')[0]
    error_count = len(result['errors'])
    error_class = 'tg-metric error-alert' if error_count else 'tg-metric'
    st.markdown(
        f"""
        <div class="tg-metrics">
          <div class="tg-metric"><div class="label">Produkty ze zdjęciami</div><div class="value">{result['total']}</div></div>
          <div class="tg-metric"><div class="label">Zapisane pliki JPG</div><div class="value">{result['saved']}</div></div>
          <div class="{error_class}"><div class="label">Błędy</div><div class="value">{error_count}</div></div>
          <div class="tg-metric"><div class="label">Czas trwania</div><div class="value">{duration}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if result['total'] == 0:
        st.warning('Brak produktów ze zdjęciami do pobrania.')
    elif error_count and result['saved'] == 0:
        st.error('Nie udało się pobrać żadnego zdjęcia.')
    elif error_count:
        st.warning('Eksport zakończony z częściowymi błędami.')
    else:
        st.success('Eksport zakończony pomyślnie.')

    if result['errors']:
        with st.expander(f'Szczegóły błędów ({error_count})'):
            for msg in result['errors']:
                st.write(msg)

    st.markdown(f'<p class="tg-info">Folder docelowy: {result["output_dir"]}</p>', unsafe_allow_html=True)


@st.cache_resource
def get_image_server():
    """Jedna instancja serwera dla całego procesu — przeżywa reruny Streamlita."""
    return ImageServer()


def render_server_section(output_dir_text):
    """Sekcja GUI: uruchamianie/zatrzymywanie serwera HTTP hostującego zdjęcia."""
    server = get_image_server()

    st.divider()
    st.subheader('Hosting zdjęć (HTTP)')
    st.caption(
        f'Udostępnia pliki z folderu docelowego pod adresem {public_image_example_url()} '
        '— np. do wyświetlania w Excelu.'
    )

    if IS_PRODUCTION_HOST:
        st.info(
            'Na serwerze produkcyjnym serwer HTTP startuje automatycznie z kontenerem '
            f'(folder: {output_dir_text.strip() or DEFAULT_OUTPUT_DIR}).'
        )
        return

    port = st.number_input('Port serwera', min_value=1, max_value=65535, value=DEFAULT_SERVER_PORT, step=1)

    col_start, col_stop = st.columns(2)
    start_server = col_start.button('Uruchom hosting', type='primary')
    stop_server = col_stop.button('Zatrzymaj hosting', disabled=not server.is_running)

    if start_server:
        try:
            server.start(Path(output_dir_text.strip() or str(DEFAULT_OUTPUT_DIR)), int(port))
            st.rerun()
        except OSError as e:
            st.error(str(e))

    if stop_server:
        server.stop()
        st.rerun()

    if server.is_running:
        st.success(f'Serwer działa: {server.base_url}/ (folder: {server.directory})')
        sample = next(server.directory.glob('*.jpg'), None)
        if sample:
            st.markdown(f'Przykładowy link: [{server.base_url}/{sample.name}]({server.base_url}/{sample.name})')
    else:
        st.markdown('<p class="tg-info">Serwer zatrzymany.</p>', unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_title='Eksport zdjęć produktów',
        page_icon=str(LOGO_PATH),
        layout='centered',
    )
    st.markdown(TG_CSS, unsafe_allow_html=True)

    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    st.markdown(
        f"""
        <div class="tg-header">
          <img src="data:image/png;base64,{logo_b64}" alt="Trend Glass">
          <div>
            <h1>Eksport zdjęć produktów</h1>
            <p>Creatio CRM → JPG {core.IMAGE_TARGET_WIDTH}×{core.IMAGE_TARGET_HEIGHT}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not all([core.base_uri, core.base_uri_is, core.client_id, core.client_secret, core.grant_type]):
        st.error('Brak wymaganych zmiennych środowiskowych w pliku .env — uzupełnij konfigurację i odśwież stronę.')
        st.stop()

    codes_text = st.text_input(
        'Filtr kodów produktów',
        value=core.os.getenv('PRODUCT_CODES', '').strip(),
        help='Kody rozdzielone przecinkami. Puste pole = wszystkie produkty ze zdjęciami.',
    )
    output_dir_text = st.text_input('Folder docelowy', value=str(DEFAULT_OUTPUT_DIR))

    start = st.button('Rozpocznij eksport', type='primary')
    progress_area = st.container()

    if start:
        output_dir = Path(output_dir_text.strip() or str(DEFAULT_OUTPUT_DIR))
        try:
            st.session_state['result'] = run_export(parse_codes(codes_text), output_dir, progress_area)
        except Exception as e:
            st.error(f'Eksport przerwany błędem: {e}')

    if 'result' in st.session_state:
        render_summary(st.session_state['result'])

    render_server_section(output_dir_text)


main()
