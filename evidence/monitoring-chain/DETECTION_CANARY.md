# DETECTION CANARY — synthetic positive-path proof (NON-SCORED)

Date: 2026-10-05 ~10:07Z. Status: PROVEN end-to-end.

## Purpose

Prove the missing leg of the monitoring chain — real OTLP telemetry → automatic
detector → persisted finding → automatic production alert dispatch → delivery —
with ONE clearly labeled synthetic span, fully isolated from all scored evidence.

## Isolation (contamination controls)

| Control | Value |
|---|---|
| Canary AI system | `e363482f-30b8-4ac8-9d2d-c002f0a3daf6` — "TMF Detection Canary — SYNTHETIC NON-SCORED" |
| Canary binder | `a135efe9-e9bd-4a59-9d10-66182c0edb35` (OTLP, created via `/api/telemetry/onboard`) |
| Assessed system `4043efee` / binder `52ec5f04` | UNTOUCHED — assessed workspace shows 94 batches / 7,529 records scoped only to its own binder |
| Span labels | `haiec.test.synthetic=true`, `haiec.run.role=DETECTION_CANARY`, `haiec.run.id=tmf-detection-canary-001`, `haiec.evidence.class=SYNTHETIC_NON_SCORED` |
| Detector used | existing production rule MCP-001 (AR-26) — no new detector created |

## What was sent

One OTLP span to `POST /api/otlp/v1/traces?binderId=a135efe9-…`:
`gen_ai.tool.name = tmf_canary_undeclared_probe` vs declared registry
`haiec.declared.tools = lookup_customer,create_ticket` → satisfies MCP-001
(tool invoked outside the declared registry). No dangerous payload.

## Chain proof (exact IDs behind every arrow)

```
synthetic labeled span → OTLP accepted (1/1, ref 80b5764c…)
→ post-persist detection sweep (automatic)
→ FINDING arf-5da00f32d5a27a06be1f48446f608a44  (AR-26 / MCP-001, HIGH)
→ dispatchDetectionFindingAlerts (production path, trigger AIRISK_FINDING_EMITTED)
→ ALERT alert-a66f3eaa-8c92-4f2a-8e01-b2684e8a8b62
→ WEBHOOK delivered 2026-10-05T10:07:12Z (independent receiver, UA HAIEC-Alerting/1.0)
→ EMAIL dispatched via org channel (6 recipients incl. organizer/judge emails)
```

- Finding persisted + replayable: `GET /api/monitoring/stream?since=2026-10-05T10:00Z` returns it.
- Alert is `ALERT_ONLY` — limitations preserved (`UNDECLARED_TOOL != MALICIOUS`, `NOT_AN_ASSURANCE_DISPOSITION`).

## What this does NOT prove

- No real production violation generated this alert. The trigger was synthetic.
- `REAL_VIOLATION_TO_ALERT` remains `NOT_OBSERVED` — the real 40-span sweep
  produced zero findings, which is the honest correct negative.
- The canary is not scored evidence and does not feed any control verdict.
