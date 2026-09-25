#!/usr/bin/env bash
# ==============================================================================
# start_server.sh — Robust startup script for Pond Planning System
# ==============================================================================

set -e

PROJECT_DIR="/home/student/pond-project"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
VENV_UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
PORT=3000
HOST="0.0.0.0"
LOG_FILE="$PROJECT_DIR/server.log"

cd "$PROJECT_DIR"

# Check if already running on port 3000
PID=$(pgrep -f "uvicorn app.main:app.*$PORT" || true)
if [ -n "$PID" ]; then
    echo "[$(date)] Server is already running on PID $PID"
    exit 0
fi

echo "[$(date)] Starting Pond Planning System on http://$HOST:$PORT..."

# Rotate server.log if larger than 20MB to prevent disk exhaustion
if [ -f "$LOG_FILE" ]; then
    FILESIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$FILESIZE" -gt 20971520 ]; then
        mv "$LOG_FILE" "$LOG_FILE.old"
        touch "$LOG_FILE"
    fi
fi

# Run uvicorn in background via nohup with closed stdin
nohup "$VENV_UVICORN" app.main:app --host "$HOST" --port "$PORT" </dev/null >> "$LOG_FILE" 2>&1 &
NEW_PID=$!

echo "[$(date)] Server started with PID $NEW_PID"
sleep 2

# Verify server responds
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "[$(date)] Process $NEW_PID is healthy."
else
    echo "[$(date)] ERROR: Process died immediately. Check $LOG_FILE"
    exit 1
fi
