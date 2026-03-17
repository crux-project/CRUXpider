#!/bin/bash

set -e

echo "Launching CRUXpider..."
echo "=================================================="

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export CRUXPIDER_PORT="${CRUXPIDER_PORT:-5003}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

python app.py &
FLASK_PID=$!

echo "CRUXpider started (PID: $FLASK_PID)"
echo "Local URL: http://127.0.0.1:${CRUXPIDER_PORT}"

sleep 5

if ! curl -s "http://127.0.0.1:${CRUXPIDER_PORT}/api/health" >/dev/null 2>&1; then
    echo "Application failed to start"
    kill $FLASK_PID 2>/dev/null || true
    exit 1
fi

cleanup() {
    echo
    echo "Stopping CRUXpider..."
    kill $FLASK_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

while true; do
    sleep 1
done
