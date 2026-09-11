# Kali Touch UI

Touchscreen-first control frontend for **Kali Linux on a Raspberry Pi** with a 4″
display. Big touch targets, no keyboard needed, and every action runs the real Kali
tool under the hood and streams its output live.

Think of it as a launcher skin over your existing Kali tools: `nmap`, `masscan`,
`airodump-ng`, `hydra`, `sqlmap`, `nikto`, `enum4linux` … grouped into sections you
tap, with simple param fields and a live console.

```
┌───────────────────────────────────────┐
│ ◉ KALI TOUCH            ● LIVE        │
├───────────────────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐      │
│ │Network│ │Recon│ │ Web │ │Brute│     │
│ │ Scan │ │ &DNS│ │Attck│ │Force│     │
│ │  ●7  │ │  ●6 │ │ ●6 │ │ ●3  │      │
│ └─────┘ └─────┘ └─────┘ └─────┘      │
│ ┌─────┐ ┌─────┐ ┌─────┐              │
│ │WiFi │ │SMB/ │ │Util │              │
│ │Attck│ │ Win │ │ity  │              │
│ └─────┘ └─────┘ └─────┘              │
└───────────────────────────────────────┘
```

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
- **Tool registry**: edit the `TOOLS` list at the top of `backend/server.py` to add
  tools/sections. Each entry is `(section, label, command_template, needs_root)`.

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
│   ├── install.sh           # deploy to /opt, autologin, kiosk autostart
│   ├── kali-touchui.service # backend systemd service (starts on boot)
│   ├── kali-touch-kiosk.desktop # X session autostart entry
│   └── kiosk.sh             # waits for backend, opens Chromium fullscreen
├── run.sh                   # run in place (python3 + optional kiosk browser)
└── README.md
```

## 1. Flash Kali to the SD card

You already have the image at `../kali-image/kali-linux-2026.2-raspberry-pi-arm64.img.xz`.

```bash
# From your workstation — find the SD card FIRST (check dmesg, lsblk)
lsblk                        # confirm the device, e.g. /dev/sdX (do NOT guess)
xzcat kali-linux-2026.2-raspberry-pi-arm64.img.xz | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

> ⚠️ Double-check the device. `dd` to the wrong disk is irreversible.

### First-boot config

Re-mount the freshly-flashed card (or (un)plug it) and, if you want headless access:

```bash
# boot partition (FAT32), on your host:
mount /dev/sdX1 /mnt/boot
touch /mnt/boot/ssh                                   # enable SSH on boot
# if the Pi has no wired/known network, configure wireless in the rootfs too:
mount /dev/sdX2 /mnt/root
vi /mnt/root/etc/NetworkManager/system-connections/... # or use raspi-config later
```

Boot the Pi, then:

```bash
ssh kali@<pi-ip>            # default password: kali
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y chromium
```

## 2. Enable passwordless sudo for day-one automation

Most attack tools need root (`nmap -sS`, `masscan`, `airodump-ng`, `reaver` …). The
backend runs them via `sudo`, so give it a NOPASSWD entry (Kali's default already
allows this for the `kali` user in chroot-style setups, but be explicit):

```bash
echo "kali ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/kali-touchui
sudo chmod 440 /etc/sudoers.d/kali-touchui
```

## 3. Get the 4″ touchscreen working

Kali ships the Raspberry Pi kernel + firmware, so most 4″ DSI/HDMI/SPI panels are
supported via the standard device-tree overlays — sometimes with zero config.

**If your panel is the common 4″ HDMI "DPI" type (e.g. Waveshare 4.0 "Lite"/XPT2046):**

Set it up with the same `LCD-show` approach you already have:

```bash
git clone https://github.com/waveshare/LCD-show.git   # or reuse ../LCD-show
cd LCD-show
# for a 4.0" module, e.g.:
sudo ./LCD4-show                     # adjust to your exact panel (LCD4, LCD4D, etc.)
sudo reboot
```

This writes the right `dtoverlay=` into `/boot/config.txt` and installs the touch
calibration. If your panel is **DSI** (Raspberry Pi official-ish 4″), skip LCD-show:

```bash
# /boot/config.txt
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-7inch     # pick the overlay matching YOUR panel
dtoverlay=goodix,interrupt=GPIO5,reset=GPIO6     # some 4" raytech-style panels
```

Verify after reboot:

```bash
xrandr                                     # your chosen resolution is listed
sudo dmesg | grep -iE "touch|goodix|xpt2046|stmpe"   # touch controller probed
```

The UI itself is resolution-agnostic (grid reflows), but for a 4″ panel you'll want
**portrait** rotation so each section card stays gorilla-sized:

```bash
# /boot/config.txt  (HDMI/DPI panel)
display_rotate=1          # or 3 for 270° portrait, per your panel orientation
# touch rotation: see your panel docs / xinput-calibrator / xsetwacom mapping
```

## 4. Deploy the UI to the Pi (boot → UI)

```bash
scp -r kali-touch-ui kali@<pi-ip>:/tmp/
ssh kali@<pi-ip>
sudo mv /tmp/kali-touch-ui /opt/kali-touch-ui
sudo bash /opt/kali-touch-ui/scripts/install.sh    # boot-to-kiosk setup
```

`install.sh` does four things:

1. Copies the app to `/opt/kali-touch-ui`.
2. Installs + enables `kali-touchui.service` — the backend **starts on every boot**
   (before login, no display needed).
3. Enables **lightdm auto-login** for the `kali` user (no login prompt ever).
4. Installs `kali-touch-kiosk.desktop` into `/etc/xdg/autostart`, so once the
   desktop session starts, `kiosk.sh` opens **Chromium fullscreen kiosk** pointing
   at `http://127.0.0.1:8080`.

**Result: power on → UI is on the touchscreen, nothing else.** The browser waits up
to 30s for the backend (in case the pipe is still warming up), then hides everything
chrome-related and shows only the app.

Backend only, no reboot needed to test:

```bash
sudo systemctl enable --now kali-touchui
```

To get back to a normal desktop on the device: close the kiosk with **Alt+F4**, or
disable the autostart entry any time with:

```bash
sudo rm /etc/xdg/autostart/kali-touch-kiosk.desktop
```

## 5. Use it

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
which fields to render straight from the template. Restart the service to reload:
`sudo systemctl restart kali-touchui`.

## Security & legality

- **This is an attack surface on a stick.** Never run the UI's tools against networks
  you don't own / are not explicitly authorized to test.
- The backend binds `0.0.0.0:8080` with **no auth**, so anyone on your LAN can trigger
  tools. For field use, either restrict the Pi to a bring-your-own AP or add a
  reverse-proxy / firewall rule. Long term, add a token header check in `do_GET`/
  `do_POST` if it'll see untrusted networks.
- Commands are injection-safe (whitelist + `shlex.split`), but tools are powerful:
  `sudo` + NOPASSWD is the enabler, so treat the Pi like a root credential.

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI not reachable | Is it a wifi client? `curl http://<ip>:8080/api/tools`. Check `systemctl status kali-touchui`. |
| Tool says "Unknown tool" | Section/label mismatch — restart service after editing `TOOLS`. |
| Tool missing → "command not found" | `sudo apt install <tool>`, it just wasn't in the registry check. |
| Touch offset / upside down | Double `display_rotate` is only video, not touch; calibrate touch separately (panel docs / `xinput-calibrator`). |
| `sudo` denies tool | Re-add the NOPASSWD entry from §2 (some upgrades rewrite sudoers). |
| Injection rejected | Fields accept only `[A-Za-z0-9._:/:[]-]` on purpose. Don't fight it — add a named param instead. |
```