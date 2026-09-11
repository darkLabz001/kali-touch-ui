#!/usr/bin/env python3
"""Wardriver headless drive runner for the Kali Touch UI.

Spawned (as root, so `iw scan` works) by the touch backend. Every status
update is one line of JSON on stdout so the backend can stream it to the UI
without a Textual front end:

    {"event":"boot","port":8888,"out":"...csv","iface":"wlan1","gps_url":"https://<host>:8888/"}
    {"event":"scan","cycle":1,"wifi":14,"total":14,"located":0,
     "gps":"none|fresh|stale","phone":"up|down","lat":..,"lon":..}
    {"event":"error","msg":"..."}
    {"event":"done","total":14,"out":"..."}

The phone GPS page (gps_page.py) is served on HTTPS :8888; scan the QR shown
by the touch UI with a phone, keep the tab open, and fixes stream in.
"""
import argparse
import json
import logging
import os
import pwd
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# This module only matters if a Pi is missing bits; log to a file rather than
# corrupting the JSON protocol on stdout.
_LOGGING = logging.getLogger(__name__)


def _user_home():
    """HOME of the human user even when we were started via `sudo -n`."""
    sudo = os.environ.get("SUDO_USER")
    if sudo:
        try:
            return Path(pwd.getpwnam(sudo).pw_dir)
        except KeyError:
            pass
    return Path.home()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default=None, help="wifi iface to scan (e.g. wlan1)")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("WARDRIVER_PORT", "8888")))
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--manual", default=None, metavar="LAT,LON",
                    help="pin a static position instead of phone GPS")
    ap.add_argument("--ble", action="store_true", help="also sweep BLE (needs bleak)")
    ap.add_argument("--home", default=None, help="data dir home (default: real user)")
    args = ap.parse_args()

    home = Path(args.home) if args.home else _user_home()
    data_dir = home / ".wardriver"
    data_dir.mkdir(parents=True, exist_ok=True)

    # wardriver.py installs a stderr handler at import time; force logging to
    # the file so stderr/stdout stay clean for our JSON protocol.
    logging.basicConfig(
        level=logging.INFO,
        filename=str(data_dir / "headless.log"),
        filemode="a",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    _LOGGING.info("headless wardriver starting via %s", sys.argv)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wardriver import WardriveSession
    import gps_server as gpsmod

    # A scan NIC that NM parked (no connection) sits admin-down; `iw scan`
    # then dies with "Network is down". Bring it up so the vector radio is
    # ready even before/without a network-manager connection.
    if args.iface:
        subprocess.run(["ip", "link", "set", args.iface, "up"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _LOGGING.info("ensure %s up", args.iface)

    if args.manual:
        try:
            mlat, mlon = [float(x.strip()) for x in args.manual.split(",")]
        except (ValueError, TypeError):
            print(json.dumps({"event": "error",
                              "msg": "manual position must be LAT,LON"}), flush=True)
            return 2
    else:
        mlat = mlon = None

    session = WardriveSession(wifi_ifname=args.iface)
    if mlat is not None:
        session.gps.set_location(mlat, mlon, accuracy=10.0, manual=True,
                                 source='manual')

    scans = data_dir / "scans"
    scans.mkdir(exist_ok=True)
    out = scans / ("wardriving_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    session.start_autosave(out)
    _LOGGING.info("autosaving to %s", out)

    # The QR page is the routing point for the whole drive: without it the
    # phone has nowhere to POST fixes. TLS only if openssl is available to
    # mint the self-signed cert the phone accepts once.
    tls = subprocess.run(["sh", "-c", "command -v openssl"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL).returncode == 0
    try:
        gps_url, srv = gpsmod.start_server(session, args.port, data_dir, tls=tls)
    except OSError as exc:
        print(json.dumps({"event": "error",
                          "msg": "could not bind GPS server on :%s: %s"
                                 % (args.port, exc)}), flush=True)
        gps_url, srv = None, None

    print(json.dumps({
        "event": "boot",
        "port": args.port,
        "iface": session.wifi_scanner.ifname or "auto",
        "out": str(out),
        "tls": tls,
        "gps_url": gps_url,  # host placeholder replaced by the backend
        "manual": mlat is not None,
    }), flush=True)

    stop = threading.Event()

    def _term(signum, _frame):
        _LOGGING.info("caught signal %s; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    cycle = 0
    first_err = True
    while not stop.is_set():
        try:
            networks = session.wifi_scanner.scan()
            session.session_data["networks"].extend(networks)
            session._queue_for_location(networks)
            devices = []
            if args.ble and not stop.is_set():
                devices = session.scan_ble_once(8)
            if not networks and not devices and stop.is_set():
                break
        except Exception as exc:
            if first_err:
                print(json.dumps({"event": "error", "msg": repr(exc)}), flush=True)
                first_err = False
            _LOGGING.exception("scan cycle failed")
            if stop.wait(args.interval):
                break
            continue
        first_err = True
        cycle += 1

        gps = session.gps
        fix = gps.last_fix
        if mlat is not None:
            gstate = "fresh"
            phone = "manual"
        elif fix is None:
            gstate = "none"
            phone = "wait"
        else:
            stale = (time.monotonic() - fix.at) > gps.max_fix_age
            phone = "up" if gpsmod.link_is_up() else "down"
            gstate = "stale" if stale else "fresh"

        located = sum(
            1 for n in session.session_data["networks"]
            if n.latitude is not None and n.longitude is not None)

        print(json.dumps({
            "event": "scan",
            "cycle": cycle,
            "wifi": len(networks),
            "total": len(session.session_data["networks"]),
            "located": located,
            "ble": len(devices),
            "gps": gstate,
            "phone": phone,
            "lat": fix.latitude if fix else None,
            "lon": fix.longitude if fix else None,
            "acc": fix.accuracy if fix else None,
        }), flush=True)

        if stop.wait(args.interval):
            break

    try:
        session.close_autosave()
    except Exception as exc:
        _LOGGING.exception("autosave close failed: %s", exc)
    print(json.dumps({
        "event": "done",
        "total": len(session.session_data["networks"]),
        "out": str(out),
    }), flush=True)
    _LOGGING.info("headless wardriver exiting cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())