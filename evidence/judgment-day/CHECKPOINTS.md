# PHASE CHECKPOINT LOG — Event-Day Working Pass
# Each phase is checkpointed to disk before the next begins. Recoverable.

## PHASE 0 — CREDENTIAL HYGIENE — CLOSED 2026-10-05 ~09:00Z
- Scan scope: entire `handover/` tree (assessed-bundles, calibration, package-dryrun-c16, sample, scripts).
- Patterns: HAIEC live keys, AWS access/secret/session keys, Bearer/session cookies, private keys, passwords, AUDIT_WRITE_TOKEN value, generic 32-hex assignment.
- Result: **ZERO secret values found in evidence/package/handover tree.**
- The `AUDIT_WRITE_TOKEN` label hits (162 files) are field-name/telemetry-ID collisions: the 32-hex pattern matched native `client_request_id`/`model_turn_id`/trace identities — NOT the actual token value. Exact-value check for the live audit token: **0 files**.
- Runtime secrets persist OUTSIDE the evidence/package tree only: `C:\tmp\otlp-token.txt` (evidence:ingest, 70 chars, required by `live_forwarder.py`) and `C:\tmp\owner-session.txt` (owner session). Referenced by name/purpose only. Not rotated (forwarder dependency).
- Handoff credential document lives in `docs/handoff/TM FORUM/...` (repo path) — contents NOT propagated into any new artifact.
- Log entry: `CREDENTIAL_HYGIENE_CHECK` recorded in `event-decision-finding-log.md`.

## PHASE 1 — TOKEN CEILING DEPLOYED SEMANTICS — CLOSED 2026-10-05 ~09:15Z
- Deployed proxy image: `cr.agentgateway.dev/agentgateway:v1.4.1` (modaas-agw deployment, agentgateway-system).
- Replicas: **1** (per-proxy multiplication does not apply).
- CRD: `AgentgatewayPolicy/v1alpha1` — installed `kubectl explain` semantics:
  - `local[].tokens` = **"Number of LLM tokens per unit of time ... Both input and output tokens are counted. However, token counts are not known until the request completes. As a result, token-based rate limits will apply to future requests only."**
  - `local[].requests` = HTTP requests per unit → 429.
  - `burst` = request allowance above request-per-unit. `unit` enum Hours/Minutes/Seconds.
  - local limits are per-proxy, no cross-instance coordination.
- Live `modaas-ceiling`: targetRef=Gateway modaas-agw, sectionName=`llm`, entries `requests:100/Minutes`, `tokens:2500000/Hours`. Accepted=True Attached=True.
- Gateway logs (24h covering the runaway window): `gen_ai.usage.input_tokens`/`output_tokens` ARE populated on llm-listener request records (usage extraction works); **zero `http.status=429` ever**; no ratelimit warn/error lines.
- OBSERVED (unchanged facts): 91 LLM calls, 2,823,563 in + 4,680 out = 2,828,243 tokens, all HTTP 200, no token-based 429; terminal 403 = Cedar MalformedToolCall.
- FINAL CLASSIFICATION: **TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY**.
- Prior `MEASUREMENT_BASIS_DIFFERS` (request-count semantics): **RETRACTED** — that description belonged to a different config surface/version; deployed v1.4.1 + v1alpha1 CRD confirms LLM-token semantics.
- Residual unexplained: post-completion charging should have emptied the 2.5M bucket mid-run (~call 85-90); no deny observed. Hypotheses not provable read-only: v1.4.1 post-response charging defect on aws.bedrock provider path; limiter not fed usage on this route; bucket key/init semantics. No stress test performed (per instruction).
- Evidence: this file + `calibration/` gateway captures + `evidence/judgment-day/` snapshot.

## PHASE 2 — C7 NEGOTIATION ROOT CAUSE — CLOSED 2026-10-05 ~09:20Z
- `invoke_agent Strands Agents` spans = Strands framework agent-invocation lifecycle, NOT a cross-agent call (present in every agent run, incl. runaway trace d6372431).
- Network agent registered tool list (runtime telemetry `gen_ai.agent.tools`): aws-knowledge x4, cluster-status, cr-author x2, customer-records, evidence-lookup, helper-docs, network-twin, runbook-lookup. **No peer-agent/invoke_agent tool exists.**
- ToolConfig providers = `agentCoreGateway` | `custom` only — **no A2A/agent provider type** in platform.
- `CAN_MODIFY_AGENT_WITHOUT_UNINTENDED_IMAGE_RECONCILIATION = NO` — any AgentConfig edit reconciles pending unapproved spec image digest `04b512e0…` (desired-state ahead of reconciled runtime `2f6e4556…`).
- Outcome: change design only, no mutation, no retest. Historical 9/10 preserved.

## PHASE 3 — C9 HISTORICAL CALIBRATION — CLOSED 2026-10-05 ~09:30Z
> **HISTORICAL / SUPERSEDED BY FROZEN C9 v2** — the UNFROZEN/UNASSESSED state described in this phase predates the freeze. CURRENT STATE: policy `346b5f43-58eb-44f8-a74e-45cfde746d74` (`c9-duration-thresholds-v2`) FROZEN; two assessed SATISFIED results exist (`fault-1791183079-256a5e`, `fault-1791183213-228329`); assessment-eligible breach NOT_ESTABLISHED.
- Data: `calibration/c9_metric_calibration.json` (saved in handover root during this pass).
- Duration: runaway window shows network agent max 298,485ms vs baseline ~3.4–13s — anomaly IS detectable; IT agent elevated to 13,067ms. Baseline windows (breach, s3): customer ~2.4–9.4s, IT ~3.0–13.0s, network ~3.4–22.6s.
- Granularity: 1-min aggregation; ~1 invocation/min — sparse per-run, defensible only as multi-window baseline.
- UserErrors/Throttles: 0 in every window — not sensitive indicators.
- TargetExecutionTime: per-tool InvokeGateway metric exists; sparse.
- Verdict: Duration = viable baseline CANDIDATE using ≥3 historical windows; C9 remains UNFROZEN/UNASSESSED — no verdict issued.

## PHASE 4 — ARTIFACT MIRROR + EVENT LOG + PACKAGE — CLOSED 2026-10-05 ~09:45Z
- Created `handover/judgment-day-current/` six working mirrors + README.
- Created `handover/event-decision-finding-log.md` (append-only).
- Created `handover/VM_SYNC_PLAN.md`.
- Snapshot added to `package-dryrun-c16/evidence/judgment-day/`; MANIFEST.sha256 + PACKAGE-DIGEST.txt recomputed (previous digest preserved in file header + log).
- Secret re-scan post-write: 0 secret-value hits.

## PHASE 5 — LIVE TELEMETRY REVALIDATION — CLOSED 2026-10-05 ~09:50Z
- Binder 52ec5f04-c01a-4715-ae46-6bef3260b505 remains bound to assessed system 4043efee.
- Prior evidenceRefs persistence verified; no new connectivity test needed (records already persisted/recognized server-side).
- LIVE_HAIEC_TELEMETRY = PROVEN (unchanged).
