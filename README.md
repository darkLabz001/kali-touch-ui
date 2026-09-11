# Kali Touch UI

Touchscreen-first control frontend for **Kali Linux on a Raspberry Pi** with a 4″
display. Big touch targets, no keyboard needed, and every action runs the real Kali
tool under the hood and streams its output live.

Think of it as a launcher skin over your existing Kali tools: `nmap`, `masscan`,
`airodump-ng`, `hydra`, `sqlmap`, `nikto`, `enum4linux` … grouped into sections you
tap, with simple param fields and a live console. Settings adds a one-tap
**System Upgrade**, a **Bluetooth tools** section, and self-updating via OTA —
both with live progress bars.

Custom-built tools round it out: **Wardrive** (phone-GPS wardriving via a QR
page → WiGLE CSV), **Recon/PineAP**, **Handshake Hunter** (auto-cracks the handshake
as soon as it's captured), **WiFi Radar**, **Rogue AP** (evil-twin AP with a captive
portal that captures login credentials), plus a tap-to-toggle **route via Tor**
(proxychains) on any network tool.

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
OTA Update* just work. It also hardens the 4″ panel timings so the display
**survives reboots** (see [Panel timing](#panel-timing-480x800-at-60-hz)) and
reboots you straight into the UI.

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

Open **Settings → ⚡ OTA Update**. **⟳ Check** compares local vs `main` on GitHub;
**⬇ Update** is only enabled when a new version exists. Updating is fully
asynchronous — a live progress bar shows the git fetch percent and a stage
label (fetching → verifying), it syntax-checks, rolls back on failure, and
reloads the UI on success.

> **Two-tap confirm:** kiosk-mode Chromium suppresses native `confirm()` dialogs,
> so all destructive actions (OTA Update, System Upgrade, Reboot, Shutdown) use an
> in-app two-tap confirm: tap once → button becomes a pulsing *"Tap again to
> confirm"* → tap again to run.

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
  - **Settings** holds WiFi connect, device info, **⚡ OTA Update** (with live
    progress), **⬆ System Upgrade** (runs `apt upgrade` with a real percent/progress
    bar), a **Bluetooth tools** section, and Reboot/Shutdown.
- **Tool registry**: edit the `TOOLS` list at the top of `backend/server.py` to add
  tools/sections. Each entry is `(section, label, command_template, needs_root)`.
- **OTA**: a git clone of this repo. `scripts/setup.sh` clones it for you, so
  updating is a clean `git reset --hard origin/main` behind the scenes.

## Components

```
kali-touch-ui/
├── backend/server.py        # HTTP + SSE backend (stdlib only)
├── wardrive/                # wardriving core: scanner/GPS/autosave + headless driver
│   ├── wardriver.py         # (vendored) WiFi/BLE scan + GPS placement + WiGLE CSV
│   ├── gps_page.py          # (vendored) phone QR page that streams GPS fixes
│   ├── gps_server.py        # standalone HTTPS phone-GPS feed (TUI-compatible)
│   └── headless.py          # drive runner: scan loop + QR page + JSON status
├── rogue/portal.py          # captive-portal HTTP site for the rogue AP (:80)
├── web/
│   ├── index.html
│   └── assets/
│       ├── style.css        # dark touch UI
│       └── app.js           # SPA: home → section → tool → live console
├── scripts/
│   ├── setup.sh             # ⭐ ONE-COMMAND: deps + service + kiosk + panel + OTA
│   ├── kali-touch-session   # X session: splash → wait for backend → kiosk;
│   │                        #   self-heals a corrupt/missing kiosk.sh on every launch
│   ├── kali-touchui.service # backend systemd service (starts on boot)
│   ├── kali-touch-kiosk.desktop # X session autostart entry → kali-touch-session
│   └── kiosk.sh             # force-wakes HDMI sink, waits for backend, opens Chromium fullscreen
├── run.sh                   # run in place (python3 + optional kiosk browser)
└── README.md
```

## Use it

1. Power on the Pi — the UI comes up fullscreen on the touchscreen automatically, and
   it survives power loss/reboots untouched.
2. **Home** → tap a section → tap a tool.
3. Fill the fields that appear (URL / IP / BSSID / creds) — or leave them to use the
   stored defaults (e.g. reaver's BSSID).
4. **▶ RUN** starts the tool, **■ STOP** kills it, and output streams live below.
5. Back arrow returns to the section/home; hitting back also stops a running stream.

### Built-in custom tools

The Home screen surfaces three hand-built tools for the field kit:

- **◈ Wardrive** — one tap starts a Wi-Fi/BLE scan that autosaves a WiGLE CSV
  (`~/.wardriver/scans/wardriving_YYYYMMDD_HHMMSS.csv` with lat/lon/accuracy).
  A QR code on screen points your *phone* at the Pi's HTTPS page (`:8888`, cert is
  self-signed — accept it), which streams GPS fixes back over
  `POST /gps/batch`; the scan is only geotagged while the phone reports a fresh fix.
  Tap **Stop** when done — the file is flushed on a clean stop.
- **⚑ Rogue AP** — an evil-twin AP (`toolwlan0` → `Free-WiFi`, ch 6) with
  `dnsmasq` resolving everything to `10.66.66.1` and a captive portal on `:80`.
  Victims tapping "Connect" dump their credentials to `/tmp/rogue/creds.csv`,
  visible live in the UI. Stopping restores the NIC to managed mode for NetworkManager.
- **Handshake Hunter** — per-target capture of an AP + client pair
  (`airodump-ng` on the attack NIC + `aireplay-ng` deauth). The moment a 4-way
  handshake is detected, the backend auto-converts it (`hcxpcapngtool`) and runs
  `aircrack-ng` against `rockyou.txt`; a found key lands in
  `/tmp/hs/pots/*.aircrack` and the UI flips to **KEY FOUND**.

Choose any runnable tool ([**Custom tools** fields](#adding-your-own-tools) apply)
and **Tor** will wrap it in `proxychains` (and start `tor` via systemd) so traffic
exits through the Tor network — ideal when the hotspot you're on shouldn't see
your scan traffic.

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

### Panel timing (480x800 at 60 Hz)

The 4″ Waveshare HDMI panels only sync *reliably* at exactly 60 Hz. With the stock
2026-era Kali images the firmware is told `disable_fw_kms_setup=1`, so X ignores
the forced `config.txt` timings and drives the panel from its EDID — which reports
an incompatible ~62 Hz and comes up as a **black screen on random boots**.
`scripts/setup.sh` applies these on the Pi for you:

```ini
# /boot/firmware/config.txt  (in the [all] panel block)
disable_fw_kms_setup=0
hdmi_group=2
hdmi_mode=87
hdmi_cvt=480 800 60 6 0 0 0
hdmi_drive=1
hdmi_force_hotplug=1
hdmi_ignore_edid=0xa00002
dtoverlay=ads7846_waveshare,penirq=25,xmin=150,xmax=3900,ymin=100,ymax=3950,speed=50000
```

```text
# /boot/firmware/cmdline.txt — append:
video=HDMI-A-1:480x800@60
```

Verify after boot: `xrandr` should mark **59.96\*** (60 Hz) as the active mode. If
your panel is a different resolution, replace `480x800` in `hdmi_cvt` and the
`video=` line.

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
| Nothing happens when tapping Update/Upgrade | Kiosk Chromium blocks `confirm()` — use two-tap confirm: tap again when the button shows *"Tap again to confirm"*. |
| Black screen after reboot (kiosk runs) | A Waveshare-typical 62 Hz EDID mode is active; the panel only syncs at 60 Hz. Re-apply the [Panel timing](#panel-timing-480x800-at-60-hz) block + `video=HDMI-A-1:480x800@60`, reboot, confirm `xrandr` shows `59.96*`. |
| Injection rejected | Fields accept only `[A-Za-z0-9._:/:[]-]` on purpose. Don't fight it — add a named param instead. |