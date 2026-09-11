# Kali Touch UI

Touchscreen-first control frontend for **Kali Linux on a Raspberry Pi** with a 4″
display. Big touch targets, no keyboard needed, and every action runs the real Kali
tool under the hood and streams its output live.

Think of it as a launcher skin over your existing Kali tools: `nmap`, `masscan`,
`airodump-ng`, `hydra`, `sqlmap`, `nikto`, `enum4linux` … grouped into sections you
tap, with simple param fields and a live console. It updates itself with OTA pulls
from this repo.

```
┌───────────────────────────────────────┐
│ ◉ KALI TOUCH            ● LIVE       │
├───────────────────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐      │
│ │Network│ │Recon│ │ Web │ │Brute│     │
│ │ Scan │ │ &DNS│ │Attck│ │Force│     │
│ │  ●7  │ │  ●6 │ │ ●6 │ │ ●3  │      │
│ └─────┘ └─────┘ └─────┘ └─────┘      │
└───────────────────────────────────────┘
```

## Quickstart

### Option A — boot-to-kiosk device (Pi with touchscreen)

On a fresh Kali Pi (SSH or keyboard), run this one command:

```bash
curl -sSL https://raw.githubusercontent.com/darkLabz001/kali-touch-ui/main/scripts/setup.sh | sudo bash
```

That installs every dependency, the backend service, auto-login, the fullscreen
kiosk, and a git clone at `/opt/kali-touch-ui` so **OTA updates** in *Settings →
OTA Update* just work. It reboots you into the UI.

