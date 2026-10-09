# TM Forum — Five-Plane Event Assurance Matrix

> REQUESTED | POLICY_AUTHORIZED | EFFECTIVELY_GRANTED | CODE_CAPABLE | OBSERVED —
> independent evidence planes, not a causal proof chain.
> PERMISSION != DELEGATION. DECLARED != OBSERVED. CONFIGURED != EXECUTED.

| Plane | Event evidence | State | Ref |
|---|---|---|---|
| REQUESTED | Scenario intents (S1/S2/S3), declared run manifests, ODA/CR desired state | ESTABLISHED | `run-declared-*.jsonl`, `s1-audit-*`, `s3-audit-*` |
| POLICY_AUTHORIZED | Cedar ALLOW/DENY decisions, Bedrock guardrail decisions, modaas-ceiling policy attachment | ESTABLISHED | `../enforcement/gateway-fault-1791164066-bdd7e3.json` |
| EFFECTIVELY_GRANTED | IAM policies snapshot, authority matrix, flat bootstrap PDP identity, shared runtime token | PARTIAL — grants enumerated; per-asset identity granularity limited (G-018) | `../iam-authority-matrix.json`, `../iam_policies_snapshot.json` |
| CODE_CAPABLE | Supplied agent spec scan: model+tool surfaces present, **no peer-agent/A2A invocation primitive**; capability-withdrawal proof (ModelConfig) | PARTIAL — capability surface bounded by supplied image | `../../KUSHAL_REVIEW_CARD.md`, `../monitoring-chain/ORGANIZER_KILL_SWITCH_EXERCISE.md` |
| OBSERVED | OTel spans, gateway per-call logs, CloudTrail AssumeRole (x5), audit records, run scores | ESTABLISHED for covered edges; **NEGOTIATION edge MISSING** (0/835 audit records) | `../../logsense-event/event-evidence/runs/` |

## What the matrix establishes

- Configured peer capability (spec declares peer agents) != observed
  delegation — the NEGOTIATION leg is MISSING, not failed-authorized.
- ServiceNow AssumeRole strengthens OBSERVED cross-platform connector
  operation ONLY — it does not raise AICT discovery, identity, or governance
  planes.
- DAI evaluation `tmf-dai-c7-negotiation-001` returned overallState=UNKNOWN
  for the negotiation delegation — formal confirmation the delegation is
  unproven, not disproven (`TMF_DAI_EVALUATION.json`).
