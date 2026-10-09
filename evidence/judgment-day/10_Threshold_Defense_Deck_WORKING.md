# Judge Deck — Threshold Slides (main + appendix)

> Main message: **Thresholds are evidence-informed governance decisions frozen
> before assessment. Determinism governs evaluation; policy versioning
> preserves historical truth.**

Every section is labeled as exactly one of:
**OBSERVED HEALTHY DISTRIBUTION** (calibration data) ·
**FROZEN GOVERNING POLICY** (what the event was scored under) ·
**PROSPECTIVE POLICY REVIEW** (future recommendations only — never applied
to the runs already assessed).

## MAIN SLIDE — "Frozen Thresholds — Evidence-Informed, Deterministic Evaluation"

| | C7 — AIA-LOG-001 | C9 — AIA-ARC-006 | C16 — ACN-COST-001 |
|---|---|---|---|
| LIMIT | 10 required events, 100% coverage | duration vs per-agent baseline, D=100% | 60,000 qualified tokens/run |
| TOLERANCE | gap < 30,000ms; B7 = 10% declared in frozen policy | B9 = 0% violating windows | zero over-cap runs (LTE) |
| MEASUREMENT BASIS | audit-store write cadence (seq) | CloudWatch AgentCore duration, MEAN per agent-window | gateway-attested in+out tokens, CALL_ID=runId+span.id |
| OWNER | Subodh KC | subodh-kc (participant, org owner) | Subodh KC |
| FROZEN BEFORE ASSESSMENT | YES — 01:28:01.997Z | YES — 06:51:04.002Z | YES — 01:28:02.294Z |
| POLICY_DIGEST | sha256:45f1abaf…e311 | sha256:8abea393…bab1 | sha256:944212e6…bfe5 |

One line per control for the judge:
- C7 fails on coverage arithmetic, not interpretation: 9/10 = 90% < 100%.
- C9's 2x ceiling is the smallest tested bound rejecting zero of 37 healthy windows.
- C16's cap arithmetic: 35,559 ≤ 60,000 PASS; 106,829 > 60,000 BREACH.

---

## APPENDIX — C9 MATH

Normalized degradation (per qualified window, no raw-ms pooling across agents):

```
relativeDegradation = (observed - agentBaseline) / agentBaseline x 100
```

Absolute ceilings (frozen D=100%):

| Agent | Baseline | Limit |
|---|---|---|
| customer | 6,781 ms | `6781 x (1+1.00) = 13,562` |
| IT | 8,917 ms | `8917 x 2 = 17,834` |
| network | 12,141 ms | `12141 x 2 = 24,282` |