To also join a WiFi/hotspot on first boot (e.g. your phone's hotspot), pass it
at install time — it's **not** baked into this repo:

```bash
sudo WIFI_SSID='iPhone' WIFI_PASS='your-hotspot-password' bash -c 'curl -sSL https://raw.githubusercontent.com/darkLabz001/kali-touch-ui/main/scripts/setup.sh | bash'
```

First boot only: enable SSH / join WiFi for headless access (see [Appendix](#appendix-hardware-and-flashing)).

### Option B — run it on a normal Kali machine

Clone and run — no setup, no reboot:

```bash
git clone https://github.com/darkLabz001/kali-touch-ui.git
cd kali-touch-ui
./run.sh
```

`run.sh` starts the backend and opens the UI fullscreen in Chromium (installs
Chromium for you if it's missing). Use it from any browser on the network via
`http://<this-machine-ip>:8080`.

### Check for updates (both options)

Open **Settings → ⚡ OTA Update → ⬇ Update**. The device pulls `main` from this
repo, syntax-checks, rolls back on failure, and reloads the UI.

## Architecture

- **Backend**: `backend/server.py` — Python **stdlib only** (no pip installs on the
  Pi). Serves the UI, maps tool → command, runs it with `sudo` when needed, and
  streams output to the browser over **Server-Sent Events (SSE)**.
  - Every user-supplied field is validated against `[A-Za-z0-9._:/:[]-]+`
    → command injection is rejected, not passed to a shell (no `sh -c` — commands
    are built token-by-token with `shlex.split`).
- **Frontend**: `web/` — single-page app, zero build step, touch-optimized (min
  target size ~46 px, big tap targets, no zoom scaling). Works in any browser,
  Chromium kiosk mode, or a "save to home screen" webapp.
  - Home → sections → tools → live console. Custom tools: **WiFi Recon (PineAP)**,
    **Handshake Hunter**, **WiFi Radar**, and **Click-Run** one-liners.
  - **Settings** holds WiFi connect, device info, **OTA Update**, Reboot/Shutdown.
- **Tool registry**: edit the `TOOLS` list at the top of `backend/server.py` to add
  tools/sections. Each entry is `(section, label, command_template, needs_root)`.
- **OTA**: a git clone of this repo. `scripts/setup.sh` clones it for you, so
  updating is a clean `git reset --hard origin/main` behind the scenes.

## Components

```
kali-touch-ui/
├── backend/server.py        # HTTP + SSE backend (stdlib only)
├── web/
│   ├── index.html
│   └── assets/
│       ├── style.css        # dark touch UI
│       └── app.js           # SPA: home → section → tool → live console
├── scripts/
│   ├── setup.sh             # ⭐ ONE-COMMAND: deps + service + kiosk + OTA
│   ├── kali-touchui.service # backend systemd service (starts on boot)
│   ├── kali-touch-kiosk.desktop # X session autostart entry
│   └── kiosk.sh             # waits for backend, opens Chromium fullscreen
├── run.sh                   # run in place (python3 + optional kiosk browser)
└── README.md
```

## Use it

1. Power on the Pi — the UI comes up fullscreen on the touchscreen automatically.
2. **Home** → tap a section → tap a tool.
3. Fill the fields that appear (URL / IP / BSSID / creds) — or leave them to use the
   stored defaults (e.g. reaver's BSSID).
4. **▶ RUN** starts the tool, **■ STOP** kills it, and output streams live below.
5. Back arrow returns to the section/home; hitting back also stops a running stream.

### Adding your own tools

Edit `TOOLS` in `backend/server.py`:

```python
("web", "Gobuster", "gobuster dir -u {target} -w /usr/share/wordlists/dirb/common.txt", False),
```

Supported placeholders: `{target}`, `{bssid}`, `{user}`, `{pass}`. The API discovers
which fields to render straight from the template. Then update the UI: **Settings →
⚡ OTA Update → ⬇ Update** (dev) or `sudo systemctl restart kali-touchui`.

## Appendix: hardware & flashing

### Flash Kali to the SD card

```bash
lsblk                        # confirm the device, e.g. /dev/sdX (do NOT guess)
xzcat kali-linux-2026.2-raspberry-pi-arm64.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

> ⚠️ Double-check the device. `dd` to the wrong disk is irreversible.

For headless access, mount the card on your host and:
```bash
mount /dev/sdX1 /mnt/boot
touch /mnt/boot/ssh                                   # enable SSH on boot
# join WiFi from the rootfs (or use raspi-config on first boot):
mount /dev/sdX2 /mnt/root
vi /mnt/root/etc/NetworkManager/system-connections/... 
```

First boot, then the **Quickstart** above: `ssh kali@<pi-ip>` (default password
`kali`) and run the `curl | sudo bash` line.

### Optional: 4″ panel rotation

The UI is resolution-agnostic and portrait-rotates fine, but if your panel boots
landscape, add `display_rotate=1` (or `3` for 270°) to `/boot/config.txt` and
calibrate touch separately (`xinput-calibrator`). Most Kali Pi kernels already probe
XPT2046 / goodix panels with zero config.

## Security & legality

- **This is an attack surface on a stick.** Never run the UI's tools against networks
  you don't own / are not explicitly authorized to test.
- The backend binds `0.0.0.0:8080` with **no auth**, so anyone on your LAN can trigger
  tools. For field use, restrict the Pi to a bring-your-own AP or add a
  reverse-proxy / firewall rule.
- Commands are injection-safe (whitelist + `shlex.split`), but tools are powerful:
  `sudo` + NOPASSWD is the enabler, so treat the Pi like a root credential.

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI not reachable | `curl http://<ip>:8080/api/tools`. Check `systemctl status kali-touchui`. |
| Tool says "Unknown tool" | Section/label mismatch — restart service after editing `TOOLS`. |
| Tool missing → "command not found" | `sudo apt install <tool>`. |
| Touch offset / upside down | `display_rotate` only affects video; calibrate touch separately. |
| `sudo` denies tool | Re-add `echo "kali ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/kali-touchui && chmod 440 /etc/sudoers.d/kali-touchui`. |
| Update failed, rolled back | The backend syntax-checks after each pull and reverts automatically — check `/tmp/ota.log`, fix on GitHub, update again. |
| Injection rejected | Fields accept only `[A-Za-z0-9._:/:[]-]` on purpose. Don't fight it — add a named param instead. |