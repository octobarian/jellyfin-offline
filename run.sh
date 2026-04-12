#!/bin/bash
# RV Media Player - dev run script
# Runs directly from the repo (no install needed)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="$SCRIPT_DIR"
export FLASK_APP=app/app.py
export FLASK_ENV=development

if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "No venv found - using system Python"
fi

echo "Starting RV Media Player at http://localhost:5000"
echo "Press Ctrl+C to stop"
exec python -m app.app
