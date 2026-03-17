#!/usr/bin/env bash

set -euo pipefail

MODE="${1:-development}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${CRUXPIDER_VENV_DIR:-$ROOT_DIR/.venv}"

cd "$ROOT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -r requirements.txt
"$VENV_DIR/bin/python" -m unittest discover -s tests -v

if [ "$MODE" = "production" ]; then
  exec "$VENV_DIR/bin/gunicorn" --bind "0.0.0.0:${CRUXPIDER_PORT:-5003}" --workers 4 --timeout 120 wsgi:app
fi

if [ "$MODE" = "development" ]; then
  exec "$VENV_DIR/bin/python" app.py
fi

echo "Unsupported mode: $MODE"
echo "Usage: ./deploy.sh [development|production]"
exit 1
