# 08 — Two Distinct Enforcement Surfaces (second enforcement point = PROVEN)

Runtime policy enforcement is proven at **two separate points** — the governed-model call path
and the governed-tool path — both through the same extAuth/Cedar evaluation, each carrying
`action_id`/`x-modaas-action-id` binding back to named runs.

| Surface | Decision | Example | Where |
|---|---|---|---|
| Model ALLOW | 200 + action_id | `4bfa786e-f143-4001-ae88-a2b7de79cda4` (IT agent, `fault-1791183079-256a5e`) | audit `model-request-result` + traceparent |
| Model DENY | **403 `MalformedToolCall`** | `fb0e7a49-ac55-4e7f-8c37-9bb3268706d6` (network agent, `fault-1791164066-bdd7e3`, 01:40:33Z) | `enforcement/audit-fault-1791164066-bdd7e3.jsonl` |
| Tool ALLOW | tool-invocation executed | `customer-records` step 1.5, every assessed run | audit `tool-invocation` records |
| Tool DENY | `result_summary=Input blocked by policy.` | `runbook-lookup` + `network-twin` under cid `customer-experience-agent-1791145515` (Oct-4 20:28/20:30Z) | `enforcement/audit-fault-1791164732-1092c5.jsonl` + gateway extAuth `/mcp/*` |
| Content guardrail | ALLOW/BLOCK | Bedrock guardrail decision records | pass/breach `modaas_evidence.jsonl` |

## Facts

- `action_id` present on **245/245** governed model calls across assessed runs (audit-store
  `model-request-result` records joined to `/modaas/evidence` platform decisions 1:1).
- extAuth FailClosed: all gateway listeners enforce; deny path terminates malformed/policy-
  violating calls before execution.
- **Limitation (disclosed):** tool-invocation audit records do **not** echo `action_id` — the
  model-path echo is complete; the tool-path correlation is via correlation_id/trace_id+timing,
  not action_id echo. Enforcement itself is established; the audit-echo field is the gap.

## Files

- `enforcement/audit-fault-1791164066-bdd7e3.jsonl` — model DENY run (403 MalformedToolCall)
- `enforcement/audit-fault-1791164732-1092c5.jsonl` — tool-policy denials ("Input blocked by policy.")
- `enforcement/gateway-fault-1791164066-bdd7e3.json` — gateway-side trace for the deny run
- `enforcement/deny-probe-evidence.jsonl` — controlled allow/deny probe records
- `enforcement/run-declared-fault-1791164066-bdd7e3.jsonl` — pre-run declaration
