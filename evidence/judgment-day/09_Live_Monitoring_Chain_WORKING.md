# 09 — Live Monitoring → Alert → Human Chain

Evidence directory: `evidence/monitoring-chain/` · Full report: `MONITORING_CHAIN_REPORT.md`

## What is proven (each leg independently inspectable)

```
SOURCE   40 real spans transcribed verbatim from fault-1791165466-51ab52 (the C16 breach run)
  → TELEMETRY   POST /api/otlp/v1/traces  binder 52ec5f04-c01a-4715-ae46-6bef3260b505
                (binder bound to assessed system 4043efee-cec6-4007-954b-1f8da2273f35)
  → EVALUATOR   automatic post-persist detection sweep — deterministic, zero manual editing
  → DECISION    0 findings — CORRECT NEGATIVE (all observed calls within declared registry;
                no rule threshold crossed; C16's 1.78× is below COST-001's 3× spike gate)
  → ALERT       rule-scoped dispatch (dispatchAlertWithRule) + persisted AlertEvent
                (evidence.status='alert_event', channelsAttempted/Succeeded)
  → DELIVERY    WEBHOOK end-to-end to independent receiver (UA HAIEC-Alerting/1.0)
                EMAIL provider-accepted → inbox-verified by named recipient
  → HUMAN       named recipients incl. organizer/judge addresses received the alert
  → ACK         recipient read + confirmed ≈4 min after dispatch (ACKNOWLEDGED)
  → EVIDENCE    alert-dispatch-receipt.json + webhook-delivery-evidence.json + this file
```

## Precise claim boundary (do not overclaim)

- `LIVE_MONITORING_MECHANISM = PROVEN` — the automatic path exists and ran on real spans.
- `REAL_VIOLATION_TO_ALERT = NOT_YET_OBSERVED` — no real monitored condition crossed a detector
  threshold; the sweep's zero-finding on real evidence is the correct verdict.
- `HUMAN_DELIVERY_PATH = PROVEN` — exercised via the **labeled synthetic** test
  (`alert-test-5e7f7b96-…`, `TEST_ALERT`/`SYNTHETIC_NOT_OBSERVED`) through the identical
  production dispatcher real findings use.
- `CONTROL_TEST_VERDICT_TO_ALERT = NOT_WIRED` — HAIEC control-test verdicts (C7/C9/C16) do not
  emit alerts; alerting on verdicts requires a producer-side emit (evaluator-side contract
  expects the monitored system to produce the alert record — C9's `m.monitoring` block).

## Architecture classification

`NEAR_REAL_TIME` (ingest-triggered) for detection-class conditions;
`MANUAL_POST_RUN` for control-test verdict alerting.

## For C9 later

The same architecture satisfies the C9 monitoring contract if organizers supply a sanctioned
breach stimulus: the alert must carry `recipient = sre-oncall@tmf-participant-team` and an
`alertId`; response states include `RESPONDED | NO_RESPONSE_RECORDED | SILENCE_RECORDED` —
`SILENCE_RECORDED` is a legitimate recorded outcome.
