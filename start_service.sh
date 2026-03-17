#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${CRUXPIDER_PORT:-5003}"
cd "$ROOT_DIR"

./start.sh &
FLASK_PID=$!

cleanup() {
  kill "$FLASK_PID" 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM

sleep 5

python3 - <<PY
import urllib.request
urllib.request.urlopen("http://127.0.0.1:${PORT}/api/health", timeout=5)
PY

echo "CRUXpider started (PID: $FLASK_PID)"
wait "$FLASK_PID"
