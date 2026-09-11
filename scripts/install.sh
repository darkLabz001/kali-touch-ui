#!/usr/bin/env bash
# Deploy Kali Touch UI as a boot-to-kiosk device:
#   1. copy app to /opt
#   2. enable backend systemd service (starts on boot)
#   3. enable auto-login (lightdm) so a desktop session starts at boot
#   4. install X session autostart that opens Chromium kiosk on the touchscreen
set -euo pipefail

APP=/opt/kali-touch-ui
SERVICE=kali-touchui.service
AUTOSTART_DIR=/etc/xdg/autostart
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root (sudo)." >&2
    exit 1
fi

# --- 1. app ---------------------------------------------------------------
if [ "$SRC_DIR" != "$APP" ]; then
    echo "[*] Installing app to $APP"
    rm -rf "$APP"
    mkdir -p "$APP"
    cp -r "$SRC_DIR"/backend "$SRC_DIR"/web "$SRC_DIR"/scripts "$SRC_DIR"/run.sh "$APP"/
    chmod +x "$APP/run.sh" "$APP/scripts/kiosk.sh"
fi

# --- 2. backend service ---------------------------------------------------
echo "[*] Installing $SERVICE"
install -m 0644 "$SRC_DIR/scripts/$SERVICE" /etc/systemd/system/$SERVICE
systemctl daemon-reload
systemctl enable $SERVICE

# --- 3. auto-login ---------------------------------------------------------
LIGHTDM_CONF=/etc/lightdm/lightdm.conf
if [ ! -f "$LIGHTDM_CONF" ] || ! grep -q '^autologin-user=' "$LIGHTDM_CONF"; then
    echo "[*] Enabling lightdm auto-login for kali"
    if ! grep -q '^\[Seat:.*\]' "$LIGHTDM_CONF" 2>/dev/null; then
        printf '\n[Seat:*]\n' >> "$LIGHTDM_CONF"
    fi
    sed -i '/^\[Seat:/a autologin-user=kali\nautologin-user-timeout=0' "$LIGHTDM_CONF"
fi

# --- 4. kiosk autostart ----------------------------------------------------
echo "[*] Installing kiosk autostart entry"
install -m 0644 "$SRC_DIR/scripts/kali-touch-kiosk.desktop" "$AUTOSTART_DIR/"

echo
echo "[*] Done."
echo "    Reboot and the UI should appear fullscreen on the touchscreen."
echo "    (Shift meanwhile: press it — dev login; browser closes with Alt+F4.)"
echo
echo "    Manual start without reboot:"
echo "      sudo systemctl start $SERVICE"
echo "      /opt/kali-touch-ui/scripts/kiosk.sh &"