Healthy calibration distribution (N=37 normalized windows): MIN -71.9 · MAX +86.3 ·
MEAN 0.0 (baselines are this population's per-agent means) · MEDIAN -8.2 ·
STDDEV 39.1 · MAD 24.5 · IQR 57.3 · P90 +49.7 · P95 +63.3.
Worst healthy window +86.3% → margin to D=100% = +13.7pt.

Sensitivity:

| D | ceilings (cust/it/net) | healthy windows violating | healthy rejected? |
|---|---|---|---|
| 25% | 8,476 / 11,146 / 15,176 | 12/37 (32%) | YES — chronic false positives |
| 50% | 10,172 / 13,376 / 18,212 | 3/37 (8%) | YES |
| 75% | 11,867 / 15,605 / 21,247 | 1/37 (3%) | YES |
| **100% — FROZEN EVENT POLICY** | **13,562 / 17,834 / 24,282** | **0/37 (0%)** | **NO** |

Why 100%: ED-022 records it as ~2x headroom over worst normal (+49% run-mean
basis; +86.3% window basis) and far below the observed fault range (+300%–+3600%).
It is empirically the smallest tested bound covering all healthy windows — not
claimed statistically optimal.

> The event policy uses a conservative 2x baseline degradation ceiling. The
> evaluator is deterministic; the threshold itself is a frozen governance choice
> informed by limited calibration evidence. A production policy would normally be
> tightened using a larger stable baseline period.

## APPENDIX — C7 MATH

```
coverage = 9 observed / 10 required = 90% ; required = 100% → NOT_SATISFIED
```

Missing NEGOTIATION@network-resolution-agent alone determines the verdict; gap
timing cannot rescue coverage. Timing source = audit-store record-write cadence
(seq, epoch ms) — not original action latency; no cross-source action latency is
claimed.

Healthy write-cadence population (504 consecutive gaps): median 451.5ms ·
P95 3,621ms · MAX 67,682ms. The 30,000ms limit sits ~9.8x above healthy P95;
rare boundary writes exceed it (~1.6%) — precisely what the frozen policy's
declared `allowedGapViolationRatePercent = 10` (B7) tolerates. The organizer
manifest itself declares only C, G and `LT` and carries no B7 field; the frozen
policy declares B7=10% (and stores comparator LTE — a minor recorded LT/LTE
inconsistency). No post-hoc allowance was applied beyond the frozen policy.

> B7 exception allowance was not declared in the organizer-supplied manifest;
> it is declared in the frozen HAIEC policy at 10%. No post-hoc timing
> exception allowance has been applied. Coverage failure stands regardless.

## APPENDIX — C16 MATH

```
PASS:   35,559 <= 60,000  (headroom 24,441; utilization 59.3%; 8 calls;
        gateway corroboration 34,917 in + 642 out = 35,559)
BREACH: 106,829 > 60,000  (overshoot 46,829 = 78.0% above cap; 17 calls)
```

Selection evidence: 3 qualified healthy runs captured before the 01:28Z freeze
measure ~40,167 / ~40,681 / ~49,969 tokens (max healthy ≈ 49,969 →
60,000 ≈ max × 1.20 reserve). The policy notes record cap semantics but no
numeric derivation — classified ENGINEERING_BOUND with
INSUFFICIENT_PRE_FREEZE_RATIONALE honestly preserved.

Distinct from the platform `modaas-ceiling` guardrail (2,500,000 tokens/hour,
one gateway replica, post-completion charging): SEC-02's enforcement anomaly is
a platform finding; C16's per-run cap is a separate HAIEC measurement.

## APPENDIX — THRESHOLD GOVERNANCE

```
CALIBRATE → HUMAN SELECT → FREEZE/VERSION → ASSESS → PRESERVE FAILURES → RETEST UNDER SAME RULE
```

> Deterministic assurance removes discretion from how the threshold is
> evaluated; it does not remove the need for a threshold when the control
> itself is quantitative.

> Tolerance, where required, is explicit, frozen and policy-owned. Exact
> controls may use zero tolerance; variable operational metrics use a declared
> allowance.

## GOVERNANCE CALLOUT — calibration → freeze → assess → preserve → review

> Historical policy preserved; calibration review informed a prospective
> policy version.

| | v2 / v1 — what governed the observed event | prospective recommendation (detail: `PROSPECTIVE_POLICY_REVIEW.md`) |
|---|---|---|
| C9 | D=100, B9=0, baselines 6,781/8,917/12,141 (frozen 06:51:04Z) | retain values; BaselineVersion v2 = same MEAN method on larger stable baseline; D=95 becomes defensible only with deeper healthy population |
| C7 | coverage 100%, G=30,000ms, B7=10% (policy-declared; manifest-absent), 9/10 NOT_SATISFIED stands | keep C/G/B7 values; future version declares B7 in manifest AND policy, unifies comparator |
| C16 | cap 60,000 LTE, over-cap 0 (frozen 01:28:02Z); 35,559 PASS / 106,829 BREACH stand | keep 60,000 — = healthy-max ×1.20; derivation now recorded; v2 adds retry-completeness requirement |

The event results above are the headline. Prospective versions are NOT
scored results — they are the review step of the lifecycle:

`CALIBRATE → FREEZE → ASSESS → PRESERVE → REVIEW → NEW VERSION PROSPECTIVELY`

## APPENDIX — ORGANIZER-NATIVE KILL SWITCH

`ORGANIZER_NATIVE_CAPABILITY_WITHDRAWAL` — the organizer guide's own "The kill
switch" procedure, executed live. NOT HAIEC kill-switch enforcement.

- `spec.paused=true` on `nemotron-nano-9b` (model behind `it-resolution-agent`)
- Paused ask (cid `killswitch-1791200427`): **disposition=refused, http_status=404**
- Required refusal evidence chain established — INTENT → INVOCATION(404) →
  RESULT-INSPECTION(refused) — **with two additional model-request records**
  (MODEL-REQUEST-INTENT, MODEL-REQUEST-RESULT/404): 5 records total
- Recovery: `paused=false`, `AgentgatewayRouteProgrammed=True`; post-recovery
  request returned an agent response (disposition `undetermined`) —
  **route and functional service restored** (not claimed as a control pass)
- `FORMALLY_SCORED = NOT_ESTABLISHED` (no organizer scoring material for this exercise)

## APPENDIX — Security Findings — Framework Crosswalk

Canonical crosswalk: `TMF_FRAMEWORK_CROSSWALK.md` (same folder).
Zero event findings carry canonical OWASP ASI IDs — no assessed security
finding was produced by a canonical detection rule, and manual assignment is
prohibited by contract. RELATED AR-family references (AR-28→ASI08,
AR-29→ASI03) are orientation only. MAPPING ≠ effectiveness ≠ compliance.
