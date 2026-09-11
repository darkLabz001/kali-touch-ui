#!/usr/bin/env bash
# Kali Touch UI launcher
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PORT="${TOUCHUI_PORT:-8080}"
FULLSCREEN="${FULLSCREEN:-1}"

echo "Launching Kali Touch UI on http://$(hostname -I | awk '{print $1}'):$PORT"
python3 "$DIR/backend/server.py" &
SERVER_PID=$!

sleep 1

if [ "$FULLSCREEN" = "1" ] && command -v chromium >/dev/null 2>&1; then
  # Open in kiosk/fullscreen in a lightweight browser
  # Chromium flags for touch + no scrollbars
  chromium --kiosk --noerrdialogs --disable-infobars \
    --touch-events=enabled --autoplay-policy=no-user-gesture-required \
    "http://127.0.0.1:$PORT" 2>/dev/null &
fi

trap "kill $SERVER_PID 2>/dev/null" EXIT
wait $SERVER_PID
