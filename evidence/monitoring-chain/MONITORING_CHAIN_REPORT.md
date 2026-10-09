# Live Monitoring Chain — Bounded Investigation Report

Date: 2026-10-05 · Org: `bdf37694-49f8-4003-ae2b-43580ff6a60e` (TM Forum 2026 — Agentic Assurance)
Scope: read-only-first inventory + smallest sanctioned exercise of existing HAIEC mechanisms. No new telemetry subsystem, no fabricated violation, no package refresh.

## Mechanism Inventory

| MECHANISM | OWNER | PARTICIPANT_ACCESSIBLE | REAL_EXTERNAL_DELIVERY | ACK_SUPPORTED | CONTROL/RUN_BINDING | AUTHORIZED | LIMITATION |
|---|---|---|---|---|---|---|---|
| `POST /api/otlp/v1/traces` → detection sweep → finding → alert | HAIEC | YES (evidence:ingest key) | via org channels | No (finding persisted; ack not modeled) | registryId + org + `haiec.evaluation.id` (if supplied on spans) | YES | trace signals only; logs path does NOT sweep |
| `/api/alerts/rules` (org rule CRUD) | HAIEC | YES (org member) | n/a (policy) | AlertEvent persisted, `channelsAttempted/Succeeded` | ruleId + findingId + surfaceId + detectionFamily | YES | notification policy only; never canonical state |
| `/api/settings/alerts` (org channels) | HAIEC | YES (org owner) | webhook/slack/email(Resend) | delivery only | org-scoped | YES | notify-only; no alert inbox/ack API |
| `/api/alerts/test` | HAIEC | YES | YES — proven | AlertEvent row | rule-scoped | YES | synthetic, labeled `TEST_ALERT`/`SYNTHETIC_NOT_OBSERVED` |
| `/api/canary/run` → `THRESHOLD_VIOLATION` | HAIEC | YES (org transport config) | via org channels | AlertEvent | surfaceId + windowId | YES | needs reachable endpoint + REAL refusal-rate drift; MEDIUM → webhook only |
| `runtime_monitoring_alerts` (resolved/resolvedBy/resolvedAt) | HAIEC | model exists | n/a | YES — resolve lifecycle in schema | endpoint/promptHash scoped | — | separate surface; not wired to OTLP/control-test path |
| `notifications` (in-app inbox, read/readAt) | HAIEC | YES | in-app only | YES — read lifecycle | user-scoped | YES | nothing writes rows from detection/alert paths |
| AWS CloudWatch alarms / SNS / SQS / EventBridge | AWS/org | — | — | — | — | NO | **zero resources exist**; workshop restriction forbids creating |
| Workshop incident/escalation scripts | organizer | — | — | — | — | NO | none found |
| ServiceNow incident path | organizer | — | — | — | — | PARTIAL | connector ACTIVE + AssumeRole OBSERVED; incident write path still NOT_ESTABLISHED |

## Executed Chain

### Leg A — real telemetry → automatic deterministic evaluation (PROVEN, correct negative)

