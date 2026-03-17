#!/bin/bash

set -e

echo "Starting CRUXpider..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=app.py
export FLASK_ENV=development
export CRUXPIDER_PORT="${CRUXPIDER_PORT:-5003}"

echo "CRUXpider will be available at http://127.0.0.1:${CRUXPIDER_PORT}"
python app.py
