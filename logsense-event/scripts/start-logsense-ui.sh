#!/usr/bin/env bash
# Start the LogSense TM Forum workbench UI. Bind 0.0.0.0:8501 for IDE preview/forwarding.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${LOGSENSE_VENV:-$HOME/venvs/logsense-event}"
export LOGSENSE_WORKSPACE="${LOGSENSE_WORKSPACE:-$HOME/logsense-event-workspace}"
export LOGSENSE_EVENT_HOME="$HERE"
HOST="${LOGSENSE_UI_HOST:-0.0.0.0}"
PORT="${LOGSENSE_UI_PORT:-8501}"
exec "$VENV/bin/python" -m logsense.cli ui --host "$HOST" --port "$PORT" --headless
