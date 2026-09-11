#!/usr/bin/env python3
"""Kali Touch UI - stdlib-only backend (no pip installs needed on the Pi)."""
import csv
import fcntl
import glob
import json
import os
import platform
import pty
import re
import select
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import termios
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
ROOT = os.path.realpath(ROOT)
HOST = "0.0.0.0"
PORT = int(os.environ.get("TOUCHUI_PORT", "8080"))

# Tool registry: (section, label, command builder, needs-root, category)
TOOLS = [
    # Network scanning
    ("scan", "Nmap Quick", "nmap -Pn -T4 -oN - {target}", False),
    ("scan", "Nmap Syn Scan", "nmap -sS -Pn -T4 {target}", True),
    ("scan", "Nmap Full Ports", "nmap -p- -Pn {target}", False),
    ("scan", "Netdiscover", "netdiscover -r {target}", True),
    ("scan", "Masscan", "masscan {target} -p1-65535 --rate 1000", True),
    ("scan", "Arp Scan (arp-scan)", "arp-scan --localnet", True),
    ("recon", "Ping Sweep", "nmap -sn {target}", False),
    ("recon", "DNS Recon", "dnsrecon -d {target}", False),
    ("recon", "DNS Enum", "dnsenum {target}", False),
    ("recon", "WhatWeb", "whatweb -v {target}", False),
    ("recon", "theHarvester", "theHarvester -d {target} -b all", False),
    ("recon", "Nslookup", "nslookup {target}", False),
    # Web
    ("web", "sqlmap", "sqlmap -u {target} --batch --crawl 1", False),
    ("web", "Nikto", "nikto -h {target}", False),
    ("web", "DirBuster (dirb)", "dirb {target}", False),
    ("web", "Gobuster Dir", "gobuster dir -u {target} -w /usr/share/wordlists/dirb/common.txt", False),
    ("web", "Gobuster Vhost", "gobuster vhost -u {target} -w /usr/share/wordlists/dirb/common.txt", False),
    ("web", "FFUF", "ffuf -u {target}/FUZZ -w /usr/share/wordlists/dirb/common.txt", False),
    ("web", "WFuzz Dir", "wfuzz -c -z file,/usr/share/wordlists/dirb/common.txt --hc 404 {target}/FUZZ", False),
    ("web", "WPScan", "wpscan --url {target} --no-banner", False),
    ("web", "WPScan Enumerate", "wpscan --url {target} --enumerate u,vp --no-banner", False),
    # Credential / brute (wordlist picks rockyou / SecLists automatically)
    ("auth", "Hydra SSH", "hydra -L /tmp/users.txt -P {wordlist} ssh://{target}", False),
    ("auth", "Hydra FTP", "hydra -L /tmp/users.txt -P {wordlist} ftp://{target}", False),
    ("auth", "Hydra MySQL", "hydra -L /tmp/users.txt -P {wordlist} mysql://{target}", False),
    ("auth", "Hydra RDP", "hydra -L /tmp/users.txt -P {wordlist} rdp://{target}", False),
    ("auth", "Hydra HTTP POST", "hydra -L /tmp/users.txt -P {wordlist} http-post-form \"{target}/login:user=^USER^&pass=^PASS^:F=incorrect\"", False),
    ("auth", "Ncrack RDP", "ncrack -p 3389 {target}", True),
    ("auth", "Medusa RDP", "medusa -h {target} -U /tmp/users.txt -P {wordlist} -M rdp -n 3389 -t 3", True),
    ("auth", "SMB Password Spray", "crackmapexec smb {target} -u /tmp/users.txt -p {pass}", True),
    # Wireless
    ("wireless", "airmon-ng start", "airmon-ng start {target}", True),
    ("wireless", "airodump-ng", "airodump-ng {target}", True),
    ("wireless", "aircrack-ng", "aircrack-ng {target}", False),
    ("wireless", "Reaver", "reaver -i {target} -b {bssid} -vv", True),
    # SMB / Windows
    ("smb", "Enum4linux", "enum4linux {target}", False),
    ("smb", "smbclient list", "smbclient -L //{target}", False),
    ("smb", "evil-winrm", "evil-winrm -i {target} -u {user} -p {pass}", False),
    # Misc
    ("util", "Tcpdump", "tcpdump -i {target} -nn", True),
    ("util", "Ping", "ping -c 4 {target}", False),
    ("util", "Traceroute", "traceroute {target}", True),
    ("util", "ip a", "ip a", False),
    ("util", "ss (ports)", "ss -tulpn", True),
    ("util", "whois", "whois {target}", False),
    ("util", "dig", "dig {target} any", False),
    ("util", "curl", "curl -sI {target}", False),
    ("util", "iwlist scan", "iwlist {target} scan", True),
    # Password cracking (rockyou / SecLists via {wordlist}, {hashmode})
    ("crack", "John Auto Detect", "john --wordlist={wordlist} {target}", False),
    ("crack", "John Single Mode", "john --single {target}", False),
    ("crack", "John Show Results", "john --show {target}", False),
    ("crack", "Hashcat Wordlist", "hashcat -m {hashmode} -a 0 {target} {wordlist}", False),
    ("crack", "Hashcat Mask", "hashcat -m {hashmode} -a 3 {target} ?a?a?a?a?a?a?a?a", False),
    ("crack", "Hashcat + Rule (best64)", "hashcat -m {hashmode} -a 0 {target} {wordlist} -r /usr/share/hashcat/rules/best64.rule", False),
    ("crack", "Hashcat Show Potfile", "hashcat -m {hashmode} --show {target}", False),
    ("crack", "Crunch Gen Wordlist", "crunch {target} 26 -o /tmp/crunch.txt", False),
    ("crack", "Hydra SSH (dict)", "hydra -L /tmp/users.txt -P {wordlist} ssh://{target}", False),
]

