#!/usr/bin/env bash

set -euo pipefail

PORT="${CRUXPIDER_PORT:-5003}"

pkill -f "python app.py" 2>/dev/null || true
pkill -f "gunicorn .*wsgi:app" 2>/dev/null || true

PORT_CHECK=$(lsof -ti:"${PORT}" 2>/dev/null || true)
if [ -n "$PORT_CHECK" ]; then
  kill "$PORT_CHECK" 2>/dev/null || true
fi

echo "CRUXpider stopped."
