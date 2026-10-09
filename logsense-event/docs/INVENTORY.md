# logsense-event — inventory and classification

| Item | Path | Class |
|---|---|---|
| LogSense source, pinned | `code/logsense/` (commit 0122cf7, v2.0.0rc1) | CODE |
| Version pin | `code/LOGSENSE_VERSION.txt` | CODE |
| Python deps | `code/requirements.txt` | CODE |
| Real run evidence (11 run dirs) | `event-evidence/runs/` | PORTABLE_EVENT_STATE |
| Run registry / gap list / run-ids | `event-evidence/{register.yaml,gap-list.md,run-ids.txt}` | PORTABLE_EVENT_STATE |
| Competition Evidence Bundles + C9/C16 measurement JSONs | `analysis-snapshots/` | PORTABLE_EVENT_STATE (analysis snapshots) |
| IAM authority matrix / policy snapshot | `config/*.json` | PORTABLE_EVENT_STATE |
| Provider env template | `config/env.example` | TEMPLATE (no secrets) |
| Install/start/verify scripts | `scripts/` | CODE |
| MCP/api docs | `docs/` | DOCS |
| Generated workspace | `~/logsense-event-workspace` | MACHINE_LOCAL (regenerated deterministically) |
| venv | `~/venvs/logsense-event` | MACHINE_LOCAL / CACHE |
| `__pycache__`, pip caches | — | CACHE (excluded) |
| Sample/demo case | none shipped | SAMPLE/DEMO (absent — verify script asserts) |

Excluded deliberately: AWS credentials, API keys, tokens, personal local paths,
the 24MB+ raw span dumps (audit/evidence JSONLs retained), unrelated cases,
stale analysis. `killswitch-exercise.txt` contains no credentials.

Native/event evidence is authoritative; HAIEC GENERIC_RECORD projections are
not packaged as the raw source.