SECTIONS = [
    ("scan", "Network Scan", "radar"),
    ("recon", "Recon & DNS", "search"),
    ("web", "Web Attacks", "globe"),
    ("auth", "Brute Force", "key"),
    ("wireless", "WiFi Attacks", "wifi"),
    ("crack", "Password Crack", "lock"),
    ("smb", "SMB / Win", "shield"),
    ("util", "Utility", "tool"),
]

# Click-to-run tools: (id, group, label, icon, binary, needs-root, apt package)
INTERACTIVE = [
    ("wifite", "WiFi", "WiFite — auto attack", "✱", "wifite", True, "wifite"),
    ("airmon", "WiFi", "Airmon-ng — monitor mode", "✱", "airmon-ng", True, "aircrack-ng"),
    ("airodump", "WiFi", "Airodump-ng — handshake capture", "◉", "airodump-ng", True, "aircrack-ng"),
    ("aireplay", "WiFi", "Aireplay-ng — deauth/inject", "✱", "aireplay-ng", True, "aircrack-ng"),
    ("aircrack", "WiFi", "Aircrack-ng — crack handshake", "❋", "aircrack-ng", False, "aircrack-ng"),
    ("reaver", "WiFi", "Reaver — WPS attack", "❋", "reaver", True, "reaver"),
    ("bully", "WiFi", "Bully — WPS attack", "❋", "bully", True, "bully"),
    ("pixiewps", "WiFi", "PixieWPS", "❋", "pixiewps", False, "pixiewps"),
    ("hcxdumptool", "WiFi", "Hcxdumptool — PMKID/PMK sniff", "◉", "hcxdumptool", True, "hcxtools"),
    ("hcxpcapngtool", "WiFi", "Hcxpcaptool — convert to hash", "❋", "hcxpcapngtool", False, "hcxtools"),
    ("wifiphisher", "WiFi", "Wifiphisher — evil twin", "⚑", "wifiphisher", True, "wifiphisher"),
    ("airgeddon", "WiFi", "Airgeddon — multi attack", "⚑", "airgeddon", True, "airgeddon"),
    ("kismet", "WiFi", "Kismet — wardriving", "◉", "kismet", True, "kismet"),
    ("macchanger", "WiFi", "Macchanger — spoof MAC", "⚒", "macchanger", True, "macchanger"),
    ("bettercap", "BLE", "Bettercap — BLE / MITM", "◆", "bettercap", True, "bettercap"),
    ("bluetoothctl", "BLE", "Bluetoothctl", "◉", "bluetoothctl", False, "bluez"),
    ("btmon", "BLE", "Btmon — BLE sniffer", "◉", "btmon", True, "bluez"),
    ("hciconfig", "BLE", "Hciconfig", "◉", "hciconfig", True, "bluez"),
    ("nmap", "Net", "Nmap", "◎", "nmap", False, "nmap"),
    ("tcpdump", "Net", "Tcpdump — packet capture", "◉", "tcpdump", True, "tcpdump"),
    ("tshark", "Net", "Tshark — Wireshark CLI", "◉", "tshark", False, "tshark"),
    ("ncat", "Net", "Ncat", "◆", "ncat", False, "nmap"),
    ("responder", "Net", "Responder — LLMNR/NBT", "◆", "responder", True, "responder"),
    ("netexec", "Net", "Netexec (crackmapexec)", "◆", "netexec", True, "netexec"),
    ("evil-winrm", "Net", "Evil-WinRM", "◆", "evil-winrm", False, "evil-winrm"),
    ("smbclient", "Net", "Smbclient", "◆", "smbclient", False, "smbclient"),
    ("msfconsole", "Net", "Metasploit", "⚑", "msfconsole", False, "metasploit-framework"),
    ("sqlmap", "Web", "Sqlmap", "◎", "sqlmap", False, "sqlmap"),
    ("gobuster", "Web", "Gobuster", "◎", "gobuster", False, "gobuster"),
    ("nikto", "Web", "Nikto", "◎", "nikto", False, "nikto"),
    ("wpscan", "Web", "WPScan", "◎", "wpscan", False, "wpscan"),
    ("theharvester", "Web", "theHarvester — OSINT", "◎", "theHarvester", False, "theharvester"),
    ("hydra", "Auth", "Hydra — brute force", "❋", "hydra", False, "hydra"),
    ("medusa", "Auth", "Medusa — brute force", "❋", "medusa", False, "medusa"),
    ("ncrack", "Auth", "Ncrack — brute force", "❋", "ncrack", False, "ncrack"),
    ("hashid", "Crack", "Hashid — identify hashes", "❋", "hashid", False, "hashid"),
    ("hashcat", "Crack", "Hashcat", "❋", "hashcat", False, "hashcat"),
    ("john", "Crack", "John the Ripper", "❋", "john", False, "john"),
    ("crunch", "Crack", "Crunch — gen wordlist", "❋", "crunch", False, "crunch"),
    ("exiftool", "Crack", "ExifTool — metadata", "❋", "exiftool", False, "libimage-exiftool-perl"),
]

LAUNCH_GROUPS = ["WiFi", "BLE", "Net", "Web", "Auth", "Crack"]

INSTALL_LOG = "/tmp/kali-ui-install.log"

SAFE_PATTERNS = re.compile(r"^[A-Za-z0-9._:/:\[\]-]+$")
bssid = ""

# Default wordlists to prefer for password attacks (rockyou / SecLists).
DEFAULT_WORDLISTS = [
    "/usr/share/wordlists/rockyou.txt",
    "/usr/share/seclists/Passwords/Common-Credentials/10k-most-common.txt",
    "/usr/share/seclists/Passwords/Common-Credentials/rockyou-75.txt",
    "/usr/share/john/password.lst",
    "/usr/share/wordlists/metasploit/default_pass_for_services_unhash.txt",
]


