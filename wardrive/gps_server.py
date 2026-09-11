#!/usr/bin/env python3
"""Standalone phone-GPS feed server for headless wardriving.

Headless port of the HTTPS server wardriver_tui.py runs on :8888 so a phone
browser can stream GPS fixes into a WardriveSession:

    https://<pi>:PORT/            the phone configuration page (start/stop GPS)
         /gps/batch               POST {fixes:[{lat,lon,acc,alt,spd,hdg,t}]}
         /gps                     GET ?lat=&lon=&acc=  (legacy single fix)
         /gps/ping                heartbeat from the phone (armed + queue)
         /gps/stop                phone session finished

The page and the fix ingestion are byte-for-byte behaviour-compatible with the
TUI so any phone that works there works here. The only difference is there is
no Textual app instance to notify, so "phone contact" is tracked on the class
itself and polled by the headless runner.
"""
import json
import logging
import os
import ssl
import subprocess
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from wardriver import ClockSync
from gps_page import render_page

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get("WARDRIVER_PORT", "8888"))
PHONE_LINK_TIMEOUT = 16.0


def make_cert(cert_dir):
    """Reuse or create the self-signed cert the phone must accept once."""
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(exist_ok=True, parents=True)
    cert = cert_dir / "cert.pem"
    key = cert_dir / "key.pem"
    if cert.exists() and key.exists():
        return str(cert), str(key)
    try:
        subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
             '-keyout', str(key), '-out', str(cert), '-days', '365',
             '-nodes', '-subj', '/CN=wardriver'],
            timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return (str(cert), str(key)) if cert.exists() and key.exists() else None


class GPSFeedServer(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'  # keep-alive; the phone polls constantly

    # Injected by the headless runner (class-wide so the HTTP threads can see
    # the session fields without a Textual app round-trip).
    session = None
    clock = ClockSync()
    last_contact = 0.0            # time.monotonic() of last phone word
    phone_stopped = False
    _contact_lock = threading.Lock()

    # -- helpers -------------------------------------------------------------

    def _reply(self, code, body=b'', ctype='text/plain'):
        self.send_response(code)
        self.send_header('Content-type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _record(self, fixes, arrival):
        """Hand a batch of phone fixes to the session, correctly timed."""
        if not fixes:
            return
        gps = self.session.gps
        # Phone timestamps are epoch milliseconds; a fix without one falls
        # back to arrival, which is the old single-fix behaviour.
        remote = [(f['t'] / 1000.0 if f.get('t') else None) for f in fixes]
        known = [t for t in remote if t is not None]
        stamped = dict(zip([i for i, t in enumerate(remote) if t is not None],
                           self.clock.stamp(known, arrival))) if known else {}

        for i, f in enumerate(fixes):
            gps.set_location(
                f['lat'], f['lon'], f.get('acc'),
                altitude=f.get('alt'), speed=f.get('spd'), heading=f.get('hdg'),
                source='phone', at=stamped.get(i, arrival),
            )
        with self._contact_lock:
            type(self).last_contact = time.monotonic()

    @staticmethod
    def _coerce(raw):
        """Validate one incoming fix, or None if it is unusable."""
        try:
            lat = float(raw['lat'])
            lon = float(raw['lon'])
        except (KeyError, TypeError, ValueError):
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        def opt(key):
            v = raw.get(key)
            if v is None or v == '':
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return {'lat': lat, 'lon': lon, 'acc': opt('acc'), 'alt': opt('alt'),
                'spd': opt('spd'), 'hdg': opt('hdg'), 't': opt('t')}

    # -- routes --------------------------------------------------------------

    def do_POST(self):
        arrival = time.monotonic()
        if self.path != '/gps/batch':
            self._reply(404, b'not found')
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self._reply(400, b'bad length')
            return
        if length <= 0 or length > 1_000_000:
            self._reply(400, b'bad length')
            return
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            incoming = payload.get('fixes') or []
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            logger.warning("bad /gps/batch body: %s", exc)
            self._reply(400, b'bad json')
            return

        fixes = [f for f in (self._coerce(r) for r in incoming) if f]
        if len(fixes) != len(incoming):
            logger.warning("dropped %d malformed fix(es)",
                           len(incoming) - len(fixes))
        self._record(fixes, arrival)
        self._reply(200, b'OK')

    def do_GET(self):
        arrival = time.monotonic()
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == '/gps':
            params = urllib.parse.parse_qs(parsed.query)
            flat = {k: v[0] for k, v in params.items() if v}
            fix = self._coerce(flat)
            if fix is None:
                logger.warning("bad /gps request %r", self.path)
                self._reply(400, b'bad coordinates')
                return
            self._record([fix], arrival)
            self._reply(200, b'OK')
            return

        if route == '/gps/ping':
            with self._contact_lock:
                type(self).last_contact = time.monotonic()
            self._reply(200, b'OK')
            return

        if route == '/gps/stop':
            with self._contact_lock:
                type(self).phone_stopped = True
                type(self).last_contact = time.monotonic()
            self._reply(200, b'OK')
            return

        if route in ('/', ''):
            self._reply(200, render_page(), 'text/html; charset=utf-8')
            return

        self._reply(404, b'not found')

    def log_message(self, format, *args):
        pass


def start_server(session, port, cert_dir, tls=True):
    """Start the GPS feed server on its own thread. Returns the URL + server."""
    GPSFeedServer.session = session
    # 0.0 (not "now") so a phone has to actually talk to us before the UI
    # reports the link as up — merely starting the server proves nothing.
    GPSFeedServer.last_contact = 0.0
    GPSFeedServer.phone_stopped = False
    srv = ThreadingHTTPServer(('0.0.0.0', port), GPSFeedServer)
    if tls:
        cas = make_cert(cert_dir)
        if cas:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cas[0], cas[1])
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Scheme = 'https' if tls else 'http'
    return f"{Scheme}://<host>:{port}/", srv


def link_is_up():
    """True if the phone has talked to us recently enough to trust its fixes."""
    with GPSFeedServer._contact_lock:
        last = GPSFeedServer.last_contact
    return bool(last) and (time.monotonic() - last) <= PHONE_LINK_TIMEOUT