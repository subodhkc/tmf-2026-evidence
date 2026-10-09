#!/usr/bin/env bash
# Install the preserved LogSense TM Forum event workbench into the Workshop IDE.
# Least-invasive: dedicated venv, vendored code via .pth, dedicated workspace.
# Layout: ~/logsense-event (this bundle) + ~/logsense-event-workspace (generated).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # the logsense-event bundle dir
VENV="${LOGSENSE_VENV:-$HOME/venvs/logsense-event}"
WORKSPACE="${LOGSENSE_WORKSPACE:-$HOME/logsense-event-workspace}"
export LOGSENSE_EVENT_HOME="$HERE"
export LOGSENSE_WORKSPACE="$WORKSPACE"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "Python 3.10+ required. Set PYTHON=/path/to/python3.11"; exit 1; }

mkdir -p "$WORKSPACE"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
# core deps + UI (streamlit) + local API (fastapi/uvicorn) + MCP extras
"$VENV/bin/python" -m pip install --quiet -r "$HERE/code/requirements.txt" \
    streamlit fastapi "uvicorn[standard]" mcp
SITE="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
echo "$HERE/code" > "$SITE/logsense-event.pth"

"$VENV/bin/python" -c 'import logsense; print("LogSense", logsense.__version__, "importable")'
"$VENV/bin/python" "$HERE/scripts/load_event_state.py"

cat <<EOF

LogSense event workbench installed.
  code:      $HERE/code (pinned, see code/LOGSENSE_VERSION.txt)
  workspace: $WORKSPACE
  start UI:  $HERE/scripts/start-logsense-ui.sh     (0.0.0.0:8501)
  start API: $HERE/scripts/start-logsense-api.sh    (127.0.0.1:8765)
  verify:    $HERE/scripts/verify-logsense-event.sh
EOF
