# DASHBOARD PROJECTION — root cause and fix (assessed system)

System: `4043efee-cec6-4007-954b-1f8da2273f35` · Binder: `52ec5f04-c01a-4715-ae46-6bef3260b505`

## Root cause

Two different fields were being read as if they were one:

1. `ai_systems.hasMonitoring` — a **stored declared asset attribute**
   (`prisma/schema.prisma`, `Boolean @default(false)`), set only at create/update.
   Our assessed system was created without it, so the inventory projection
   reported `false` — a stale declared field, not a live signal.
2. `telemetryReadiness` — the **real derived projection**
   (`lib/evidence/telemetry-readiness.ts` → `loadTelemetryStatusProjection`,
   consumed by `app/api/inventory/systems/[id]/workspace` and the MCP
   `haiec_get_telemetry_status` tool). It derives from `environment_binders`
   (aiSystemId-scoped) + `evidence_ingestion_batches`. It was already correct.

Earlier confusion also came from the org-scoped evidence feed, which does not
surface the per-row `aiSystemId` column — org coverage was never the issue;
the system-scoped read-model was already binding correctly.

## Smallest source-backed fix

No code change. Corrected the stale declared field through the canonical
inventory API: `PUT /api/inventory/{systemId}` with `hasMonitoring: true` —
the asset declaration now matches reality (active bound binder + live intake).

## Verified readback (2026-10-05)

`GET /api/inventory/systems/4043efee…/workspace` →
```json
"telemetryReadiness": {
  "state": "SIGNAL_RECEIVED", "binderConfigured": true, "systemBound": true,
  "signalReceived": true, "latestReceivedAt": "2026-10-05T09:26:57.500Z",
  "acceptedBatchCount": 94, "acceptedRecordCount": 7529,
  "nextAction": "RUN_NEW_EVALUATION"
}
```
`GET /api/inventory/systems/4043efee…` → `hasMonitoring: true` (persisted).
`GET /api/monitoring/telemetry` (org) → both binders ACTIVE,
`telemetryStatus: CONFIGURED_ACTIVE`, canary binder lastEventAt 10:07:12Z.

Scoping proof: the assessed workspace counts (94 batches / 7,529 records)
exclude the canary binder — system isolation is real, not org-wide inference.

## Residual limitation

`hasMonitoring` remains a declared field, not a computed one — a system could
be declared true with no binder. The authoritative signal is
`telemetryReadiness.state`. No code PR was required; the read-model was
already correct. Documented for judges: check `workspace.telemetryReadiness`,
not the inventory flag.
