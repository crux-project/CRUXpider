#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${CRUXPIDER_VENV_DIR:-$ROOT_DIR/.venv}"
PORT="${CRUXPIDER_PORT:-5003}"
HOST="${CRUXPIDER_HOST:-127.0.0.1}"

cd "$ROOT_DIR"

echo "CRUXpider bootstrap"
echo "workspace: $ROOT_DIR"
echo "venv: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

if [ "${CRUXPIDER_SKIP_TESTS:-0}" != "1" ]; then
  "$VENV_DIR/bin/python" -m unittest discover -s tests -v
fi

echo "Starting CRUXpider on http://$HOST:$PORT"
exec "$VENV_DIR/bin/python" app.py
