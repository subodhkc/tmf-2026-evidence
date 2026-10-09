# TM Forum — Evidence Quality / Corroboration Matrix

> Source authority decides what a record can establish.
> SELF_REPORTED_BUT_CORROBORATABLE is an honest middle tier — agent-writable
> does not mean forged.

| Source | Authority tier | Native vs derived | Self-reported? | Independent? | Corroborated? | Establishes | Cannot establish |
|---|---|---|---|---|---|---|---|
| AWS CloudTrail (AssumeRole x5) | platform-attested | native | no | yes | yes (IDE-native capture) | connector operation | AICT discovery/identity |
| Gateway per-call logs | platform-attested | native | no | yes | yes (token series, pod identity) | runtime traffic/enforcement timing | HAIEC verdicts |
| Cedar / guardrail decisions | platform-attested | native | no | yes | yes | runtime ALLOW/DENY | post-run control result |
| CloudWatch / OTel spans | platform-attested | native | no | yes | partial (clock comparability unproven) | observed spans/durations | delegation semantics |
| ODA/CR status | platform-attested | native | no | yes | yes | desired-vs-handled state | intent fulfillment |
| AgentCore identity | platform-attested | native | no | yes | partial (flat bootstrap principal) | caller surface | per-asset identity granularity |
| ServiceNow AssumeRole/AICT | third-party attested | native | no | yes | connector op yes; discovery UNKNOWN | connector ACTIVE | full AICT inventory/governance |
| Agent-written audit records | agent self-reported | native (self-written) | **yes** | no | **yes** — platform `/modaas/evidence` action_ids + gateway usage corroborate | declared agent narrative within shared-token scope | independent truth alone (shared-token forge-write exposure: SEC-01) |
| HAIEC OTLP copy | derived | derived (participant forwarder) | n/a | partial | yes (binder 52ec5f04 persisted) | participant-side reconstruction | canonical platform state |
| LogSense measurement | derived | derived | n/a | n/a | recomputes from bound evidence | deterministic math shown to judge | new evidence facts |
| HAIEC persisted Control Test | participant-attested | derived verdict | n/a | n/a | reproducible from inputs+policy | control verdict under frozen policy | enforcement |

## Reading

- Self-reported audit records carry `SELF_REPORTED_BUT_CORROBORATABLE` status —
  corroborated where platform-attested action_ids/usage overlap; never treated
  as forged merely because the shared token could write them (that capability
  is itself SEC-01).
- Derived copies (OTLP forwarder, LogSense) are reconstruction/measurement
  surfaces — the ledger is not the interpreter.
