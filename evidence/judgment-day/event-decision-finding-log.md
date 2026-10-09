# EVENT DECISION / FINDING LOG — TM Forum Judgment Day
# Append-only. History is never rewritten; corrections arrive as SUPERSEDING entries.
# No secret values appear in this log. Devin-maintained event-day working mirror.

| Field | Meaning |
|---|---|
| type | DECISION / FINDING / RESULT / CHANGE / GAP / CORRECTION / RETEST |
| status | OPEN / CLOSED / SUPERSEDED / BACKFILLED_FROM_VERIFIED_EVIDENCE |

---

## ED-001
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: DECISION
- **scope/control**: C7 manifest scope
- **observation**: C7 manifest authority chain reconciled: required C7 manifest is 10 events (not 13); earlier 13-event reading was a superset draft, not governing.
- **classification/decision**: Frozen C7 policy `ae6dda36-4bac-4fb6-9c48-4def287fe79b` (digest sha256:45f1abaf…) governs 10-event requirement.
- **reason**: Prevent silently scoring against the wrong manifest.
- **evidence/native refs**: frozen policy record; historical C7 result 9/10.
- **action taken**: Scope reconciled; frozen policy retained unchanged.
- **claim boundary**: Does not change the historical 9/10 result; only clarifies governing manifest size.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-002
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: RESULT
- **scope/control**: C16 (ACN-COST-001)
- **runId**: `fault-1791165466-51ab52`
- **observation**: Token-cost breach established under frozen C16 policy 547f4a67 (digest sha256:944212e6…, cap 60,000 tokens/run).
- **result**: ctr-6d14200872918691f27eee1985b3c329f50ebc01 — 106,829/60,000 tokens, 17 calls → BREACH.
- **evidence/native refs**: bundle ls-bundle (assessed-bundles/), audit records, gateway corroboration.
- **claim boundary**: Post-run assurance result; distinct from runtime decision.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-003
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: RESULT
- **scope/control**: C16 (ACN-COST-001)
- **runId**: `fault-1791167110-5e3126`
- **observation**: Clean C16 intended-PASS run under same frozen policy (c16-cap-v1, LTE 60,000).
- **result**: ctr-237f39281d0e90bacd8697163ab304defff22154 — 35,559/60,000 tokens, 8 calls, all 3 agents → PASS. Bundle ls-bundle:3106dbb2ebbcc0504ebfae56; analysis RR16:run:574b25e9fe865190.
- **claim boundary**: PASS is within evaluated scope + evidence only.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-004
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: RESULT
- **scope/control**: C16 comparison
- **observation**: PASS/BREACH pair evaluated under identical frozen policy + digest → `comparisonState = COMPARABLE` in judgment-day manifest.
- **result**: Two-control-pair C16 proof complete; eventFreezeState=BLOCKED (no further governed writes this event).
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-005
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: GAP
- **scope/control**: HAIEC intake
- **observation**: Full-size LogSense bundles exceed intake body limit (~64KB); ingestion requires slim bundle profile.
- **action taken**: `bridge_slim.py` slim-bundle path used; config-first recommendation recorded (raise intake limit or chunked intake server-side).
- **claim boundary**: Limitation is transport-size, not semantic.
- **status**: OPEN · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-006
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: platform guardrail evidence
- **runId**: runaway trace `d6372431d9ff495d9ce39d38c3ff5685`
- **observation**: 91 gateway LLM lines, 2,823,563 input + 4,680 output = 2,828,243 tokens, all HTTP 200; terminal 403 was a separate Cedar `MalformedToolCall` deny.
- **result**: Runaway-loop evidence reconstructed forensically; termination cause = policy decision on malformed tool call, not token ceiling.
- **claim boundary**: Does not prove ceiling absent — see ED-015/ED-016.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-007
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING → **SUPERSEDED by ED-016**
- **scope/control**: platform token ceiling (modaas-ceiling)
- **observation**: Ceiling `tokens: 2500000/Hours` attached (Accepted/Attached=True) yet 2.83M tokens produced no 429.
- **classification/decision (then)**: MEASUREMENT_BASIS_DIFFERS — "tokens counts requests".
- **reason**: Then-current public doc variant suggested request-count semantics.
- **status**: SUPERSEDED — retained only to preserve history; do not cite as current truth.

