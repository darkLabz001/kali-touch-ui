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
apt-get install -y --no-install-recommends chromium python3 git bluez bluez-utils bluez-tools 2>/dev/null || \
    apt-get install -y --no-install-recommends chromium python3 git bluez bluez-utils || true
systemctl enable --now bluetooth >/dev/null 2>&1 || true

if [ -n "${WIFI_SSID:-}" ] && [ -n "${WIFI_PASS:-}" ]; then
    echo "[*] Provisioning WiFi '$WIFI_SSID'…"
    nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS" >/dev/null 2>&1 \
        || nmcli connection add type wifi con-name "$WIFI_SSID" ssid "$WIFI_SSID" \
               wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PASS" \
               connection.autoconnect yes 802-11-wireless.cloned-mac-address permanent
fi

echo "[*] Storing WiFi connections with priority (new ones win over defaults)…"
:
# Keep the last provisioned connection preferred so watchdog/auto-connect pick it.
nmcli -g UUID connection show "$WIFI_SSID" 2>/dev/null | while read -r uuid; do
    nmcli connection modify "$uuid" connection.autoconnect-priority 300 2>/dev/null || true
done

echo "[*] Disabling WiFi power-save (drops while roaming/scanning)…"
install -m 0644 /dev/stdin /etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF
nmcli connection reload >/dev/null 2>&1 || true
for dev in $(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1}'); do
    iw dev "$dev" set power_save off >/dev/null 2>&1 || true
done

echo "[*] Installing WiFi reconnect watchdog…"
install -m 0755 "$APP/scripts/wifi-watchdog.sh" /usr/local/bin/wifi-watchdog.sh
install -m 0644 "$APP/scripts/wifi-watchdog.service" /etc/systemd/system/wifi-watchdog.service
install -m 0644 "$APP/scripts/wifi-watchdog.timer" /etc/systemd/system/wifi-watchdog.timer
systemctl daemon-reload
systemctl enable --now wifi-watchdog.timer >/dev/null 2>&1 || true

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

echo "[*] Optional: QR-code rendering for Wardriving phone link (best-effort, 💫)."
apt-get install -y --no-install-recommends python3-qrcode python3-pil >/dev/null 2>&1 \
    || true

echo "[*] Installing kiosk autostart…"
install -m 0644 "$APP/scripts/kali-touch-kiosk.desktop" "$AUTOSTART_DIR/"
echo "[*] Installing resilient kiosk fallback…"
install -D -m 0755 "$APP/scripts/kiosk.sh" /usr/local/share/kali-touch/kiosk.sh
install -m 0755 "$APP/scripts/kali-touch-session" /usr/local/bin/kali-touch-session

echo "[*] Hardening 4-inch panel timings (boots → UI at 480x800@60, no black screens)…"
PANEL_CFG=""
for c in /boot/firmware/config.txt /boot/config.txt; do
    if grep -q '^hdmi_cvt=480 800' "$c" 2>/dev/null; then
        PANEL_CFG="$c"; break
    fi
done
if [ -z "$PANEL_CFG" ]; then
    for c in /boot/firmware/config.txt /boot/config.txt; do
        if [ -e "$c" ] && [ -w "$(dirname "$c")" ]; then
            PANEL_CFG="$c"; break
        fi
    done
fi
if [ -n "$PANEL_CFG" ]; then
    sed -i 's/^disable_fw_kms_setup=1/disable_fw_kms_setup=0/' "$PANEL_CFG"
    if ! grep -q '^hdmi_cvt=480 800 60' "$PANEL_CFG"; then
        printf '\n# --- 4inch HDMI LCD: force 480x800@60, survive reboots (no black screen) ---\nhdmi_group=2\nhdmi_mode=87\nhdmi_cvt=480 800 60 6 0 0 0\nhdmi_drive=1\nhdmi_force_hotplug=1\nhdmi_ignore_edid=0xa00002\ndtoverlay=ads7846_waveshare,penirq=25,xmin=150,xmax=3900,ymin=100,ymax=3950,speed=50000\n' >> "$PANEL_CFG"
    fi
fi
for c in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -e "$c" ]; then
        grep -q 'video=HDMI-A-1:480x800@60' "$c" || printf ' video=HDMI-A-1:480x800@60' >> "$c"
        break
    fi
done

echo
echo "[*] Setup complete."
echo "    The UI will appear fullscreen on the touchscreen after reboot."
echo "    Rebooting in 5 seconds — Ctrl+C to cancel:"
sleep 5
reboot