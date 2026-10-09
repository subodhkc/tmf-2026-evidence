# Gap list — current truth only

## Organizer/platform dependencies (open)

- **C7 NEGOTIATION**: the supplied agent image writes `pending-live-negotiation` markers but has no
  peer-agent/A2A invocation primitive. Zero negotiation events in all 835 audit records (all teams).
  Requires organizer-sanctioned exposure — participant cannot fix the image.
- **C9 live breach**: two assessed SATISFIED runs under frozen v2 semantics; no sanctioned
  live-degradation stimulus exists to produce a real breach. Organizer ruling pending.
  (Historical degradation is not assessment-eligible; timestamp defect disclosed in
  C9_TIMESTAMP_ERRATUM.md.)
- **Control-test verdict → alert producer not wired**: HAIEC control-test verdicts (C7/C9/C16) do
  not emit alerts. The monitoring chain is proven via the detection/telemetry path; verdict-driven
  alerting is a platform gap. `CONTROL_TEST_VERDICT_TO_ALERT = NOT_WIRED`.
- **C9 real-violation alert not observed**: no real monitored condition crossed a detector
  threshold — the live sweep on real spans produced a correct zero-finding.
- **ServiceNow AICT**: connector ACTIVE + AssumeRole OBSERVED (5 CloudTrail events, ServiceNowAictUser → SgcAictReadOnlyAccessRole, 352826992186-session, Workshop-IDE native capture; participant-scope reproduction region-limited). AICT inventory discovery + participant incident path remain NOT_ESTABLISHED.
  Email/webhook remains the proven human-notification channel.
- **AWS-native notification resources**: zero SNS topics / CloudWatch alarms / EventBridge rules /
  SQS queues exist in the account — no organizer-provisioned alert route was available.

## Honest evidence limitations (preserved)

- RUN_START is operator-declared; no platform run-start signal exists.
- 64KB per-record ingest bound: oversized runs (e.g. 2.83M-token runaway) cannot be evaluated.
- `modaas-ceiling` `local[].tokens: 2,500,000/Hours` is LLM input+output tokens on the
  deployed v1.4.1/v1alpha1 schema (request-count reading retracted): runaway run consumed
  2,828,243 tokens / 91 calls; bucket first exceeded at call #85, then 4 post-exhaustion
  requests (#86-89) returned 200 — CONFIRMED enforcement anomaly, organizer-owned (SEC-02).
- Audit-store records are agent self-written under a shared token; corroborated by
  platform-attested `/modaas/evidence` action_ids and gateway usage figures.
- Flat PDP identity: decisions show `ServiceIdentity::"bootstrap-key"`.
- Tool-invocation audit records do not echo `action_id` (model-path echo complete; tool-path
  correlation via correlation_id/trace_id).
- Runtime records bound to control/version: PARTIAL (AlertEvent/finding carry
  ruleId/findingId/surfaceId/evalId; no verdict linkage).
- Provider request-id / retry completeness not fully attested.
- Cross-source subsecond clock comparability not proven.
- `hasMonitoring` was a stale declared field — corrected via canonical API;
  system-scoped `telemetryReadiness` projection verified (SIGNAL_RECEIVED,
  systemBound, 94 batches / 7,529 records). RESOLVED.

- ~~System dashboard monitoring~~ → `telemetryReadiness` projects binder-bound intake correctly; declared field corrected.

## Closed / resolved (removed from open gaps)

- ~~C9 UNESTABLISHED~~ → two assessed SATISFIED runs under frozen v2 policy.
- ~~C9 timestamp labels~~ → disclosed + corrected (erratum file; originals preserved).
- ~~Monitoring/alerting existence~~ → production dispatcher + delivery + named-human ack proven.
- ~~S2 ungraded~~ → organizer-graded 5/10 FAIL ×2 (original + retest), divergence documented.
