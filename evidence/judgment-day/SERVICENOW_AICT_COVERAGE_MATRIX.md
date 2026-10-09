# ServiceNow AICT Coverage / Blind-Spot Matrix — TM Forum Event

Companion to `SERVICENOW_AWS_IDENTITY_RECONCILIATION.md`. Connector resolution
is organizer-reported but participant-unverified (no live access from this
machine). All AICT cells are `PENDING_VERIFICATION` until the reconciliation
protocol runs.

| SURFACE | AICT_STATE | AWS_NATIVE_STATE | HAIEC_STATE | AUTHORITATIVE_SOURCE | LIMITATION |
|---|---|---|---|---|---|
| Agents (customer / IT / network-resolution) | UNKNOWN | OBSERVED (runtime telemetry, approved digests) | OBSERVED + inventoried (assessed system `4043efee…`) | AWS runtime + HAIEC | AICT `sys_id` not yet captured |
| Models (bedrock model ids) | UNKNOWN | OBSERVED (gateway model-request records) | OBSERVED | gateway/audit | AICT model discovery unverified |
| Prompts / config | UNKNOWN | OBSERVED (spec snapshots) | OBSERVED (snapshots) | AWS CR specs | AICT prompt discovery likely NOT_EXPOSED — do not force |
| Tools (registered tool list) | UNKNOWN | OBSERVED (`gen_ai.agent.tools` telemetry) | OBSERVED | runtime telemetry | AICT tool discovery unverified |
| AgentCore runtime | UNKNOWN | OBSERVED | OBSERVED | AWS | |
| AgentCore endpoint | UNKNOWN | OBSERVED | OBSERVED | AWS | |
| Gateway (`modaas-agw`, listener `llm`) | UNKNOWN | OBSERVED (91-call series) | OBSERVED | gateway logs | platform-owned surface |
| Guardrails (Cedar policies, ModelConfig pause) | UNKNOWN | OBSERVED (deny records, withdrawal exercise) | OBSERVED | Cedar/gateway | |
| MCP servers | UNKNOWN | PARTIAL (405 probe traffic observed) | OBSERVED | gateway | |
| Sessions | UNKNOWN | OBSERVED (audit records) | OBSERVED | audit store | self-written, corroborated |
| Traces | UNKNOWN | OBSERVED (AgentCore spans) | OBSERVED | OTel/CloudWatch | AICT trace discovery unverified |
| Evaluations | UNKNOWN | organizer grading | OBSERVED (Control Test ctrs) | HAIEC Control Test | AICT is not the verdict engine |
| CloudWatch/log source | UNKNOWN | OBSERVED | OBSERVED (live forwarder, dedupe) | CloudWatch→HAIEC OTLP | |
| Human actions | UNKNOWN | — | PROVEN for email/webhook ack (synthetic test) | dispatcher receipts | ServiceNow human loop UNKNOWN |
| Incidents | UNKNOWN | n/a | NOT_WIRED | — | connector ≠ incident rights |

## Cross-platform judge story (read-only, current truth)

```
AWS AgentCore ── native runtime + CloudWatch evidence ──┐
                                                        ├─→ HAIEC
ServiceNow AICT ── enterprise asset/discovery identity ─┘   reconciles identities
                                                            binds evidence
                                                            applies frozen policy
                                                            deterministic Control Test
                                                            preserves gaps/limitations
```

If human-loop proof later succeeds: `SYNTHETIC_NON_SCORED_GOVERNANCE_DEMO →
ServiceNow incident → queue/recipient → ack/silence → sys_id bound back`.
ServiceNow is NEVER the verdict engine.

**Authority order:** native AWS/OTel/gateway = preferred runtime truth ·
AICT = enterprise inventory + cross-platform governance corroboration ·
HAIEC = assurance evaluation.
