# DETECTION COVERAGE REVIEW — why zero live findings is the correct answer

Owner: `lib/ai-security/rules/agent-detection-rules.ts` (8 producers, 27 rules).
Sweep owner: `lib/ai-security/detection-otlp-hook.ts` (post-persist, non-fatal).
Finding store: `detection-findings-store.ts` → evidence partition `status=detection_finding`.
Alert: `dispatchDetectionFindingAlerts` → org config + active rules (`ALERT != FINDING`).

## Enabled detector inventory

| RULE | FAMILY | INPUT (OTLP attrs) | CONDITION / THRESHOLD | AUTO-ALERT |
|---|---|---|---|---|
| PROMPT-001..005 | PROMPT | `gen_ai.prompt`, `haiec.prior_turn_count`, context size/limit | extraction/jailbreak/override/manipulation/overflow patterns | yes (AIRISK_FINDING_EMITTED) |
| RAG-001..004 | RAG | `gen_ai.rag.chunk_*`, declared knowledge sources | undeclared source, instruction-like chunk, embedding drift, cross-session | yes |
| MEM-001..002 | MEMORY | `gen_ai.memory.operation`, channel/scope + declared | write via undeclared channel / undeclared scope | yes |
| MULTI-001..004 | MULTI_AGENT | `gen_ai.agent.handoff.*` | A→B→A cycle, undeclared handoff, unregistered target, shared surface | yes |
| MCP-001..004 | MCP_TOOL | `gen_ai.tool.name`, server/schema/agent id + `haiec.declared.*` | undeclared tool / server / schema drift / unregistered agent | yes |
| EXFIL-001..004 | EXFIL | `gen_ai.completion`, `gen_ai.tool.payload`, destination allowlist, prompt signature | sensitive-content patterns in output/payload, egress outside allowlist | yes |
| COST-001..004 | COST | `gen_ai.usage.*`, `haiec.usage.baseline_tokens`, `haiec.retry_count` | >3× baseline spike; retry ≥5 & >3×; undeclared surface; loop+cycle | yes |
| AGENT-AUTH-001..003 | AGENT_AUTH | `haiec.delegation.*` | observed actor/scope outside declared chain; tool actor outside chains | yes |

## Known findings vs live detector coverage

| KNOWN FINDING | MATCHES LIVE DETECTOR? | WHY |
|---|---|---|
| C16 breach 106,829 > 60,000 | NO | COST-001 requires a caller-supplied `haiec.usage.baseline_tokens` AND >3× multiplier; real ratio was 1.78×. C16 is a frozen-control verdict, not a detector anomaly |
| S2 false certainty | NO | claim-vs-disposition divergence is LogSense/assurance semantics; no detector family reads it |
| C7 missing NEGOTIATION | NO | detectors evaluate present records; absence-of-event-type is not a telemetry anomaly |
| Token-ceiling enforcement anomaly (SEC-02) | NO | platform enforcement property, not a span-level signal |
| Runaway / MalformedToolCall loop | NO | COST-003 needs A→B→A handoff cycle + >3× spike; real run had neither handoffs nor >3× |
| Policy-blocked tool call | NO (correctly) | denied tools were in the declared registry; policy DENY is enforcement working, not an anomaly |
| Plaintext shared credential | N/A on spans | exposure was found in spec/config artifacts; EXFIL-* only scans span output/payload text |
| Scanner exposure / config drift | NO | infrastructure findings, outside telemetry rule families |

## Verdict

`DETECTOR_COVERAGE_COMPLETE_FOR_KNOWN_FINDINGS = NO` — by design. The live sweep
covers telemetry anomaly classes; the assurance findings came from LogSense
reconstruction, frozen Control Tests, authority investigation, and organizer grading.
`ZERO_DETECTION_FINDINGS != ZERO_PROBLEMS` — preserved as a permanent claim boundary.
