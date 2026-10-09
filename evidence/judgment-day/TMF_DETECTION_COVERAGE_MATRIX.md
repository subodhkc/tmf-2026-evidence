# TM Forum — Detection Coverage Matrix

> Visibility artifact, not an engine. Shows which mechanism owns which claim.
> CONTROL TEST != GENERIC DETECTOR != SECURITY FINDING != SCENARIO GRADER !=
> RUNTIME GUARDRAIL. A result produced by one mechanism must never be cited as
> produced by another.

## Mechanism inventory

| Mechanism | Owner | Input | Output | Proves | Cannot prove |
|---|---|---|---|---|---|
| Frozen Control Test (C7/C9/C16) | HAIEC | Bound evidence + frozen policy/digest | SATISFIED / NOT_SATISFIED verdict | The policy's own question under its frozen semantics | Anything outside the frozen policy scope |
| Generic HAIEC detector (AR rules) | HAIEC | Normalized telemetry/records | detector finding (0 on real traffic) | Presence/absence of detector-known anomaly classes | Frozen-policy violations; verdicts |
| Security/platform finding | organizer-owned, participant-documented | platform observation | qualified finding (SEC-01/02/03, EXP-04, HIS-05) | Qualified surface behavior | Exploitability, compromise |
| Scenario grader (S1/S2/S3) | organizer | run behavior | score (6/8, 5/10, 8/10) | Graded scenario performance | Control satisfaction |
| Runtime guardrail/enforcement | organizer platform | request path | ALLOW/DENY/403/withdrawal | Runtime decision occurred | Post-run control result |

## Item coverage

| Item | Owning mechanism | Result | Detector finding? | Why correct |
|---|---|---|---|---|
| C7 (AIA-LOG-001) | Control Test | NOT_SATISFIED, 9/10, NEGOTIATION missing, B7=10% | N/A | Frozen manifest rule evaluated bound records |
| C9 (346b5f43…) | Control Test | 2 runs SATISFIED; breach NOT_ESTABLISHED | N/A | Frozen duration policy, mean per agent-window |
| C16 PASS (547f4a67…) | Control Test | 35,559/60,000 SATISFIED | N/A | Frozen per-run token cap |
| C16 BREACH | Control Test | 106,829/60,000 NOT_SATISFIED | N/A | Same frozen policy/digest as PASS |
| C7 missing NEGOTIATION | Control Test manifest | absent leg = coverage gap, not fabricated | no | Gap is a coverage result, not a detector anomaly |
| SEC-02 token-ceiling anomaly | Security finding (organizer platform) | confirmed anomaly, mechanism unresolved read-only | no | Platform limiter != HAIEC C16 cap |
| Synthetic MCP canary | detector pipeline proof | finding→alert delivered | yes (synthetic, labeled) | Proves pipeline operability ONLY, never real violation |

## The zero-findings rule

`findings = 0` on real traffic means: generic AR detectors observed no
detector-known anomaly. It does NOT mean "no control violations" and NOT
"system safe" — C16 NOT_SATISFIED coexists with zero generic findings because
the C16 frozen Control Test is not the AR-28 generic COST detector. Neither
mechanism owes the other's answer.

See: `02_Threshold_and_Governance_WORKING.md`, `../../gap-list.md`,
`../monitoring-chain/DETECTION_CANARY.md`.