def _scan_wordlists(base, max_depth=1, cap=80):
    res = []
    if not os.path.isdir(base):
        return res

    def walk(d, depth):
        if len(res) >= cap:
            return
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            return
        for ent in entries:
            p = os.path.join(d, ent)
            if os.path.isfile(p) and ent.endswith(".txt") and os.path.getsize(p) > 0 and " " not in ent:
                res.append((p, ent))
            elif os.path.isdir(p) and depth < max_depth and not ent.startswith("."):
                walk(p, depth + 1)
            if len(res) >= cap:
                return

    walk(base, 0)
    return res


def find_wordlists():
    """Return available dictionary files for the UI picker."""
    paths = []
    paths += _scan_wordlists("/usr/share/wordlists")
    paths += _scan_wordlists("/usr/share/seclists", max_depth=2, cap=100)
    paths += _scan_wordlists("/usr/share/john")
    for p in DEFAULT_WORDLISTS:
        if os.path.isfile(p) and all(p != x[0] for x in paths):
            paths.append((p, os.path.basename(p)))
    if not paths:
        paths.append((DEFAULT_WORDLISTS[0], "rockyou.txt"))
    seen = set()
    out = []
    for p, name in paths:
        if p not in seen:
            seen.add(p)
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            out.append({"path": p, "name": name, "size": size})
    return out


def default_wordlist():
    for p in DEFAULT_WORDLISTS:
        if os.path.isfile(p):
            return p
    lists = [w["path"] for w in find_wordlists()]
    return lists[0] if lists else "/usr/share/wordlists/rockyou.txt"


DEFAULT_USERS = ["root", "admin", "administrator", "user", "guest", "kali",
                 "test", "oracle", "pi", "ubuntu", "support", "manager"]


def ensure_users_file():
    if not os.path.exists("/tmp/users.txt"):
        with open("/tmp/users.txt", "w") as f:
            f.write("\n".join(DEFAULT_USERS) + "\n")


# ---------------------------------------------------------------
# WiFi + system settings helpers
# ---------------------------------------------------------------

def _run(cmd, timeout=10):
    """Run a command and return (code, stdout). Never uses a shell."""
    try:
        p = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout
    except Exception as e:
        return -1, str(e)


def _run_args(args, timeout=10):
    """Like _run but takes a pre-split argv list (safe for names with spaces)."""
    try:
        p = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        return -1, str(e)


def _wifi_iface():
    rc, out = _run("iw dev")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Interface"):
            return line.split()[-1]
    # prefer a wireless interface from /sys/class/net
    try:
        for name in os.listdir("/sys/class/net"):
            wpath = "/sys/class/net/%s/wireless" % name
            if os.path.isdir(wpath):
                return name
    except OSError:
        pass
    return None


def _ipv4():
    ip = None
    try:
        host = socket.gethostname()
        for addr in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = addr[4][0]
            if not ip.startswith("127."):
                break
    except Exception:
        pass
    if not ip or ip.startswith("127."):
        try:
            rc, out = _run("ip -4 addr show scope global")
            import re as _re
            m = _re.search(r"inet\s+([0-9.]+)", out)
            if m:
                ip = m.group(1)
        except Exception:
            pass
    return ip or ""


