#!/usr/bin/env bash
# Start the canonical local LogSense API. Loopback only by default (127.0.0.1:8765).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${LOGSENSE_VENV:-$HOME/venvs/logsense-event}"
export LOGSENSE_WORKSPACE="${LOGSENSE_WORKSPACE:-$HOME/logsense-event-workspace}"
export LOGSENSE_EVENT_HOME="$HERE"
export LOGSENSE_API_HOST="${LOGSENSE_API_HOST:-127.0.0.1}"
export LOGSENSE_API_PORT="${LOGSENSE_API_PORT:-8765}"
exec "$VENV/bin/python" -m logsense.cli api
