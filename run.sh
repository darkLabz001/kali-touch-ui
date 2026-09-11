#!/usr/bin/env bash
# Kali Touch UI — run right on your Kali box (no install needed).
#   ./run.sh
# Opens the UI in fullscreen Chromium; server starts in the background.
# If anything it needs is missing, it installs it for you.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PORT="${TOUCHUI_PORT:-8080}"
FULLSCREEN="${FULLSCREEN:-1}"

command -v python3 >/dev/null 2>&1 || {
    echo "python3 not found — this script targets Kali Linux." >&2
    exit 1
}

if [ "$FULLSCREEN" = "1" ] && ! command -v chromium >/dev/null 2>&1; then
    echo "[*] Installing chromium (needed for the fullscreen UI)…"
    sudo apt-get update -qq
    sudo apt-get install -y chromium
fi

echo "[*] Starting server on http://127.0.0.1:$PORT"
echo "    (you + anyone on this box can use it; tap tools stream live output)"
python3 "$DIR/backend/server.py" &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT

sleep 1

if [ "$FULLSCREEN" = "1" ] && command -v chromium >/dev/null 2>&1; then
    chromium --kiosk --noerrdialogs --disable-infobars \
        --touch-events=enabled --autoplay-policy=no-user-gesture-required \
        "http://127.0.0.1:$PORT" 2>/dev/null &
fi

wait $SERVER_PID