def sysinfo():
    info = get_network_info()
    I = info.get("wifi_iface")
    if I and I != "none detected":
        rc, out = _run("iw dev %s link" % I)
        for m in re.finditer(r"SSID: (.+)", out):
            info["ssid"] = m.group(1).strip()
            break
    else:
        info["ssid"] = ""
    info.setdefault("ssid", "")
    rc, out = _run("vcgencmd measure_temp")
    info["temp"] = ""
    if rc == 0:
        m = re.search(r"[0-9.]+", out)
        if m:
            info["temp"] = m.group(0)
    try:
        with open("/proc/loadavg") as f:
            info["load"] = f.read().split()[0]
    except IOError:
        info["load"] = ""
    try:
        with open("/proc/meminfo") as f:
            tot = av = 0
            for line in f:
                parts = line.split()
                if parts[0] == "MemTotal:":
                    tot = int(parts[1])
                elif parts[0] == "MemAvailable:":
                    av = int(parts[1])
            info["mem"] = "%d%%" % (100 * (tot - av) // tot) if tot else ""
    except IOError:
        info["mem"] = ""
    return info


def get_network_info():
    info = {
        "hostname": socket.gethostname(),
        "os": "Kali Linux " + platform.release(),
        "ip": _ipv4(),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "uptime": "",
    }
    rc, out = _run("uptime -p")
    if rc == 0:
        info["uptime"] = out.strip()
    # ip link shows which interfaces have a carrier / are up
    iface = _wifi_iface()
    info["wifi_iface"] = iface if iface else "none detected"
    return info


def parse_iwlist_scan(out):
    """Parse `iwlist <iface> scan` output into a list of network dicts."""
    nets = []
    cur = None

    def flush():
        pass

    def push():
        nonlocal cur
        if cur and cur.get("essid") is not None and cur["essid"] != "":
            nets.append(cur)
        cur = None

    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Cell") or line.startswith("BSS"):
            push()
            cur = {"essid": None, "bssid": None, "quality": 0.0, "signal": None, "enc": "Open", "channel": None}
            m = re.search(r"Address: ([0-9A-Fa-f:]+)", line)
            if m:
                cur["bssid"] = m.group(1).upper()
            continue
        if cur is None:
            continue
        low = line.lower()
        if "essid:" in low:
            essid = line.split(":", 1)[1].strip().strip('"')
            cur["essid"] = essid
        elif "freq:" in low:
            m = re.search(r"Channel\s*([0-9]+)", line)
            if m:
                cur["channel"] = m.group(1)
        elif "signal level" in low or "level=" in low:
            m = re.search(r"(-?[0-9]+)\s*dBm", line)
            if m:
                cur["signal"] = m.group(1)
                cur["quality"] = max(0, min(1, (int(m.group(1)) + 100) / 60.0))
        elif "encryption key" in low:
            if "on" in low:
                cur["enc"] = "WPA/WPA2"
            else:
                cur["enc"] = "Open"
        elif "ie:" in low and "wpa" in low and cur["enc"] != "Open":
            pass
    push()
    return nets


def scan_wifi():
    iface = _wifi_iface()
    if not iface:
        return {"networks": [], "error": "no wireless interface found"}
    rc, out = _run("sudo iwlist %s scan" % iface, timeout=30)
    if rc != 0:
        fallback = _run("sudo iw dev %s scan" % iface, timeout=30)
        if fallback[0] == 0:
            out = fallback[1]
        else:
            return {"networks": [], "error": out.strip() or "scan failed (exit %d)" % rc}
    nets = parse_iwlist_scan(out)
    # stable ordering: strongest signal first
    nets.sort(key=lambda n: n["quality"], reverse=True)
    return {"networks": nets, "iface": iface}


def connect_wifi(ssid, password=None):
    ssid = (ssid or "").strip()
    if not ssid:
        return {"ok": False, "error": "no SSID provided"}
    iface = _wifi_iface() or "wlan0"

    # Prefer NetworkManager: connection profiles are saved persistently,
    # so the device reconnects to this network automatically on reboot.
    rc, _ = _run("systemctl is-active NetworkManager")
    if rc == 0:
        res = _nm_connect(ssid, password, iface)
        if res.get("ok"):
            return res
        if res.get("fatal"):
            return res
        # otherwise fall through to wpa_supplicant as a fallback

    # bring interface up, kill existing connections
    _run("sudo ip link set %s up" % iface)
    _run("sudo wpa_cli -i %s disconnect" % iface)
    time.sleep(0.5)

    conf = "/tmp/kali-touch-wpa.conf"
    body = 'ctrl_interface=/run/wpa_supplicant\nnetwork={\n    ssid="%s"\n' % ssid
    if password:
        escaped = password.replace('"', '\\"').replace("\\", "\\\\")
        body += '    psk="%s"\n' % escaped
    else:
        body += "    key_mgmt=NONE\n"
    body += "}\n"
    try:
        with open(conf, "w") as f:
            f.write(body)
    except OSError as e:
        return {"ok": False, "error": "cannot write wpa config: %s" % e}

    cmd = "sudo wpa_supplicant -B -i %s -c %s" % (iface, conf)
    rc, err = _run(cmd, timeout=15)
    if rc != 0:
        return {"ok": False, "error": err.strip() or ("wpa_supplicant failed (%d)" % rc)}

    # wait for association + dhcp
    connected = False
    for _ in range(15):
        time.sleep(1)
        r = _run("sudo wpa_cli -i %s status" % iface)
        if r[0] == 0 and "STATE=COMPLETED" in r[1]:
            connected = True
            break
    if not connected:
        _run("sudo wpa_cli -i %s disconnect" % iface)
        return {"ok": False, "error": "could not associate with %s" % ssid}

    rc2 = _run("sudo dhclient -r %s" % iface)
    _run("sudo dhclient -v %s" % iface, timeout=20)
    return {"ok": True, "ssid": ssid, "ip": _ipv4(), "persistent": False}


def _nm_connect(ssid, password, iface):
    """Connect via NetworkManager. Persists the connection profile on disk."""
    _run_args(["sudo", "nmcli", "radio", "wifi", "on"])
    _run_args(["sudo", "nmcli", "dev", "wifi", "rescan"])
    time.sleep(1)
    args = ["sudo", "nmcli", "-w", "40", "dev", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    rc, err = _run_args(args, timeout=60)
    if rc != 0:
        msg = (err or "").strip().splitlines()
        msg = msg[-1] if msg else "nmcli connect failed"
        # wrong/unsupported psk or auth failures are not "no NetworkManager"
        fatal = any(k in (err or "") for k in ("password", "authentication", "secrets", "invalid"))
        return {"ok": False, "error": msg, "fatal": fatal}
    # wait for an IP
    ip = ""
    for _ in range(15):
        time.sleep(1)
        ip = _ipv4()
        if ip and not ip.startswith("169.254"):
            break
    return {"ok": True, "ssid": ssid, "ip": ip, "persistent": True}


def reboot_device():
    _run("sudo systemctl reboot", timeout=2)
    time.sleep(0.3)
    return {"ok": True}


def shutdown_device():
    _run("sudo systemctl poweroff", timeout=2)
    time.sleep(0.3)
    return {"ok": True}


def sanitize(value):
    value = (value or "").strip().replace(" ", "")
    if not value or not SAFE_PATTERNS.match(value):
        raise ValueError("Unsafe characters in input")
    return value


def find_tool(section, label):
    label = (label or "").strip()
    for s, l, c, r in TOOLS:
        if s == section and l == label:
            return (c, r)
    return None


def build_cmd(params):
    section = sanitize(params.get("section", "util"))
    label = params.get("label", "")
    found = find_tool(section, label)
    if not found:
        raise ValueError("Unknown tool")
    cmd, needs_root = found
    if "{target}" in cmd:
        cmd = cmd.replace("{target}", sanitize(params.get("target")))
    if "{bssid}" in cmd:
        cmd = cmd.replace("{bssid}", sanitize(params.get("bssid", bssid)))
    if "{user}" in cmd:
        cmd = cmd.replace("{user}", sanitize(params.get("user", "admin")))
    if "{pass}" in cmd:
        cmd = cmd.replace("{pass}", sanitize(params.get("pass", "password")))
    if "{wordlist}" in cmd:
        chosen = (params.get("wordlist") or "").strip()
        wl = chosen if chosen else default_wordlist()
        cmd = cmd.replace("{wordlist}", sanitize(wl))
    if "{hashmode}" in cmd:
        hm = (params.get("hashmode") or "0").strip()
        cmd = cmd.replace("{hashmode}", sanitize(hm or "0"))
    if needs_root:
        cmd = "sudo " + cmd
    return cmd


class SSEManager:
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()
        self.proc = None

    def start(self, command):
        with self.lock:
            self.queue = []
        print(f"[run] {command}")
        self.proc = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
        )

    def stop(self):
        if self.proc:
            self.proc.terminate()

    def poll(self):
        with self.lock:
            out = self.queue
            self.queue = []
        return out


SSE = SSEManager()


class TermManager:
    """Interactive bash session on a PTY. Output is pushed to a queue
    drained by the /sse/term endpoint; input comes in via POST."""

    MAX_QUEUE = 400

    def __init__(self):
        self.fd = None
        self.pid = None
        self.queue = []
        self.lock = threading.Lock()
        self.exited = True

    def start(self, shell="/bin/bash", init_cmd=None, cwd=None):
        if not self.exited and self.fd is not None:
            self.stop()
        try:
            home = cwd or (os.path.expanduser("~") or "/")
        except OSError:
            home = "/"
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # child — becomes an interactive shell
            # The backend may have been launched via nohup/& with SIGINT at
            # SIG_IGN; interactive bash then leaves SIGINT ignored for its
            # children, so ^C from the pty would never interrupt commands.
            # Reset dispositions before exec'ing the shell.
            for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU):
                try:
                    signal.signal(sig, signal.SIG_DFL)
                except (ValueError, OSError):
                    pass
            os.chdir(home)
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLUMNS"] = "72"
            os.environ["LINES"] = "30"
            os.execvp(shell, [shell])
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 72, 0, 0))
        except OSError:
            pass
        self.exited = False
        banner = "Kali Touch Terminal - type 'exit' to close, Ctrl+C to interrupt.\r\n\r\n"
        if init_cmd:
            banner = f"▶ running: {init_cmd}\r\n\r\n"
        with self.lock:
            self.queue = [banner.encode()]
        threading.Thread(target=self._reader, daemon=True).start()
        if init_cmd:
            threading.Thread(target=self._prime, args=(init_cmd,), daemon=True).start()
        return True

    def _prime(self, cmd):
        time.sleep(0.6)
        if not self.exited and self.fd is not None:
            try:
                os.write(self.fd, (cmd.rstrip("\r") + "\r").encode("utf-8"))
            except OSError:
                pass

    def _reader(self):
        while not self.exited and self.fd is not None:
            r, _, _ = select.select([self.fd], [], [], 0.1)
            if not r:
                continue
            try:
                data = os.read(self.fd, 4096)
            except OSError:
                self._mark_exit()
                break
            if not data:
                self._mark_exit()
                break
            with self.lock:
                self.queue.append(data)
                if len(self.queue) > self.MAX_QUEUE:
                    del self.queue[: len(self.queue) - self.MAX_QUEUE]
        # reap the child so we don't leave a zombie
        if self.pid:
            try:
                os.waitpid(self.pid, os.WNOHANG)
            except OSError:
                pass

    def _mark_exit(self):
        self.exited = True
        with self.lock:
            if not self.queue or b"[EXITED]" not in self.queue[-1]:
                self.queue.append(b"\r\n[SESSION EXITED - press restart to open a new shell]\r\n")

    def write(self, data):
        if self.fd is None or self.exited:
            return False
        try:
            os.write(self.fd, data.encode("utf-8"))
            return True
        except OSError:
            return False

    def stop(self):
        self.exited = True
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except OSError:
                pass
            try:
                os.waitpid(self.pid, os.WNOHANG)
            except OSError:
                pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None

    def poll(self):
        with self.lock:
            out = self.queue
            self.queue = []
        return out


