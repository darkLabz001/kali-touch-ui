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
        --no-first-run \
        --check-for-update-interval=31536000 \
        --touch-events=enabled --disable-gpu --disable-gpu-compositing --use-gl=swiftshader --disable-software-rasterizer=0 --enable-unsafe-swiftshader --password-store=basic \
        --disable-pinch \
        --overscroll-history-navigation-disabled \
        --pull-to-refresh=0 \
        --window-size=480,800 --window-position=0,0 \
        --app="$URL" 2>/tmp/kali-touch-kiosk.log &
    BROWSER_PID=$!

    # Keep the kiosk window exactly edge-to-edge at 480x800 (xfwm4 adds a
    # frame otherwise) while the browser runs, and detect if it dies.
    while kill -0 "$BROWSER_PID" 2>/dev/null; do
        sleep 3
        WID=$(DISPLAY=:0 xdotool search --name "Kali Touch UI" 2>/dev/null | head -1)
        if [ -n "$WID" ]; then
            DISPLAY=:0 xdotool windowraise "$WID" windowsize "$WID" 480 800 windowmove "$WID" 0 0 2>/dev/null
        fi
    done

    echo "kali-touch-ui: kiosk browser exited, restarting in ${RESTART_DELAY}s" >> /tmp/kali-touch-kiosk.log
    sleep "$RESTART_DELAY"
done