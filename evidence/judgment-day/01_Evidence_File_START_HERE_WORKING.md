# ARTIFACT 1 — EVIDENCE FILE (START HERE)
**DEVIN EVENT-DAY WORKING MIRROR — Drive copy remains canonical until ChatGPT reconciliation.**
Updated: 2026-10-05 · Sources: persisted HAIEC results, platform native records, this-pass read-only inspections.

## Headline state
| Item | State |
|---|---|
| Assessed system | `4043efee-cec6-4007-954b-1f8da2273f35` |
| C16 pair | PASS `ctr-237f3928…` (35,559/60,000) + BREACH `ctr-6d142008…` (106,829/60,000), same frozen policy/digest → **COMPARABLE** |
| C7 | 9/10 — NEGOTIATION event absent in all tested scenarios (incl. S3 attempt `fault-1791179120-30b2dc`) |
| C9 | FROZEN + ASSESSED — policy `346b5f43-58eb-44f8-a74e-45cfde746d74` (`c9-duration-thresholds-v2`, baseline `c9-duration-baseline-tmf-modaas@v1`, D=100%, B9=0%); two assessed SATISFIED results (`fault-1791183079-256a5e`, `fault-1791183213-228329`); assessment-eligible breach NOT_ESTABLISHED |
| LIVE_HAIEC_TELEMETRY | **PROVEN** — binder `52ec5f04-c01a-4715-ae46-6bef3260b505`, participant forwarder `handover/live_forwarder.py`, zero protected-platform mutation |
| Token ceiling (platform) | **TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY** (deployed v1.4.1/v1alpha1: tokens = LLM tokens; no enforcement observed) |
| Approval identity | ESTABLISHED for all material assets |
| Approval-current-for-runtime | YES for agents (approved digest == running); tools = phase-level only (implementation digest unreadable) → NOT_ESTABLISHED |
| CR spec drift | CR_SPEC_AHEAD_OF_RECONCILED_STATE (spec `04b512e0…` pending; runtime `2f6e4556…` == approved) |
| Audit corroboration | SELF_REPORTED_CORROBORATED (model-request results vs /modaas/evidence + gateway token parity) |
| Official C16 package | STAGED_LOCAL_NOT_SUBMITTED (`package-dryrun-c16/`, VM sync pending) |

## Live telemetry (PROVEN path)
CloudWatch (5 log groups) → `live_forwarder.py` (cursor, native-id dedupe, prompt/body stripped) → OTLP/HTTP JSON → binder `52ec5f04` → persisted evidence (evidenceRefs returned, verified read-side with org context). 1,384 records mirrored; 226 dedupe-skips. Non-assessed connectivity test used runRole=CONNECTIVITY_TEST, assessment=false.

## C16 gateway corroboration (PASS run `fault-1791167110-5e3126`)
Platform gateway records, pulled independently: **8 calls · 34,917 input · 642 output · 35,559 total — exact match** to LogSense + audit trail. S3 run: 20,227 tokens — exact match.

## Correlation-key matrix (surface-specific; trace_id does NOT join every source)
| Source A | Source B | Primary key | Secondary | Confidence | Limitation |
|---|---|---|---|---|---|
| audit `model-request-result` | `/modaas/evidence` decisions | `action_id` | correlation_id | HIGH | — |
| audit records | gateway LLM records | token-total parity + run window | request ordering | HIGH (aggregate) | no per-call gateway action_id |
| AgentCore span ↔ AgentCore span | same-runtime | `trace_id` | span_id/parent | HIGH | per-invocation only |
| run ↔ all surfaces | whole-run | `run_id` (declared, self-reported) | event timestamps | MEDIUM | run_id not in platform records; join is time+trace |
| gateway call ↔ agent call | gateway trace | `request_traceparent` | — | MEDIUM | audit `trace_id` ≠ gateway `trace.id` (different id spaces) |
| mirrored telemetry ↔ native | forwarded records | native record id (dedupe key) | producerRunId | HIGH | provenance labeled, not native |

## Security findings carried forward
- Direct model invoke denied for INSPECTED participant + runtime roles only (not universal).
- Flat bootstrap authorization principal observed; no per-asset deny exercised.
- Named platform ceiling exists but did not enforce on tested window — enforcement anomaly, semantics confirmed per deployed CRD.

## Gaps not closed
C7 NEGOTIATION (ORGANIZER_DEPENDENCY � no A2A provider exists); ServiceNow facilitator activation; ~64KB bundle intake limit; VM-side package sync.