TERM = TermManager()


RECON_DIR = "/tmp/recon"


def parse_recon_csv(path):
    """Parse airodump-ng CSV into {aps, clients} (PineAP-recon style)."""
    aps, clients = [], []
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            rows = list(csv.reader(f))
    except OSError:
        return {"aps": aps, "clients": clients}
    section = 0
    headers = None
    for r in rows:
        if not r:
            continue
        first = (r[0].strip() if r else "")
        if first.startswith("BSSID") and "channel" in [c.strip().lower() for c in r]:
            headers = r
            section = 1
            continue
        if first.startswith("Station MAC"):
            headers = r
            section = 2
            continue
        if section == 0 or len(r) < len(headers or []):
            continue
        try:
            if section == 1:
                bssid = (r[0] or "").strip()
                if len(bssid) < 12:
                    continue
                aps.append({
                    "bssid": bssid,
                    "first": r[1].strip(), "last": r[2].strip(),
                    "channel": r[3].strip(), "speed": r[4].strip(),
                    "privacy": r[5].strip(), "cipher": r[6].strip(),
                    "auth": r[7].strip(), "power": r[8].strip(),
                    "beacons": r[9].strip(), "iv": r[10].strip(),
                    "lanip": r[11].strip(),
                    "essid": r[13].strip() if len(r) > 13 else "",
                    "key": r[14].strip() if len(r) > 14 else "",
                })
            elif section == 2 and len(r) > 5:
                clients.append({
                    "station": (r[0] or "").strip(),
                    "first": (r[1] or "").strip(), "last": (r[2] or "").strip(),
                    "power": (r[3] or "").strip(), "packets": (r[4] or "").strip(),
                    "bssid": (r[5] or "").strip(),
                    "probes": (r[6] or "").strip() if len(r) > 6 else "",
                })
        except IndexError:
            continue
    return {"aps": aps, "clients": clients}