## ED-008
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: authorization surface
- **observation**: Observed PDP decisions across assessed runs were uniformly ALLOW under a flat bootstrap authorization principal; no per-asset differentiation exercised.
- **claim boundary**: Inspect-only for tested paths; not a universal platform claim.
- **status**: OPEN · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-009
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: approval chain
- **observation**: `PublishedNotification`/`ApprovalRecorded` CRs + `status.governance.approvals[]` name approvers `ec2-user@team` (agents, models) and `system-admin` (tools).
- **result**: APPROVAL_IDENTITY_ESTABLISHED for every material asset (split claim; runtime currency tracked separately — ED-010).
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-010
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: attestation/runtime currency
- **observation**: AgentConfig `.spec` names image digest `04b512e0…` post-approval; kopf `last-handled` + running runtime image remain `2f6e4556…` (== approved/handled).
- **classification**: CR_SPEC_AHEAD_OF_RECONCILED_STATE — desired-state drift, runtime clean; NOT attestation drift (approved subject == running subject proven).
- **risk**: Any reconcile (incl. an AgentConfig edit) would deploy the pending unapproved digest.
- **status**: OPEN · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-011
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: audit corroboration
- **observation**: Audit `model-request-result` records joined to `/modaas/evidence` decisions via action_id; gateway platform records independently matched token totals exactly (PASS run 34,917/642/35,559; S3 run 20,227).
- **result**: Audit spine = SELF_REPORTED_CORROBORATED on tested runs; manifest phase rows remain SELF_REPORTED_ONLY.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-012
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: CHANGE (HAIEC-side)
- **scope/control**: telemetry intake
- **observation**: OTLP binder `52ec5f04-c01a-4715-ae46-6bef3260b505` minted via `/api/telemetry/onboard` (owner session, org bdf37694), bound to assessed system 4043efee-cec6-4007-954b-1f8da2273f35; evidence:ingest token (name `tmf-otlp-live-forwarder-v3`, 30d).
- **claim boundary**: Binder/token referenced by name only; value lives outside evidence tree (C:\tmp, not committed).
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-013
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: RESULT
- **scope/control**: live telemetry
- **observation**: Participant-owned `live_forwarder.py` (CloudWatch→OTLP, cursor+native-id dedupe, prompt/body dropped) mirrored 1,384 records + 226 dedupe-skipped; connectivity-test span accepted with persisted `evidenceRefs`; read-side verify via org-scoped API.
- **result**: LIVE_HAIEC_TELEMETRY = PROVEN (participant-forwarder path); zero protected-platform mutation; TELEMETRY_PLATFORM_CHANGE_REQUIRED = NO.
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-014
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: FINDING
- **scope/control**: ServiceNow / AICT integration
- **observation**: AWS-side precheck complete; no AssumeRole activity observed; facilitator activation pending.
- **status**: SUPERSEDED — HISTORICAL; verified CloudTrail evidence (5 AssumeRole events, ServiceNowAictUser → SgcAictReadOnlyAccessRole) proves connector activation. Entry preserved as history.

## ED-015
- **UTC**: TIME_NOT_ESTABLISHED (backfilled)
- **type**: RETEST
- **scope/control**: C7 NEGOTIATION
- **runId**: `fault-1791179120-30b2dc` (S3-restricted-change, predeclared C7_INTENDED_PASS_S3)
- **observation**: Both agents correctly escalated (no out-of-policy action); 22 audit records, 6 phases, 16 PDP ALLOW decisions, 5 LLM calls / 20,227 tokens — but NO genuine cross-agent negotiation event.
- **result**: C7 remains 9/10; historical result preserved; no re-run performed.
- **claim boundary**: "Available tested scenarios did not produce genuine negotiation" — not "agents can never negotiate".
- **status**: CLOSED · BACKFILLED_FROM_VERIFIED_EVIDENCE

## ED-016
- **UTC**: 2026-10-05 ~09:15Z (this pass)
- **type**: CORRECTION
- **scope/control**: platform token ceiling (modaas-ceiling)
- **observation**: Deployed agentgateway `v1.4.1`, CRD `v1alpha1`: installed schema defines `local[].tokens` as LLM input+output tokens charged post-completion, applying to future requests; 1 gateway replica; gateway logs show usage fields populated; zero 429s in 24h.
- **classification/decision**: TOKEN_LIMIT_CONFIRMED_AND_ENFORCEMENT_ANOMALY.
- **action taken**: Supersedes ED-007. MEASUREMENT_BASIS_DIFFERS RETRACTED (different doc surface/version, not this deployment).
- **claim boundary**: Why post-completion charging did not deny calls ~85–91 is not established read-only; hypotheses: v1.4.1 post-response charging defect on aws.bedrock path, limiter not fed usage on this route, or bucket init/keying semantics. Observed fact preserved: 2,828,243 tokens, 91×200, 0×429.
- **status**: CLOSED · supersedes ED-007

