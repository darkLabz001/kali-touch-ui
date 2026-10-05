"""Local touchscreen browser launcher; accepts named destinations only."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
from device import handle_device_request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SITES = {'discord': 'https://discord.com/app', 'reddit': 'https://www.reddit.com/',
         'youtube': 'https://www.youtube.com/'}
_lock = threading.Lock()
_process = None


def handle_entertainment_request(handler, path):
    global _process
    if path != '/api/entertainment/open':
        return False

    def reply(code, **body):
        handler._send(code, json.dumps(body).encode())
        return True

    host = handler.headers.get('Host', '')
    origin = handler.headers.get('Origin', '')
    if (handler.client_address[0] not in ('127.0.0.1', '::1')
            or host.split(':')[0] not in ('127.0.0.1', 'localhost')
            or origin not in ('http://127.0.0.1:8080', 'http://localhost:8080')
            or handler.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
        return reply(403, error='Open Social on the device touchscreen.')
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 256:
            raise ValueError()
        body = json.loads(handler.rfile.read(length))
        site = body.get('site') if isinstance(body, dict) else None
        if not isinstance(site, str) or site not in SITES:
            raise ValueError()
    except (ValueError, UnicodeError):
        return reply(400, error='Choose a supported social app.')
    with _lock:
        if _process is not None and _process.poll() is None:
            return reply(409, error='A social browser is already open. Use Back to Kali first.')
        env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':0'),
                   XAUTHORITY=str(Path.home() / '.Xauthority'),
                   DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/%s/bus' % os.getuid())
        try:
            _process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/social_browser.py'), site],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            ready, _, _ = select.select([_process.stdout], [], [], 8)
            ok = bool(ready) and _process.stdout.readline().strip() == b'READY'
            _process.stdout.close()
            if not ok:
                _process.terminate()
                return reply(503, error='Browser could not start. Check the desktop session and Chromium installation.')
        except OSError:
            return reply(503, error='Browser launcher is unavailable on this device.')
    return reply(200, ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send(self, status, body):
        self.send_response(status)
        origin = self.headers.get('Origin', '')
        if origin in ('http://127.0.0.1:8080', 'http://localhost:8080'):
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self.headers.get('Origin', '')
        if origin not in ('http://127.0.0.1:8080', 'http://localhost:8080'):
            self._send(403, b'{}'); return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if not handle_device_request(self, 'GET', self.path):
            self._send(404, b'{}')

    def do_POST(self):
        if handle_device_request(self, 'POST', self.path):
            return
        if not handle_entertainment_request(self, self.path):
            self._send(404, b'{}')


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8082), Handler).serve_forever()
