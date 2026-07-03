"""Lekki serwer HTTP hostujący pobrane zdjęcia produktów.

Serwuje wskazany folder (np. product_images) pod http://<host>:<port>/<plik>.jpg,
dzięki czemu zdjęcia można linkować np. w Excelu. Oparty wyłącznie na bibliotece
standardowej; nasłuchuje na 0.0.0.0 (dostęp z sieci LAN, gotowe pod Docker).
"""

import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Server(ThreadingHTTPServer):
    # Na Windows SO_REUSEADDR pozwala zbindować zajęty port bez błędu,
    # więc wyłączamy je tam; na Linuksie jest potrzebne do szybkiego restartu.
    allow_reuse_address = os.name != 'nt'


def get_host_address():
    """Zwraca adres IP maszyny widoczny w sieci lokalnej (fallback: hostname)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostname()


def get_public_base_url(port=None):
    """Publiczny URL serwera zdjęć (nginx) lub lokalny adres IP:port."""
    public = os.getenv('PUBLIC_IMAGE_BASE_URL', '').strip().rstrip('/')
    if public:
        return public
    if port is None:
        port = int(os.getenv('IMAGE_SERVER_PORT', '8000'))
    return f'http://{get_host_address()}:{port}'


class ImageServer:
    """Zarządza cyklem życia serwera HTTP serwującego folder ze zdjęciami."""

    def __init__(self):
        self._server = None
        self._thread = None
        self._directory = None
        self._port = None

    @property
    def is_running(self):
        return self._server is not None

    @property
    def port(self):
        return self._port

    @property
    def directory(self):
        return self._directory

    @property
    def base_url(self):
        if not self.is_running:
            return None
        return get_public_base_url(self._port)

    def start(self, directory, port):
        """Uruchamia serwer w wątku daemon; restartuje, jeśli już działa."""
        if self.is_running:
            self.stop()

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
        try:
            self._server = _Server(('0.0.0.0', port), handler)
        except OSError as e:
            self._server = None
            raise OSError(f'Nie można uruchomić serwera na porcie {port}: {e}') from e

        self._directory = directory
        self._port = port
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f'image-server-{port}',
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Zatrzymuje serwer i zwalnia port."""
        if not self.is_running:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        self._directory = None
        self._port = None
