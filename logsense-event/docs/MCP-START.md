# LogSense MCP — startup

The vendored LogSense ships a canonical MCP server (`logsense.integrations.mcp`).

## stdio (default)

```bash
export LOGSENSE_WORKSPACE=~/logsense-event-workspace
export LOGSENSE_EVENT_HOME=~/logsense-event
~/venvs/logsense-event/bin/python -m logsense.cli mcp
```

Register it with any MCP-capable client as a stdio server using that command.

## streamable-http (loopback)

```bash
export LOGSENSE_MCP_TRANSPORT=streamable-http
export LOGSENSE_MCP_HOST=127.0.0.1
export LOGSENSE_MCP_PORT=8766
~/venvs/logsense-event/bin/python -m logsense.cli mcp
```

## Local API alternative

`scripts/start-logsense-api.sh` runs the canonical FastAPI service at
`127.0.0.1:8765` (uvicorn). Optional bearer: set `LOGSENSE_API_TOKEN`.

## HAIEC MCP (separate, authoritative assurance surface)

HAIEC MCP / Control Test is the authoritative assurance-query surface —
`haiec_control_test_query`, `haiec_judgment_day_status`, telemetry and
governance reads. It is configured against the HAIEC deployment with the
judge-provided key; it is NOT part of this bundle and no HAIEC key is stored
here.
