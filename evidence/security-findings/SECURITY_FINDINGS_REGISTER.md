# Security & Exposure Register — organizer-owned platform items

Categories below are load-bearing: SECURITY = supported current security finding;
EXPOSURE = observed surface property (no compromise claimed); HISTORICAL = point-in-time,
resolved/superseded.

All findings are **organizer-owned infrastructure/runtime properties**. Participant role:
observe, qualify, document — no unauthorized remediation attempted.

| ID | Finding | Evidence basis | Owner | Participant fix |
|---|---|---|---|---|
| SEC-01 | `PLAINTEXT_SHARED_RUNTIME_CREDENTIAL_EXPOSURE` — the same 32-char shared runtime token appears in cleartext in each supplied agent's spec env (`credentialProviderType`), implying forge-write capability to the shared audit store | agent spec snapshot + iam authority matrix | organizer | none — recommended only |
| SEC-02 | `TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY` — CONFIRMED. `modaas-ceiling` `local[].tokens: 2,500,000/Hours` on listener `llm` (Accepted/Attached=True). Deployed agentgateway v1.4.1 / CRD v1alpha1: `tokens` = **LLM input+output tokens charged post-completion** (installed-schema verified). Scope proof: **1 gateway replica observed** (all 91 calls on pod `modaas-agw-557c7d8d67-gphks`, single log stream — no replica split); same limiter key (`llm`); run duration 5.8 min « 1h window (refill ≈694 tok/s cannot explain ~278k overage in ~15s). Bucket first exceeded at call #85 (cum 2,537,324 — 200 consistent with post-completion charging); **4 subsequent requests #86–89 all returned 200** (+~70k tokens each) — the actual anomaly; #90's 403 is Cedar `MalformedToolCall` (different layer). Mechanism unresolved read-only (post-response charging defect on aws.bedrock path / limiter not fed usage / bucket init). Distinct from the C16 HAIEC cap | gateway logs (per-call token series) + policy snapshot + installed-CRD schema | organizer | none |
| SEC-03 | `PHANTOM_TOOL_CALL / MODEL_TURN_RUNAWAY` — 84 consecutive `tool_calls` turns with only 1 real tool invocation; terminated by Cedar `MalformedToolCall` 403, not by a turn/loop limit | audit + gateway reconstruction | organizer | none |
| EXP-04 (was SEC-04) | `PUBLIC_LISTENER_SCANNER_EXPOSURE` — EXPOSURE: bare-EIP host probes (`/admin`, `/manager/text/list`, `CONNECT`) reach the gateway listeners; all returned 404 | live listener response evidence | organizer | none |
| HIS-05 (was SEC-05) | `CONFIG_APPROVAL / RECONCILIATION DRIFT` — HISTORICAL/RESOLVED: earlier CR desired-digest vs handled-digest drift documented; current snapshot shows `driftDetected=False` | config snapshots (two points in time) | organizer | none |

Raw supporting evidence: `evidence/iam-authority-matrix.json`, `evidence/iam_policies_snapshot.json`,
`evidence/enforcement/` (deny surfaces), audit timelines.

**Claim boundary:** these are qualified observations of organizer-owned surface behavior, not
claims of exploitability. None are participant-remediable within the workshop authority model.
