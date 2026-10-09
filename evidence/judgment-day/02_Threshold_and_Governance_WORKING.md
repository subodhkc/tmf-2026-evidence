# ARTIFACT 2 — THRESHOLD & GOVERNANCE
**DEVIN EVENT-DAY WORKING MIRROR — Drive copy remains canonical.**

## Frozen governing instances (unchanged — do not edit)
| Control | Policy ID | Digest | Rule |
|---|---|---|---|
| C7 | `ae6dda36-4bac-4fb6-9c48-4def287fe79b` | sha256:45f1abaf…e311 | 10-event manifest; NEGOTIATION required |
| C16 (ACN-COST-001) | `547f4a67-76eb-4bf3-befb-c1212ae23f81` | sha256:944212e6…bfe5 | c16-cap-v1: total tokens/run LTE 60,000 |

## C9
**FROZEN + ASSESSED.** Policy `346b5f43-58eb-44f8-a74e-45cfde746d74` (`c9-duration-thresholds-v2`), baseline `c9-duration-baseline-tmf-modaas@v1`: metric `aws.bedrock-agentcore.duration_ms`, LOWER_IS_BETTER, MEAN per agent-window; baselines customer=6,781 ms · IT=8,917 ms · network=12,141 ms; D=100%, B9=0%. Two assessed SATISFIED results: `fault-1791183079-256a5e` (`ctr-214db6a9…`, worst +7.5%) and `fault-1791183213-228329` (`ctr-72f8118b…`, worst +28.5% — an intended-degradation exercise that did not degrade; honest keep, NOT a breach). Assessment-eligible breach: NOT_ESTABLISHED. Threshold defense: worst qualified healthy normalized degradation +86.3%; D=100% was the smallest tested coarse candidate (25/50/75/100) rejecting none of the 37 qualified calibration windows; the exploratory ~95% candidate (86.3×1.10=94.93) was not adopted — false precision from N=37 single-day calibration population. (The earlier "UNFROZEN / KPI candidate" state below is HISTORICAL — superseded by this freeze.)

## Platform guardrail vs HAIEC governing cap — keep distinct
`modaas-ceiling` (AgentgatewayPolicy, `tokens: 2,500,000/Hours` on listener `llm`) is a **PLATFORM GUARDRAIL — SEPARATE FROM the C16 GOVERNING CAP**. It is not a HAIEC policy and must not be cited as C16 enforcement. Deployed-semantics finding (v1.4.1, v1alpha1): `tokens` = LLM input+output tokens, post-completion charging; no enforcement observed on the runaway window → TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY (organizer-side item, not a HAIEC result).

## Governance posture
- Event freeze: BLOCKED — frozen policies/results immutable this event.
- Approval chain: identity established (ec2-user@team: agents/models; system-admin: tools). Runtime currency: YES (agents, approved==running); NOT_ESTABLISHED for tool implementation digests.
- Desired-state drift open: agent CR spec `04b512e0…` unreconciled; any reconcile would run an unattested image — do not edit AgentConfigs.