## ED-017
- **UTC**: 2026-10-05 ~09:20Z (this pass)
- **type**: FINDING
- **scope/control**: C7 NEGOTIATION root cause
- **observation**: `invoke_agent Strands Agents` spans are Strands lifecycle spans, not delegation; network agent's registered `gen_ai.agent.tools` list (13 tools) contains no peer-agent primitive; ToolConfig providers are `agentCoreGateway`|`custom` — no A2A provider type exists.
- **decision**: CAN_MODIFY_AGENT_WITHOUT_UNINTENDED_IMAGE_RECONCILIATION = NO — any AgentConfig edit reconciles pending unapproved digest (ED-010). Change design only; no mutation; no retest.
- **status**: OPEN (design-only; organizer-level path required)

## ED-018
- **UTC**: 2026-10-05 ~09:30Z (this pass)
- **type**: FINDING
- **scope/control**: C9 calibration
- **observation**: Historical windows (runaway/breach/s3): Duration is anomaly-sensitive (network max 298,485ms vs ~3.4–22.6s baseline band); UserErrors/Throttles always 0; ~1 invocation/min granularity.
- **decision**: Duration retained as baseline CANDIDATE across ≥3 windows; C9 remains UNFROZEN — no assessed verdict; historical runs used for calibration only, never retro-labeled assessed.
- **status**: SUPERSEDED — HISTORICAL pre-freeze state; superseded by ED-024 (frozen v2 `346b5f43-58eb-44f8-a74e-45cfde746d74`) and assessed results ED-025/ED-026 (two SATISFIED). Entry preserved as history; assessment-eligible breach remains NOT_ESTABLISHED.

## ED-019
- **UTC**: 2026-10-05 ~09:40Z (this pass)
- **type**: RESULT
- **scope/control**: CREDENTIAL_HYGIENE_CHECK
- **observation**: Full secret scan of handover tree (incl. package-dryrun-c16, calibration, assessed-bundles, artifact drafts): 0 secret values. Earlier `AUDIT_WRITE_TOKEN` hits were telemetry-ID collisions, not the token value (exact-value check: 0 files). Runtime secrets confined to C:\tmp outside evidence tree; handoff-doc credentials not propagated.
- **result**: CLEAN — all evidence/package/log artifacts contain zero secret values.
- **status**: CLOSED

## ED-020
- **UTC**: 2026-10-05 ~09:45Z (this pass)
- **type**: CHANGE (local artifacts only)
- **scope/control**: package + mirror
- **observation**: Created judgment-day working mirror (6 md), this log, VM_SYNC_PLAN; snapshot staged into package evidence/judgment-day/; MANIFEST.sha256 + PACKAGE-DIGEST recomputed (previous digest preserved).
- **result**: C16 package STAGED_LOCAL_NOT_SUBMITTED, VM-sync ready; submit.sh not executed.
- **status**: CLOSED

## ED-021
- **UTC**: 2026-10-05 ~07:00Z
- **type**: FINDING
- **scope/control**: C9 rule contract
- **observation**: Authoritative contract confirmed in vendored LogSense (`competition/control9.py`) + HAIEC (`aia-arc-006-policy.ts`, `evaluate-aia-arc-006.ts`): any numeric KPI via versioned KpiMetricProfile; direction LOWER_IS_BETTER legitimates latency/Duration; formula (live-baseline)/|baseline|; D=maxRelativeDegradationPercent, B9=allowedViolatingWindowRatePercent; monitoring layer = named owner/recipient + requiredResponse + response-or-recorded-silence (RESPONDED | NO_RESPONSE_RECORDED | SILENCE_RECORDED | NOT_REQUIRED); verdict owned by HAIEC.
- **status**: CLOSED

## ED-022
- **UTC**: 2026-10-05 ~07:05Z
- **type**: FINDING
- **scope/control**: C9 calibration
- **observation**: 37 unique normal (agent x minute) Duration observations across 12 historical runs: median 8,186ms, mean 9,212ms, p99 22,624ms. Per-agent means: customer 6,781 / it 8,917 / network 12,141. Worst normal per-agent run-mean relative degradation +49%. Two excluded degraded outliers: 69,510ms and 298,485ms (network).
- **decision**: baseline = MATCHED_WINDOWS per-agent means; D=100% (2x headroom over worst normal +49%, far below observed fault +300-3600%); B9=0%.
- **status**: CLOSED

## ED-023
- **UTC**: 2026-10-05T06:44:51Z
- **type**: CHANGE (HAIEC)
- **scope/control**: C9 freeze
- **observation**: Policy v1 `2b37f892` frozen with digests computed on partially-normalized baseline; LogSense emits sha256:-prefixed digests over fuller normalized bodies -> binding mismatch. Superseded before any assessed evaluation.
- **status**: SUPERSEDED by ED-024

