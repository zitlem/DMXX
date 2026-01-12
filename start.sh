#!/bin/bash

# DMXX Startup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"

# Read from config.json, fall back to env vars, then defaults
if [ -f "$CONFIG_FILE" ]; then
    PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('port', 8000))" 2>/dev/null || echo "${DMXX_PORT:-8000}")
    HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('host', '0.0.0.0'))" 2>/dev/null || echo "${DMXX_HOST:-0.0.0.0}")
else
    PORT="${DMXX_PORT:-8000}"
    HOST="${DMXX_HOST:-0.0.0.0}"
fi

cd "$SCRIPT_DIR"

# Kill any existing DMXX process on the same port
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "Stopping existing process on port $PORT..."
    kill $(lsof -ti:$PORT) 2>/dev/null
    echo "Waiting 5 seconds for clean shutdown..."
    sleep 5
fi

# Build frontend if dist doesn't exist
if [ ! -d "frontend/dist" ]; then
    echo "Building frontend..."
    (cd frontend && npm run build)
fi

echo "Starting DMXX on http://$HOST:$PORT"

# Try to find uvx in common locations (helps when running with sudo)
if command -v uvx &> /dev/null; then
    UVX_CMD="uvx"
elif [ -f "$HOME/.local/bin/uvx" ]; then
    UVX_CMD="$HOME/.local/bin/uvx"
elif [ -f "/home/ai/.local/bin/uvx" ]; then
    UVX_CMD="/home/ai/.local/bin/uvx"
else
    echo "Error: uvx not found. Please install uv first."
    exit 1
fi

exec $UVX_CMD --with-requirements backend/requirements.txt \
    uvicorn backend.main:app --host "$HOST" --port "$PORT"
