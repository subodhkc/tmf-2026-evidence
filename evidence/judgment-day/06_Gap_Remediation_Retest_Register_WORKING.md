# ARTIFACT 6 — GAP / REMEDIATION / RETEST REGISTER
**DEVIN EVENT-DAY WORKING MIRROR — Drive copy remains canonical.**

| Gap | Item | State | Evidence / next step |
|---|---|---|---|
| G-005 | Approval chain | **CLOSED (identity)** | approvers established; runtime currency split tracked under G-017 |
| G-006 | Standard evidence surfaces | PARTIAL | not every supported surface exercised; coverage claims limited to tested surfaces |
| G-008 | ServiceNow/AICT | PARTIAL | connector ACTIVE + ASSUMEROLE_PROVEN (5 CloudTrail events, ServiceNowAictUser→SgcAictReadOnlyAccessRole, IDE capture); AICT discovery + human-governance path NOT_ESTABLISHED |
| G-009 | C9 KPI | **CLOSED** | policy 346b5f43 frozen; 2 assessed runs SATISFIED; no breach observed (honest); illustrative +398% proves rule fires |
| G-010 | Official submission | OPEN | package staged locally; VM sync pending (VM_SYNC_PLAN.md); submit.sh not run |
| G-013 | C7 NEGOTIATION | OPEN | tested scenarios produce no genuine invoke_agent negotiation; platform has no A2A tool provider; AgentConfig edit unsafe (pending unapproved image) — organizer-level path required |
| G-015 | Token ceiling | OPEN → organizer | TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY (v1.4.1/v1alpha1: LLM-token semantics confirmed; 2.83M tok, 0×429) |
| G-016 | AWS→HAIEC telemetry | **CLOSED/PROVEN** | participant forwarder + binder 52ec5f04; persisted evidence verified |
| G-017 | CR spec/runtime currency | OPEN | spec `04b512e0…` unreconciled vs running `2f6e4556…`; reconcile would deploy unattested image |
| G-018 | Identity granularity | OPEN | flat bootstrap principal; per-asset differentiation not exercised |
| G-019 (new) | Correlation-key namespaces | OPEN (documented) | audit `trace_id` ≠ gateway `trace.id`; gateway binding is `request_traceparent`; matrix in Artifact 1 |

New-gap note: G-019 added rather than hiding the mismatched trace namespaces.