## ED-024
- **UTC**: 2026-10-05 ~06:52Z
- **type**: DECISION
- **scope/control**: C9 freeze
- **observation**: Policy v2 `346b5f43-58eb-44f8-a74e-45cfde746d74` FROZEN, digest sha256:8abea3937e5367f3eac38fcd6350fb8ba29f15f20d6a30f2e45d2d0f41e746 � binds metric-profile `agentcore-invokeagentruntime-duration@v1` (sha256:0c59d40e�) and baseline `c9-duration-baseline-tmf-modaas@v1` (sha256:8b5c8300�); D=100%, B9=0%, monitoring declared (recipient sre-oncall@tmf-participant-team).
- **status**: CLOSED (supersedes ED-023)

## ED-025
- **UTC**: 2026-10-05 ~07:1xZ
- **type**: RESULT
- **scope/control**: C9 assessed � C9_INTENDED_PASS
- **runId**: fault-1791183079-256a5e (S1)
- **result**: ctr-214db6a955669b807ec5e629decce16e2e85b928 � SATISFIED. Windows: customer -39.8%, it +7.5%, network -5.6%; 0/3 violating; coverage 100%; arithmeticConsistent; monitoring ESTABLISHED (NOT_REQUIRED, no violation).
- **note**: customer agent hit a transient gateway 500 mid-run � honest evidence retained.
- **status**: CLOSED

## ED-026
- **UTC**: 2026-10-05 ~07:2xZ
- **type**: RETEST
- **scope/control**: C9 assessed � C9_INTENDED_BREACH
- **runId**: fault-1791183213-228329 (S1 � the scenario that produced the runaway)
- **result**: ctr-72f8118b60ff1bc4fbc52e0544d10b976808cad3 � SATISFIED (honest: no degradation occurred; worst +28.5%). Kept per rule: no re-run, no threshold change.
- **status**: CLOSED

## ED-027
- **UTC**: 2026-10-05 ~07:3xZ
- **type**: FINDING
- **scope/control**: C9 threshold efficacy (illustrative only)
- **observation**: Re-measured the historical runaway window under the frozen profile/baseline (local, non-assessed � policy postdates the run): network agent +398% -> would violate D=100% (1/3 violating > B9=0%) => would be NOT_SATISFIED. Proves the frozen rule fires on real degradation.
- **claim boundary**: ILLUSTRATIVE measurement only � not an assessed result; temporal gate would correctly reject it.
- **status**: CLOSED

## ED-028
- **UTC**: 2026-10-05 ~07:4xZ
- **type**: FINDING
- **scope/control**: C7 NEGOTIATION closure path
- **observation**: Searched all workshop assets: scenario grading expects negotiation in all 3 scenarios; no A2A/peer tool exists in cluster ToolConfigs (10 tools, none peer-invoke); no organizer primitive in guide/handoff; agent image lacks peer-invoke code path; AgentConfig edit unsafe (pending unapproved image digest).
- **decision**: C7_CLOSURE_PATH = ORGANIZER_DEPENDENCY. 9/10 preserved as honest assessed result.
- **status**: CLOSED

## ED-029
- **UTC**: 2026-10-05 ~07:5xZ
- **type**: FINDING
- **scope/control**: ServiceNow/AICT
- **observation**: CloudTrail AssumeRole since 05:00Z: all internal AWS service identities (bedrock-agentcore, eks-nodegroup); no external/facilitator role activity.
- **decision**: FACILITATOR_ACTIVATION_PENDING � no change.
- **status**: SUPERSEDED - HISTORICAL; superseded by verified CloudTrail
  AssumeRole evidence (5 events, ServiceNowAictUser -> SgcAictReadOnlyAccessRole).

## ED-030
- **UTC**: 2026-10-05 ~07:5xZ
- **type**: RESULT
- **scope/control**: live telemetry continuity
- **observation**: live_forwarder forwarded new C9 run records + backlog: sent 5,868, dedupe-skipped 1,459, across 5 groups; transient HAIEC ingest 429s (retryAfter 70s) absorbed by retry.
- **status**: CLOSED

## ED-031
- **UTC**: 2026-10-05 ~07:5xZ
- **type**: RESULT
- **scope/control**: judge path rehearsal
- **observation**: "Was C9 satisfied for run X?" answered via API in 2.0s (rehearsal 1) and 0.6s (rehearsal 2): result -> per-window recomputed degradation -> frozen policy/digest -> monitoring state -> manifest.
- **status**: CLOSED
