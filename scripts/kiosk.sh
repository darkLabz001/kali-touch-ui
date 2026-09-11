#!/usr/bin/env bash
# Kiosk launcher for Kali Touch UI.
# Run from the desktop session's autostart: waits for the backend, then opens
# Chromium fullscreen so the UI is the only thing on the touchscreen.
set -u

# Never let the display blank or sleep on the panel.
if [ -n "${DISPLAY:-}" ]; then
    xset s off -dpms >/dev/null 2>&1 || true
    xset dpms force on >/dev/null 2>&1 || true
fi

# Force the HDMI output and panel into a known-on state: some 4" HDMI DPI
# panels come up dark in standby and only wake on a fresh modeset. Use the
# panel's exact config.txt timing (480x800 @ 60Hz CVT) — deviating from it
# (e.g. refresh rate or pixel clock) makes the panel go black.
vcgencmd display_power 1 >/dev/null 2>&1 || true
if command -v xrandr >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
    xrandr --output HDMI-1 --mode 480x800 --rate 60 2>/dev/null || true
    xset dpms force on >/dev/null 2>&1 || true
fi

URL="${TOUCHUI_URL:-http://127.0.0.1:8080}"
BACKEND="$URL"

# Wait up to 30s for the backend to come up.
for i in $(seq 1 30); do
    if curl -sf -o /dev/null "$BACKEND/api/tools"; then
        break
    fi
    sleep 1
done

# Which browser binary do we have?
BROWSER=""
for b in chromium chromium-browser google-chrome; do
    if command -v "$b" >/dev/null 2>&1; then BROWSER="$b"; break; fi
done

if [ -z "$BROWSER" ]; then
    # No browser: at least open a udev-provisioned message so it's not silent.
    echo "kali-touch-ui: no chromium/google-chrome/browser found" >> /tmp/kali-touch-kiosk.log
    exit 1
fi

# Launch the kiosk and keep it alive: if Chromium ever crashes (e.g. GPU
# process failure on boot), restart it so the screen never stays black.
RESTART_DELAY="${TOUCHUI_RESTART_DELAY:-3}"
while true; do
    "$BROWSER" \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-component-update \
        --no-first-run \
        --check-for-update-interval=31536000 \
        --hide-scrollbars \
        --disable-features=TranslateUI,AutofillServerCommunication,MediaRouter \
        --touch-events=enabled --disable-gpu --disable-gpu-compositing --use-gl=swiftshader --disable-software-rasterizer=0 --enable-unsafe-swiftshader --password-store=basic \
        --disable-pinch \
        --overscroll-history-navigation-disabled \
        --pull-to-refresh=0 \
        --window-size=480,800 --window-position=0,0 \
        --app="$URL" 2>/tmp/kali-touch-kiosk.log &
    BROWSER_PID=$!

    # Keep the kiosk window exactly edge-to-edge at 480x800 with no WM frame
    # (xfwm4 adds one otherwise) and no title bar, and detect if the browser dies.
    while kill -0 "$BROWSER_PID" 2>/dev/null; do
        sleep 3
        WID=$(DISPLAY=:0 xdotool search --name "Kali Touch UI" 2>/dev/null | head -1)
        if [ -n "$WID" ]; then
            DISPLAY=:0 xdotool windowraise "$WID" windowsize "$WID" 480 800 windowmove "$WID" 0 0 2>/dev/null
            DISPLAY=:0 xprop -id "$WID" -f _MOTIF_WM_HINTS 32c -set _MOTIF_WM_HINTS 0x2,0x0,0x0,0x0,0x0 2>/dev/null
        fi
    done

    echo "kali-touch-ui: kiosk browser exited, restarting in ${RESTART_DELAY}s" >> /tmp/kali-touch-kiosk.log
    sleep "$RESTART_DELAY"
done