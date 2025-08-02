#!/bin/bash
# Development run script for RV Media Player
# This script runs the application from the source directory

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the script directory
cd "$SCRIPT_DIR"

# Set environment variables
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
export FLASK_APP=app/app.py
export FLASK_ENV=development

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "No virtual environment found. Using system Python..."
fi

# Run the application
echo "Starting RV Media Player..."
echo "Access the web interface at: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo ""

python -m app.app
