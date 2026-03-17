#!/bin/bash

export CRUXPIDER_PORT="${CRUXPIDER_PORT:-5003}"

echo "Stopping CRUXpider..."
pkill -f "python app.py" 2>/dev/null || true
pkill -f "python app_integrated.py" 2>/dev/null || true

PORT_CHECK=$(lsof -ti:${CRUXPIDER_PORT} 2>/dev/null || true)
if [ -n "$PORT_CHECK" ]; then
    kill -9 $PORT_CHECK 2>/dev/null || true
fi

echo "Done."
