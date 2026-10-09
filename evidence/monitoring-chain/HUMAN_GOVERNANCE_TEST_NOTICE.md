# TM Forum Hackathon — Human Governance / Monitoring Test

**Team:** Agentic AI Proof Graph - HAIEC
**Sender:** Subodh Kc — Agentic AI Proof Graph - HAIEC
**Alert:** `alert-test-5e7f7b96-1608-4b17-b8d3-2fc8c5fae291` · Rule `tmf-human-governance-monitoring-test` · fired `2026-10-05T09:51:24.243Z`

## What this is

A **controlled TM Forum Hackathon test** — not a production incident. It validates the
**human-notification leg** of the live monitoring/governance chain:

```
live telemetry → deterministic evaluator → alert → named human → delivery → ack/silence → evidence
```

## Why email

ServiceNow human-loop integration is **not fully available** — facilitator-side AICT
activation/access remains pending. Email via the HAIEC production alert dispatcher is the
available human notification channel for this test.

## What recipients can do

No technical action is required. Recipients may respond with one of:

- **CONTINUE MONITORING**
- **STATIC / HOLD**

A reply, or recorded silence, is captured as the human-response evidence for this test.

## Technical note (for judges)

The alert was produced by the **HAIEC production dispatcher** (`dispatchAlert` +
`dispatchAlertWithRule`, same path real detection findings use) via the sanctioned
`/api/alerts/test` endpoint. The platform's test payload text is fixed by the API schema
and is permanently labeled `TEST_ALERT` / `SYNTHETIC_NOT_OBSERVED` — this companion
document carries the human-facing context the fixed schema cannot express. This alert is
NOT presented as evidence that a real C16/C9 breach fired automatically; it proves the
dispatch → delivery → named-human → ack plumbing.
