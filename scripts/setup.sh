#!/usr/bin/env bash
# Kali Touch UI — one-command setup to a boot-to-kiosk device.
#
#   curl -sSL https://raw.githubusercontent.com/darkLabz001/kali-touch-ui/main/scripts/setup.sh | sudo bash
#
# or, from a clone of this repo:
#   sudo ./scripts/setup.sh
#
# Does everything: deps, app install (git clone → OTA-ready), passwordless
# sudo for tools, backend service on boot, auto-login, and the Chromium kiosk.
set -euo pipefail

APP=/opt/kali-touch-ui
SERVICE=kali-touchui.service
AUTOSTART_DIR=/etc/xdg/autostart
REPO="https://github.com/darkLabz001/kali-touch-ui.git"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root (sudo)." >&2
    echo "  curl -sSL https://raw.githubusercontent.com/darkLabz001/kali-touch-ui/main/scripts/setup.sh | sudo bash" >&2
    exit 1
fi

echo "[*] Installing system packages (chromium, python3, git)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends chromium python3 git || true

echo "[*] Installing app as a git clone (OTA-ready)…"
rm -rf "$APP"
git clone --quiet "$REPO" "$APP"
chown -R kali:kali "$APP"

echo "[*] Enabling passwordless sudo for attack tools…"
printf 'kali ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/kali-touchui
chmod 440 /etc/sudoers.d/kali-touchui

echo "[*] Installing backend service (starts on boot)…"
install -m 0644 "$APP/scripts/$SERVICE" /etc/systemd/system/$SERVICE
systemctl daemon-reload
systemctl enable --now $SERVICE

echo "[*] Enabling lightdm auto-login for kali…"
LIGHTDM_CONF=/etc/lightdm/lightdm.conf
if [ ! -f "$LIGHTDM_CONF" ] || ! grep -q '^autologin-user=' "$LIGHTDM_CONF"; then
    if ! grep -q '^\[Seat:.*\]' "$LIGHTDM_CONF" 2>/dev/null; then
        printf '\n[Seat:*]\n' >> "$LIGHTDM_CONF"
    fi
    sed -i '/^\[Seat:/a autologin-user=kali\nautologin-user-timeout=0' "$LIGHTDM_CONF"
fi

echo "[*] Installing kiosk autostart…"
install -m 0644 "$APP/scripts/kali-touch-kiosk.desktop" "$AUTOSTART_DIR/"
echo "[*] Installing resilient kiosk fallback…"
install -D -m 0755 "$APP/scripts/kiosk.sh" /usr/local/share/kali-touch/kiosk.sh
install -m 0755 "$APP/scripts/kali-touch-session" /usr/local/bin/kali-touch-session

echo
echo "[*] Setup complete."
echo "    The UI will appear fullscreen on the touchscreen after reboot."
echo "    Rebooting in 5 seconds — Ctrl+C to cancel:"
sleep 5
reboot