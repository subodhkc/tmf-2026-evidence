# LogSense → HAIEC Projection & DAI Applicability

10 evidence-qualified LogSense forensic projections persisted as
`GENERIC_RECORD` evidence records on the assessed system via the LogSense
binder `e349b6c5-a58e-4a4d-8cec-cbadbd1d23b9` (batch digest
`987327678cfce584`, ingestionId recorded in `logsense-findings-ingest.json`).

Object semantics — they are evidence records, NOT canonical finding objects:

| Question | Answer |
|---|---|
| IS_CANONICAL_HAIEC_FINDING_OBJECT | NO — GENERIC_RECORD evidence class |
| IS_QUERYABLE_AS_FINDING | NO — no findings-store entry, no `arf-*` id |
| IS_QUERYABLE_AS_EVIDENCE | YES — system-bound evidence refs on the assessed system |
| IS_VISIBLE_IN_FINDINGS_UI | NO |
| IS_VISIBLE_VIA_MCP | YES — via system evidence surfaces, as records |
| HAS_STABLE_FINDING_ID | NO — evidence refs only |

Smallest canonical step later (not done — audit-only pass): a finding-projection
adapter that mints `arf-*` finding objects bound to these evidenceRefs.
`LOGSENSE_DISCOVERS → HAIEC_RELATES`, preserved.

## HAIEC evidence refs (one per projected finding)

2b2ad186… S2-FALSE-CERTAINTY · b6087579… C7-NEGOTIATION · 349c6a62… TOKEN-CEILING ·
e425300e… RUNAWAY · ff516043… CRED-EXPOSURE · bcd018aa… SCANNER ·
31181d1d… CONFIG-DRIFT · dd59b826… C9-TIMESTAMP · e0dd53fb… C9-HIST-ANOMALY ·
edbfec30… 2ND-ENFORCEMENT

## DAI applicability — CANDIDATE states only (evaluator NOT run)

`DAI_STATE = NOT_EVALUATED` for every row. The states below are EXPECTED
mappings if a delegation comparison were ever evaluated; nothing was
submitted, executed, or persisted.

| Finding | DAI applicable? | State / rationale |
|---|---|---|
| C7 negotiation missing | YES | EXPECTED `UNRESOLVED_DELEGATION_EXPOSURE` — delegation expected but not evidenced; organizer-image dependency |
| S3 safe refusal | YES | EXPECTED `INSIDE_ESTABLISHED_DELEGATION` — escalation stayed within declared constraints |
| S2 false certainty | NO | claim/disposition divergence is not a delegation-plane fact — not forced into DAI |
| C16 spend breach | NO | spend-cap violation; DAI dimensions don't model cost ceilings (delegation scope, not magnitude-of-spend) |
| Token ceiling lag | NO | enforcement property, not delegation comparison |
| Runaway loop | NO | behavioral anomaly |
| Credential exposure | PARTIAL | effectivelyGranted-plane evidence exists; no delegation comparison to evaluate; NOT_EVALUATED |
| Kill-switch prevented effect | N/A (not executed) | revocation/prevented effect is an enforcement fact; would bind to OBSERVED/PREVENTED, not a new plane |

DAI evaluation requires confirmed delegation evidence (`/api/dai/evidence`,
`confirmed:true` literal) — not submitted: the delegation facts are
organizer-owned and confirming them would overclaim.

`DAI_EVALUATOR_EXECUTED = NO` · `DAI_RESULT_PERSISTED = NO` ·
`DAI_RESULT_ID = NONE` · `DAI_STATE = NOT_EVALUATED` (all items).
Any state string above is a candidate expectation, never an evaluated result.

## Proof-chain projection (established edges only)

C16 breach: REQUEST→policy(frozen 547f4a67)→EFFECTIVE_GRANT→OBSERVED(17 calls,106,829 tok)
→enforcement-control NOT_SATISFIED(ctr-6d142008)→evidence(17 event refs)→ALERT(none — verdict→alert not wired). All ESTABLISHED except alert edge = NOT_WIRED.

S2: REQUEST→agents→tool calls→OBSERVED(text "Undetermined")→disposition(auto-resolve)
→FINDING(divergence)→RETEST(identical fail). ESTABLISHED end-to-end.

S3: REQUEST(restricted)→delegation→OBSERVED refusal/escalation. ESTABLISHED.

C7: declared peer target exists → OBSERVED negotiation edge = MISSING (documented).

Kill switch: CONTROL→REVOCATION→GUARD→PREVENTED op→audit→alert→recover —
HAIEC architecture exists; runtime demo NOT_EXECUTED (admin-key mint is
platform-only). SEPARATELY: the organizer guide contains a sanctioned
operator kill-switch procedure ("The kill switch" under Prove-the-governance:
pause ModelConfig → refused/404 disposition → unpause → 3 audit records).
That is the ORGANIZER's runtime path, executed on their platform — distinct
from the HAIEC product capability.
