#!/usr/bin/env zsh
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "=========================================================="
echo "  HIVEMIND STUDIO — Apple Silicon Tavern x ComfyUI MVP"
echo "=========================================================="

# Start FastAPI backend on port 8765 (auto-reloads on .py edits without restarting on JSON data saves)
echo "[1/2] Starting FastAPI Backend on http://127.0.0.1:8765 ..."
"$ROOT_DIR/.venv/bin/uvicorn" backend.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir "$ROOT_DIR/backend" --reload-include "*.py" &
BACKEND_PID=$!

trap "kill $BACKEND_PID 2>/dev/null || true" EXIT

# Start Vite Frontend on port 5173
echo "[2/2] Starting Browser Studio UI on http://localhost:5173 ..."
npm --prefix "$ROOT_DIR/frontend" run dev -- --host 127.0.0.1 --port 5173