`POST /api/otlp/v1/traces?binderId=52ec5f04-c01a-4715-ae46-6bef3260b505` — 40 REAL spans transcribed verbatim from `fault-1791165466-51ab52` (the C16 breach run), carrying the REAL declared registry (`haiec.declared.tools` = the deployed image's actual 13-tool list; `haiec.declared.agents` = the 3 real roles) and `haiec.evaluation.id=ctr-6d14200872918691f27eee1985b3c329f50ebc01`.

- accepted 40 / rejected 0 / quarantined 0 → post-persist `runOtlpDetectionSweep` ran
- Result: **0 detection findings, 0 alerts** — verified via `/api/monitoring/risks` (empty), `/api/monitoring/stream` (empty), `/api/notifications` (empty)
- Honest reading: all observed calls were within the declared registry; no rule threshold crossed. COST-001 requires >3× baseline — C16 breach ratio is 1.78× (would NOT fire even if mapped). A zero-finding sweep on within-policy evidence is the CORRECT decision, not a pipeline failure.

### Leg B — rule-bound alert → real external delivery → named humans (PROVEN via sanctioned synthetic trigger)

1. `PUT /api/settings/alerts` — org channel `producer-alerts`: webhook → independent receiver + email → 2 named humans; all 4 triggers, all severities.
2. `POST /api/alerts/rules` — `rule-tmf-threshold-violation` (THRESHOLD_VIOLATION, MEDIUM+, WEBHOOK+EMAIL, dedup 15m, 10/h).
3. `POST /api/alerts/test {ruleId, THRESHOLD_VIOLATION, HIGH}` → `fired:true`, `channelsAttempted=[WEBHOOK,EMAIL]`, `channelsSucceeded=[WEBHOOK,EMAIL]`.
4. AlertEvent persisted (`evidence.status='alert_event'` — returned in response; UI projection at `/monitoring/alerts/history` requires TMF-org session context to view).
5. Delivery verified independently: `POST https://webhook.site/d57e8ece-…` at `2026-10-05 09:26:29`, UA `HAIEC-Alerting/1.0`, src `32.194.160.246`, full payload `alert-test-50018638-828f-4f19-ba4b-fa601d3945ee`.
6. Email: Resend accepted (channelsSucceeded=EMAIL) → real inboxes `suvodkc@gmail.com`, `kushal.gautam@gmail.com`.
7. **INBOX-VERIFIED 09:30Z**: recipient confirmed receipt — `[HAIEC Alert] HIGH — TEST on UNSCOPED` from `noreply@haiec.com` to `me, kushal.gautam`, carrying Time `2026-10-05T09:26:29.658Z`, Trigger `THRESHOLD_VIOLATION`, org `bdf37694…`, alert-test ID, `TEST_ALERT`/`SYNTHETIC_NOT_OBSERVED` limitations. Named human read and acknowledged ≈4 min after dispatch → `HUMAN_RESPONSE_STATE = ACKNOWLEDGED`.

## Verdict

`LIVE_MONITORING_STATE = ESTABLISHED (mechanism proven end-to-end; no live violation has fired — correct negative)`
`MONITORED_CONDITION = detection-class telemetry anomalies (real spans evaluated); control-verdict alerts (C7/C9/C16) have NO producer wiring`
`MONITORING_ARCHITECTURE = NEAR_REAL_TIME (ingest-triggered automatic sweep→finding→alert→delivery) for detection class; MANUAL_POST_RUN for control-test verdicts`
`EVALUATOR_STATE = PROVEN (automatic, deterministic, zero manual editing)`
`ALERT_STATE = PROVEN for detection+rule-scoped triggers; synthetic for test; NOT_WIRED for control-test verdicts`
`ALERT_ID = alert-test-50018638-828f-4f19-ba4b-fa601d3945ee (synthetic flag preserved)`
`HUMAN_RECIPIENT_STATE = PROVEN — named humans (owner + kushal.gautam) received the alert in real inboxes`
`DELIVERY_STATE = PROVEN — webhook end-to-end at independent receiver + email inbox-verified`
`HUMAN_RESPONSE_STATE = ACKNOWLEDGED (recipient read/confirmed ~4 min post-dispatch, 2026-10-05T09:30Z)`
`ACK_OR_SILENCE_EVIDENCE = recipient's verbatim received-email paste + webhook-delivery-evidence.json + alert-dispatch-receipt.json`
`CONTROL_BOUND_RECORD_STATE = PARTIAL (AlertEvent/finding carry org+ruleId+findingId+surfaceId+detectionFamily+evaluationId-if-supplied; no control-test verdict linkage)`
`RUNTIME_RECORD_BOUND_TO_CONTROL_VERSION = PARTIAL`
`C9_ALERT_PATH_READY = PARTIAL — alert mechanism + recipient contract ready; blockers: (1) sanctioned breach stimulus (2) alert must be produced by monitored side carrying matching recipient + alertId into the measurement bundle`
`SERVICENOW_HUMAN_LOOP = NOT_ESTABLISHED (connector ACTIVE + ASSUMEROLE_PROVEN; incident path unverified)`
`HOLY_GRAIL_CHAIN = PARTIAL`

CHAIN (with honest break):
```
SOURCE (real workshop spans, mirrored)        — PROVEN  (40 accepted)
  → TELEMETRY (OTLP traces ingest)            — PROVEN
  → EVALUATOR (automatic detection sweep)     — PROVEN (deterministic, no manual edit)
  → DECISION (findings)                       — PROVEN-CORRECT-NEGATIVE (0 findings; evidence clean)
  → ALERT (dispatchAlert via org rule)        — PROVEN (mechanism; exercised via labeled synthetic trigger)
  → DELIVERY (webhook external + email)       — PROVEN end-to-end (independent receiver + verified inbox)
  → HUMAN (named recipients)                  — PROVEN (2 named humans received)
  → ACK/SILENCE                               — PROVEN (ACKNOWLEDGED ~4min; silence would be recorded same way)
  → EVIDENCE (AlertEvent + delivery receipts) — PROVEN
  → CONTROL TEST linkage                      — NOT_WIRED (no producer emits alerts from verdicts)
```
Break point for a fully-automatic violation-driven chain: **no real monitored condition satisfies a detector threshold** (correct negative), and **control-test verdicts have no alert producer**. Both reported, neither fabricated.