class ReconManager:
    """PineAP-recon style scanner: airodump-ng in monitor mode with a live
    AP/client table and a rolling scan log."""

    def __init__(self):
        self.proc = None
        self.iface = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def available_iface(self, requested=None):
        def ok(ifc):
            if not ifc:
                return None
            r = subprocess.run(["sudo", "-n", "iw", "dev", ifc, "info"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ifc if r.returncode == 0 else None

        def rank(ifc):
            if ifc == "toolwlan0":
                return 0
            if ifc.startswith("wl") and ifc != "wlan0":
                return 1
            return 2

        if requested:
            found = ok(requested)
            if found:
                return found
        sniff = []
        try:
            for entry in os.listdir("/sys/class/net"):
                if os.path.isdir("/sys/class/net/%s/wireless" % entry) \
                        and not re.match(r"p2p", entry, re.I):
                    sniff.append(entry)
        except OSError:
            pass
        if not sniff:
            try:
                out = subprocess.run(["iw", "dev"], capture_output=True,
                                     text=True, timeout=5).stdout
                sniff = [m for m in re.findall(r"Interface\s+(\S+)", out)
                         if not re.match(r"p2p", m, re.I)]
            except (OSError, subprocess.TimeoutExpired):
                pass
        for ifc in sorted(set(sniff), key=rank):
            name = ok(ifc)
            if name and name != "wlan0" and name != "p2p-dev-wlan0":
                return name
        for ifc in ["toolwlan0", "mon0", "wlan1"]:
            name = ok(ifc)
            if name:
                return name
        return None

    def usb_hint(self):
        try:
            out = subprocess.run(["lsusb"], capture_output=True, text=True,
                                 timeout=5).stdout or ""
        except OSError:
            return ", replug the Alpha adapter"
        if "0bda:0811" in out or "0bda:8812" in out:
            return " (Alpha on USB but no usable interface — replug it)"
        return " (Alpha adapter not detected on USB — replug it)"

    def _monitor(self, iface):
        for a in (["ip", "link", "set", iface, "down"],
                  ["iw", "dev", iface, "set", "type", "monitor"],
                  ["ip", "link", "set", iface, "up"]):
            subprocess.run(["sudo", "-n"] + a, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        return subprocess.run(["iw", "dev", iface, "info"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0

    def start(self, iface=None):
        HS.stop(crack=False)
        iface = self.available_iface(iface)
        if not iface:
            return False, "no wireless card" + self.usb_hint()
        self.stop()
        if not self._monitor(iface):
            self.stop()
            return False, "could not bring %s to monitor mode" % iface
        try:
            os.makedirs(RECON_DIR, exist_ok=True)
        except OSError:
            pass
        for f in glob.glob(RECON_DIR + "-*.csv"):
            try:
                os.remove(f)
            except OSError:
                pass
        log = open(RECON_DIR + "/scan.log", "wb")
        self.proc = subprocess.Popen(
            ["sudo", "-n", "airodump-ng", "--band", "abg", "--write", RECON_DIR,
             "--write-interval", "2", "--output-format", "csv", iface],
            stdout=log, stderr=subprocess.STDOUT)
        self.iface = iface
        return True, iface

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None

    def state(self):
        aps = clients = 0
        if self.running():
            d = self.data()
            aps, clients = len(d["aps"]), len(d["clients"])
        return {"running": self.running(), "iface": self.iface,
                "aps": aps, "clients": clients}

    def data(self):
        cands = sorted(glob.glob(RECON_DIR + "-*.csv"))
        path = cands[-1] if cands else RECON_DIR + "-01.csv"
        return parse_recon_csv(path)

    def log_tail(self):
        p = RECON_DIR + "/scan.log"
        if os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    raw = f.read(4000).decode("utf-8", "replace")
                raw = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw)
                raw = raw.replace("\r\n", "\n").replace("\r", "\n")
                return raw
            except OSError:
                return ""
        return ""

    def deauth(self, bssid, client=None, iface=None):
        if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", bssid):
            return False
        if client and not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", client):
            return False
        iface = self.available_iface(iface) or self.iface or "toolwlan0"
        cmd = ["sudo", "-n", "aireplay-ng", "-0", "5", "-a", bssid]
        if client:
            cmd += ["-c", client]
        cmd += [iface]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


RECON = ReconManager()


HS_DIR = "/tmp/hs"
HS_HASHES = HS_DIR + "/hashes"
HS_POTS = HS_DIR + "/pots"
WORDLIST = "/usr/share/wordlists/rockyou.txt"


def _safe(name):
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "")[:24]
    return s or "ap"


class HandshakeManager:
    """Targeted handshake hunter: airodump-ng to /tmp/hs, convert with
    hcxpcapngtool to hashcat-22000, crack with hashcat + rockyou."""

    def __init__(self):
        self.proc = None
        self.iface = None
        self.target = None
        self.base = None
        self.channel = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def iface_for(self):
        return RECON.available_iface()

    def start(self, bssid, essid="", channel=None):
        if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", str(bssid)):
            return False, "bad BSSID"
        iface = self.iface_for()
        if not iface:
            return False, "no wireless card" + RECON.usb_hint()
        RECON.stop()
        self.stop(crack=False)
        try:
            os.makedirs(HS_DIR, exist_ok=True)
        except OSError:
            pass
        base = HS_DIR + "/" + _safe(essid or bssid)
        self.base = base
        self.target = bssid.upper()
        self.channel = channel
        cmd = ["sudo", "-n", "airodump-ng"]
        if channel:
            cmd += ["-c", str(channel)]
        cmd += ["--bssid", bssid, "-w", base, "--output-format", "pcap", "--write-interval", "2", iface]
        log = open(HS_DIR + "/hs.log", "wb")
        self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        self.iface = iface
        return True, os.path.basename(base)

    def stop(self, crack=True):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None
        if crack and HASHCAT and HASHCAT.poll() is None:
            try:
                HASHCAT.terminate()
                HASHCAT.wait(5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    HASHCAT.kill()
                except OSError:
                    pass

    def captures(self):
        out = []
        for cap in sorted(glob.glob(HS_DIR + "/*.cap")):
            st = os.stat(cap)
            base = cap[:-4]
            info = {"file": os.path.basename(cap), "size": st.st_size,
                    "mtime": int(st.st_mtime), "handshakes": 0, "pmkid": 0}
            hash_file = HS_HASHES + "/" + os.path.basename(base) + ".22000"
            try:
                r = subprocess.run(["hcxpcapngtool", "-o", hash_file, cap],
                                   capture_output=True, text=True, timeout=60)
                out_txt = (r.stdout or "") + "\n" + (r.stderr or "")
                info["handshakes"] = out_txt.count("4-WAY HANDSHAKE") + out_txt.count("Fourway")
                info["handshakes"] += out_txt.count("4-WAY-HANDSHAKE") * 0
                info["pmkid"] = out_txt.count("PMKID")
            except (OSError, subprocess.TimeoutExpired):
                pass
            info["hash"] = os.path.exists(hash_file) and os.path.getsize(hash_file) or 0
            info["cracked"] = self.cracked(os.path.basename(base))
            out.append(info)
        return out

    def hash_file(self, base):
        return HS_HASHES + "/" + base + ".22000"

    def pot_file(self, base):
        return HS_POTS + "/" + base + ".pot"

    def cracked(self, base):
        pf = self.pot_file(base)
        if os.path.isfile(pf):
            try:
                with open(pf, "r") as f:
                    line = f.read().strip()
                if ":" in line:
                    return line.split(":", 2)[-1]
            except OSError:
                pass
        return None

    def deauth(self, bssid, client=None, count=2):
        if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", str(bssid)):
            return False
        iface = self.iface_for() or self.iface or "toolwlan0"
        cmd = ["sudo", "-n", "aireplay-ng", "-0", str(count), "-a", bssid]
        if client:
            cmd += ["-c", client]
        cmd += [iface]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


HASHCAT = None


def start_crack(base):
    global HASHCAT
    hf = HS.hash_file(base)
    if not os.path.isfile(hf) or os.path.getsize(hf) == 0:
        return False, "no hash for " + base
    if not os.path.isfile(WORDLIST):
        return False, "wordlist missing"
    if HASHCAT is not None and HASHCAT.poll() is None:
        return False, "crack already running"
    try:
        os.makedirs(HS_POTS, exist_ok=True)
    except OSError:
        pass
    try:
        HASHCAT = subprocess.Popen(
            ["sudo", "-n", "hashcat", "-m", "22000", "-a", "0",
             "-w", "2", "--potfile-path", HS.pot_file(base),
             "--status", "--status-timer", "5", hf, WORDLIST],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "cracking"
    except OSError:
        return False, "hashcat missing"


def crack_status(base):
    if HASHCAT is not None and HASHCAT.poll() is None:
        return {"cracking": True, "cracked": HS.cracked(base)}
    pw = HS.cracked(base)
    return {"cracking": False, "cracked": pw}


HS = HandshakeManager()


def run_feed():
    while True:
        if SSE.proc:
            line = SSE.proc.stdout.readline()
            if line:
                with SSE.lock:
                    SSE.queue.append(line)
                continue
            rc = SSE.proc.poll()
            if rc is not None:
                with SSE.lock:
                    SSE.queue.append(f"\n[EXIT {rc}]\n")
                SSE.proc = None
        time.sleep(0.05)


threading.Thread(target=run_feed, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/tools":
            tools = []
            for s, l, c, r in TOOLS:
                params = []
                if "{target}" in c:
                    params.append("target")
                if "{bssid}" in c:
                    params.append("bssid")
                if "{user}" in c:
                    params.append("user")
                if "{pass}" in c:
                    params.append("pass")
                if "{wordlist}" in c:
                    params.append("wordlist")
                if "{hashmode}" in c:
                    params.append("hashmode")
                tools.append({"section": s, "label": l, "root": r, "params": params})
            launchers = []
            for lid, gp, lab, ico, bin_, root, pkg in INTERACTIVE:
                path = shutil.which(bin_)
                launchers.append({
                    "id": lid, "group": gp, "label": lab, "icon": ico,
                    "bin": path, "exists": bool(path), "root": root, "pkg": pkg,
                })
            self._send(200, json.dumps(
                {"sections": SECTIONS, "tools": tools, "launchers": launchers}
            ).encode())
        elif path == "/api/wordlists":
            self._send(200, json.dumps({"wordlists": find_wordlists()}).encode())
        elif path == "/api/network":
            self._send(200, json.dumps({"info": get_network_info()}).encode())
        elif path == "/api/sysinfo":
            self._send(200, json.dumps(sysinfo()).encode())
        elif path == "/api/wifi/scan":
            self._send(200, json.dumps(scan_wifi()).encode())
        elif path == "/api/term/status":
            self._send(200, json.dumps(
                {"running": not TERM.exited and TERM.pid is not None,
                 "pid": TERM.pid}
            ).encode())
        elif path == "/api/recon/state":
            self._send(200, json.dumps(RECON.state()).encode())
        elif path == "/api/recon/data":
            self._send(200, json.dumps(RECON.data()).encode())
        elif path == "/api/recon/log":
            self._send(200, json.dumps({"log": RECON.log_tail()}).encode())
        elif path == "/api/hs/state":
            self._send(200, json.dumps({
                "running": HS.running(),
                "iface": HS.iface,
                "target": HS.target,
                "channel": HS.channel,
                "captures": len(glob.glob(HS_DIR + "/*.cap")),
                "cracking": (HASHCAT is not None and HASHCAT.poll() is None),
            }).encode())
        elif path == "/api/hs/captures":
            self._send(200, json.dumps({"captures": HS.captures()}).encode())
        elif path == "/api/hs/crack/status":
            base = self.query.get("base", [""])[0]
            if not base:
                self._send(400, b'{"ok":false}')
            else:
                self._send(200, json.dumps(crack_status(base)).encode())
        elif path == "/api/launch/status":
            if os.path.isfile(INSTALL_LOG):
                with open(INSTALL_LOG, "rb") as f:
                    tail = f.read(4000).decode("utf-8", "replace")
            else:
                tail = ""
            busy = subprocess.run(["pgrep", "-x", "apt-get"], stdout=subprocess.DEVNULL).returncode == 0
            self._send(200, json.dumps({"busy": busy, "log": tail}).encode())
        elif path == "/sse/term":
            self.handle_sse_term()
            return
        elif path.startswith("/sse"):
            self.handle_sse()
            return
        elif path == "/" or path == "/index.html":
            self.serve_file("index.html", "text/html")
        elif path.startswith("/media/"):
            name = path[len("/media/"):]
            if name.endswith(".mp4"):
                ctype = "video/mp4"
            elif name.endswith(".png"):
                ctype = "image/png"
            else:
                ctype = "application/octet-stream"
            self.serve_file(os.path.join("media", name), ctype)
        elif path.startswith("/assets/"):
            name = path[len("/assets/"):]
            if name.endswith(".css"):
                self.serve_file(os.path.join("assets", name), "text/css")
            elif name.endswith(".js"):
                self.serve_file(os.path.join("assets", name), "application/javascript")
            else:
                self._send(404, b"nf")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if path == "/api/run":
            try:
                cmd = build_cmd(body)
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}).encode())
                return
            SSE.start(cmd)
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/stop":
            SSE.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/wifi/connect":
            res = connect_wifi(body.get("ssid", ""), body.get("password"))
            self._send(200 if res.get("ok") else 400, json.dumps(res).encode())
        elif path == "/api/reboot":
            self._send(200, json.dumps(reboot_device()).encode())
        elif path == "/api/shutdown":
            self._send(200, json.dumps(shutdown_device()).encode())
        elif path == "/api/term/start":
            TERM.start(init_cmd=body.get("cmd") or None, cwd=body.get("cwd") or None)
            self._send(200, json.dumps({"ok": True, "running": TERM.exited is False}).encode())
        elif path == "/api/recon/start":
            ok, msg = RECON.start(body.get("iface"))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/recon/stop":
            RECON.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/recon/deauth":
            ok = RECON.deauth(body.get("bssid", ""), body.get("client") or None, body.get("iface") or None)
            self._send(200 if ok else 400, json.dumps({"ok": ok}).encode())
        elif path == "/api/hs/start":
            ok, msg = HS.start(body.get("bssid", ""), body.get("essid", ""), body.get("channel"))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/hs/stop":
            HS.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/hs/deauth":
            ok = HS.deauth(body.get("bssid", ""), body.get("client") or None)
            self._send(200 if ok else 400, json.dumps({"ok": ok}).encode())
        elif path == "/api/hs/crack":
            ok, msg = start_crack(body.get("base", ""))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/launch/install":
            tid = body.get("id", "")
            pkg = next((p for lid, gp, lab, ico, bin_, root, p in INTERACTIVE if lid == tid), None)
            if not pkg:
                self._send(404, json.dumps({"error": "unknown tool"}).encode())
                return
            if subprocess.run(["pgrep", "-x", "apt-get"], stdout=subprocess.DEVNULL).returncode == 0:
                self._send(409, json.dumps({"error": "apt is busy"}).encode())
                return
            subprocess.Popen(
                f"apt-get install -y --no-install-recommends {pkg}",
                shell=True, stdout=open(INSTALL_LOG, "w"), stderr=subprocess.STDOUT,
            )
            self._send(200, json.dumps({"ok": True, "pkg": pkg}).encode())
        elif path == "/api/term/input":
            data = body.get("data", "")
            if isinstance(data, str):
                TERM.write(data)
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/term/stop":
            TERM.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        else:
            self._send(404, b"nf")

    def handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                lines = SSE.poll()
                for ln in lines:
                    for chunk in ln.splitlines(keepends=True):
                        self.wfile.write(f"data: {chunk}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_sse_term(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                out = TERM.poll()
                for chunk in out:
                    if isinstance(chunk, bytes):
                        text = chunk.decode("utf-8", "replace")
                    else:
                        text = str(chunk)
                    # JSON-encode so \n / control bytes survive the SSE wire.
                    self.wfile.write(f"data: {json.dumps(text)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_file(self, rel, ctype):
        target = os.path.realpath(os.path.join(ROOT, rel))
        if not target.startswith(ROOT):
            self._send(403, b"forbidden")
            return
        if os.path.isfile(target):
            with open(target, "rb") as f:
                self._send(200, f.read(), ctype)
        else:
            self._send(404, b"nf")


if __name__ == "__main__":
    ensure_users_file()
    print(f"Kali Touch UI listening on http://{HOST}:{PORT}")
    print(f"default wordlist: {default_wordlist()}")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
