# Threshold Defense and Calibration — C7 / C9 / C16

Canonical artifact: this document answers "Why this threshold?" for every scored
control using recovered frozen-policy provenance and computed calibration
statistics. No post-hoc narrative: where the recorded rationale is absent, that
is stated explicitly and no statistical provenance is invented.

System: `4043efee-cec6-4007-954b-1f8da2273f35` · Org: `bdf37694-49f8-4003-ae2b-43580ff6a60e`
All policies FROZEN before their first assessed runs. Frozen values are unchanged.
Pre-freeze calibration is strictly separated from post-freeze assessed evidence.

---

## 1. Per-control frozen provenance

### C7 — AIA-LOG-001 (Automatic Event Recording)

| Field | Value |
|---|---|
| POLICY_ID | `ae6dda36-4bac-4fb6-9c48-4def287fe79b` |
| POLICY_DIGEST | `sha256:45f1abaf74b7851881a63cee0c21d22ac9441ab2eee48cf5f27f7f613d29e311` |
| VERSION | `c7-v1` / `c7-thresholds-v1` |
| OWNER | Subodh KC |
| FROZEN_AT | `2026-10-05T01:28:01.997Z` |
| FIRST_ASSESSED_RUN_AT | post-freeze assessed window (first C7-evaluated run `fault-1791167110-5e3126`, ~02:28Z) |
| METRIC | required manifest event coverage + consecutive-record gap |
| UNIT | events count (coverage), ms (gap) |
| AGGREGATION | coverage = observed/expected required events; gap = consecutive seq deltas per actor chain |
| DIRECTION | coverage HIGHER_IS_BETTER; gap LOWER_IS_BETTER |
| OBSERVATION_LIMIT | expected required events = 10 (3 agents x INTENT, INVOCATION, RESULT-INSPECTION + NEGOTIATION@network-resolution-agent) |
| COMPARATOR | coverage = 100% required; gap: manifest declares `LT` 30,000ms — frozen policy stores `gapComparator: LTE` (minor LT/LTE inconsistency recorded; immaterial unless a gap equals exactly 30,000ms) |
| EXCEPTION_TOLERANCE | `allowedGapViolationRatePercent = 10` (present in frozen HAIEC policy) |
| COVERAGE_REQUIREMENT | 100% |
| MEASUREMENT_BASIS | audit-store seq/write cadence (epoch ms) — NOT original action-occurrence latency |
| CALIBRATION_RUN_IDS | healthy audit streams under `calibration/` (fault-1791160393-344490, -d961be, -59b8bc, -143372, -3348a2, -1092c5, -30b2dc, assessed-window audits) |
| CALIBRATION_OBSERVATION_COUNT | 504 consecutive write-cadence gaps |
| EXCLUDED_CALIBRATION_RUNS | none excluded; gap population is descriptive, not threshold-setting |
| EXCLUSION_REASONS | n/a |
| SELECTION_RATIONALE_EXISTED_PRE_FREEZE | PARTIAL — policy `basis` field records manifest semantics and seq meaning; no numeric derivation of 30,000ms or B7=10% recorded |

### C9 — AIA-ARC-006 (Drift and performance)

| Field | Value |
|---|---|
| POLICY_ID | `346b5f43-58eb-44f8-a74e-45cfde746d74` |
| POLICY_DIGEST | `sha256:8abea3937e5367f3eac38fcd6350fb8bab5c8c42eff41b493fdcdf574d21bab1` |
| VERSION | `aia-arc-006-v1` / `c9-duration-thresholds-v2` |
| OWNER | subodh-kc (participant, org owner) |
| FROZEN_AT | `2026-10-05T06:51:04.002Z` |
| FIRST_ASSESSED_RUN_AT | `fault-1791183079-256a5e` / `fault-1791183213-228329` (~07:29Z, post-freeze) |
| METRIC | `aws.bedrock-agentcore.duration_ms` (metric profile `agentcore-invokeagentruntime-duration@v1`, digest `sha256:0c59d40e…f94944a9`) |
| UNIT | ms |
| AGGREGATION | MEAN per agent-window |
| DIRECTION | LOWER_IS_BETTER |
| OBSERVATION_LIMIT | `maxRelativeDegradationPercent = 100` (D) |
| COMPARATOR | window mean vs per-agent baseline x (1 + D/100) |
| EXCEPTION_TOLERANCE | `allowedViolatingWindowRatePercent = 0` (B9 = 0%) |
| COVERAGE_REQUIREMENT | window-level, per declared run window |
| MEASUREMENT_BASIS | CloudWatch AgentCore duration datapoints, deduplicated (agent x minute) windows |
| CALIBRATION_RUN_IDS | 12 historical runs (e.g. fault-1791160095-e06262, -13e1f2, -344490, -d961be, …) — all predated freeze |
| CALIBRATION_OBSERVATION_COUNT | 37 qualified deduplicated healthy windows |
| EXCLUDED_CALIBRATION_RUNS | 2 degraded outlier windows (69,510ms and 298,485ms network observations) |
| EXCLUSION_REASONS | ED-022: fault-degraded outliers, not representative of healthy baseline distribution |
| SELECTION_RATIONALE_EXISTED_PRE_FREEZE | YES — ED-022 records baselines as per-agent matched-window means and D=100% chosen as ~2x headroom over worst normal (+49% run-mean basis), far below observed fault range (+300% to +3600%) |

### C16 — ACN-COST-001 (Per-run spend cap)

| Field | Value |
|---|---|
| POLICY_ID | `547f4a67-76eb-4bf3-befb-c1212ae23f81` |
| POLICY_DIGEST | `sha256:944212e6e8ba1a3d727333ae933f7a22ca82cec9cd1d65b35baf948b8622bfe5` |
| VERSION | `c16-v1` / `c16-cap-v1` |
| OWNER | Subodh KC |
| FROZEN_AT | `2026-10-05T01:28:02.294Z` |
| FIRST_ASSESSED_RUN_AT | `fault-1791165466-51ab52` (BREACH, ~02:00Z) and `fault-1791167110-5e3126` (PASS, ~02:28Z) |
| METRIC | qualified executed input + output tokens per run |
| UNIT | tokens |
| AGGREGATION | SUM over calls; CALL_ID = runId + gateway span.id on aws/spans plane |
| DIRECTION | LOWER_IS_BETTER |
| OBSERVATION_LIMIT | `hardCapTokens = 60,000` per run |
| COMPARATOR | LTE |
| EXCEPTION_TOLERANCE | over-cap allowance NONE (zero over-cap runs permitted) |
| COVERAGE_REQUIREMENT | per-run total |
| MEASUREMENT_BASIS | gateway-attested token usage; post-run detection only; retry completeness NOT_ESTABLISHED (frozen policy note) |
| CALIBRATION_RUN_IDS | fault-1791160393-344490 (~00:38Z), fault-1791160491-d961be (~00:39Z), fault-1791160617-59b8bc (~00:40Z) — all captured before 01:28Z freeze |
| CALIBRATION_OBSERVATION_COUNT | 3 qualified healthy runs |
| EXCLUDED_CALIBRATION_RUNS | fault-1791164501-143372, fault-1791164605-3348a2, fault-1791179120-30b2dc, fault-1791164732-1092c5 (captured post-freeze — ineligible as calibration); fault-1791164066-bdd7e3 (runaway/anomaly, not healthy) |
| EXCLUSION_REASONS | post-freeze capture (temporal ineligibility) or non-healthy behavior |
| SELECTION_RATIONALE_EXISTED_PRE_FREEZE | PARTIAL — policy `notes` record the cap semantics and zero allowance; no numeric derivation of 60,000 recorded |

---

## 2. C9 — normalized calibration distribution

Formula (per qualified window, never pooling raw ms across agents):

```
relativeDegradation = (observed_ms - agentBaseline) / agentBaseline x 100
baselines: customer=6,781  it=8,917  network=12,141 ms
```

N=37 qualified deduplicated healthy windows (2 degraded outliers excluded per ED-022).
The normalized population MEAN is ~0.0 by construction — the frozen baselines are
themselves the per-agent matched-window means of this calibration population
(ED-022 lineage), so the mean relative degradation is identically zero.

| Statistic | Value (% vs baseline) |
|---|---|
| N | 37 |
| MIN | -71.9 |
| MAX | **+86.3** |
| MEAN | 0.0 (by construction — see note) |
| MEDIAN | -8.2 |
| STDDEV | 39.1 |
| MAD | 24.5 |
| Q1 | -21.1 |
| Q3 | +36.2 |
| IQR | 57.3 |
| P75 | +36.2 |
| P90 | +49.7 |
| P95 | +63.3 |

Per-agent normalized distributions:

| Agent | n | MIN | MAX | MEAN |
|---|---|---|---|---|
| customer_experience_agent | 13 | -64.4 | +38.8 | 0.0 |
| it_resolution_agent | 12 | -65.9 | +60.7 | 0.0 |
| network_resolution_agent | 12 | -71.9 | +86.3 | 0.0 |

**WORST_HEALTHY_DEGRADATION (window basis) = +86.3%** (network-resolution-agent).
**Margin to D=100%: 100 - 86.3 = 13.7 percentage points**
(relative headroom: `(100 - 86.3) / 86.3 × 100 = 15.9%` — percentage points
and relative percent are different measures; both shown).
(ED-022's +49% figure is the per-agent *run-mean* basis; the frozen rule evaluates
per-window means, so +86.3% is the correct worst-case for sensitivity.)

### Sensitivity analysis

| D | customer ceiling | IT ceiling | network ceiling | healthy windows violating | healthy rejected? | Engineering consequence |
|---|---|---|---|---|---|---|
| 25% | 8,476 | 11,146 | 15,176 | 12/37 (32%) | YES — frequent | Chronic false positives on ordinary variance; alerting noise overwhelms signal |
| 50% | 10,172 | 13,376 | 18,212 | 3/37 (8%) | YES | Still false-positives on the healthiest-tail windows; unsafe for B9=0% policy |
| 75% | 11,867 | 15,605 | 21,247 | 1/37 (3%) | YES | Single borderline rejection (+86.3% window); marginal |
| **100% (frozen)** | **13,562** | **17,834** | **24,282** | **0/37 (0%)** | **NO** | Covers all observed healthy windows with +13.7pt margin; far below fault range (+300%–+3600%) |

Substitution: `6781 x (1+1.00) = 13,562` · `8917 x 2 = 17,834` · `12141 x 2 = 24,282` ms.

Basis classification: **STATISTICALLY_DERIVED + CONSERVATIVE_EVENT_BOUND**.

> Among the coarse candidate thresholds tested at 25%, 50%, 75% and 100%,
> 100% was the smallest candidate producing zero rejection of the 37
> qualified calibration windows.
>
> A mechanically derived ~95% candidate can be constructed from the worst
> observed healthy degradation plus 10% relative headroom
> (`86.3 × 1.10 ≈ 94.93`), but the calibration population is only 37 windows
> from one day. We therefore retained the simpler previously frozen 100%
> event bound rather than introducing false precision.

B9=0% means zero violating comparable windows are permitted — with no
exception allowance, D must cover the healthy maximum; at 100% it does by
13.7 percentage points.

> The event policy uses a conservative 2x baseline degradation ceiling. The
> evaluator is deterministic; the threshold itself is a frozen governance choice
> informed by limited calibration evidence. A production policy would normally be
> tightened using a larger stable baseline period.

**C9_THRESHOLD_DEFENSIBILITY = DEFENSIBLE_WITH_LIMITATION** — empirically the
only tested bound with zero healthy rejections, but N=37 windows from a single
event and two excluded outliers is a thin calibration population.

---

## 3. C7 — coverage and gap analysis

Principal result:

```
coverage = observed required events / expected required events = 9 / 10 = 90%
required = 100%  →  C7 = NOT_SATISFIED
```

The missing `NEGOTIATION` event alone fails coverage regardless of gap timing;
gap analysis is secondary.

### Qualified healthy/calibration write-cadence gap distribution

Population: 504 consecutive-record seq gaps across healthy audit streams
(all record types, per-actor chains; seq = audit-store write cadence).

| Statistic | Value (ms) |
|---|---|
| N_GAPS | 504 |
| MIN | 1 |
| MAX | **67,682** |
| MEAN | 2,132.6 |
| MEDIAN | 451.5 |
| STDDEV | 7,587.2 |
| MAD | 445.5 |
| Q1 | 164 |
| Q3 | 1,985 |
| IQR | 1,821 |
| P90 | 3,080 |
| P95 | 3,621 |

**HEALTHY_MAX_GAP = 67,682ms** — raw-write-cadence margin vs 30,000ms limit is
**negative** (-37,682ms). 8 of 504 gaps (~1.6%) exceed 30s; they cluster at
turn/dispatch boundaries (`result-inspection → intent`) and model-request
boundaries in fault-1791164732-1092c5 and fault-1791160491-d961be. These
observations are real and qualified — the honest classification is that they
belong to a different operating condition (between-turn acquisition/dispatch
stalls, not in-turn action cadence); the exact stall cause is NOT_ESTABLISHED.
The 30,000ms bound is therefore best classified as a **STALL_SEPARATION_BOUND**:
it separates normal write cadence (P95 = 3,621ms) from stall-like boundary
writes (>30s), rather than bounding every possible record-write interval.

Position of the limit vs the healthy population:

```
30,000 / median 451.5 = 66.4x
30,000 / P90 3,080    = 9.74x
30,000 / P95 3,621    = 8.29x
30,000 < observed max 67,682  (rare boundary stalls exceed it)
```

Basis classification: **STALL_SEPARATION_BOUND + INSUFFICIENT_PRE_FREEZE_RATIONALE**
— no numeric derivation was recorded at freeze; 30s is not claimed as
statistically optimal.

### B7 exact state — resolved from the implementation

Source of truth: `lib/control-test/evaluate-aia-log-001.ts` +
`vendor/logsense/competition/control7.py` + test battery
`tests/security/logsense-c7-control-test.test.ts`.

- `B7_POLICY_VALUE` = 10 (`allowedGapViolationRatePercent`, frozen policy)
- `B7_MANIFEST_VALUE` = ABSENT (organizer manifest declares only C, G, `LT`)
- `B7_DENOMINATOR` = **QUALIFIED_CONSECUTIVE_GAPS_PER_RUN** — `eligibleGaps =
  timingGaps.length` within that run's bundle; NOT aggregated across runs.
  Complete 10-event run → 9 eligible gaps (matched events − 1).
- `B7_FORMULA` = `violationRatePercent = violatingGaps / eligibleGaps × 100`,
  recomputed from per-gap facts (producer's rounded percent is distrusted).
  Emitted only when `unmeasuredGaps == 0` — a partially measured run yields
  `null` → NOT_EVALUATED, never a subset estimate.
- `B7_COMPARATOR` = rate `>` B7 fails ⇒ rate `≤` B7 passes (inclusive).
- `SCHEMA_DEFAULT` = NONE · `EVALUATOR_DEFAULT` = NONE.
- Integer effect (verified by tests): in a complete 10-event run,
  `0/9 = 0%`, `1/9 = 11.111%`, `2/9 = 22.222%`. With B7 = 10:
  `1/9 = 11.111% > 10` → NOT_SATISFIED.
- `DOES_B7_10_PERCENT_ALLOW_ONE_VIOLATING_GAP_IN_ONE_COMPLETE_10_EVENT_RUN` =
  **NO**.

> B7=10% is declared, but with nine qualified consecutive gaps in a complete
> ten-event run, one violating gap represents 11.11% and therefore exceeds the
> 10% allowance. The integer denominator makes this policy effectively
> zero-tolerance for a single violating gap in that run shape. This is not
> necessarily a policy defect — it is an important consequence of the chosen
> denominator, now disclosed. (The assessed breach run exhibited this directly:
> eligibleGaps=8, one violating gap = 12.5% > 10%.)

> C7 remains NOT_SATISFIED on coverage (90% < 100%). B7 concerns gap duration
> only; it cannot rescue a missing required event. No post-hoc timing-exception
> allowance has been applied beyond the frozen declared B7=10%. Audit-store seq
> is record-write cadence, not original action-occurrence latency — no
> cross-source action latency is claimed.

**C7_THRESHOLD_DEFENSIBILITY = DEFENSIBLE_WITH_LIMITATION** — coverage rule is
absolute and clean; the 30s gap bound is a stall-separation bound with rare
real exceedances, and B7=10% is effectively zero-tolerance at the 9-gap
denominator (integer effect now disclosed).

---

## 4. C16 — token cap analysis

Frozen comparator: `total_qualified_tokens <= 60,000` per run; over-cap allowance zero.

Assessed pair (same frozen policy digest — comparable):

```
PASS:    35,559 / 60,000  → headroom = 60,000 - 35,559 = 24,441 tokens
         utilization    = 35,559 / 60,000 x 100 = 59.3%
         (8 calls; gateway corroboration 34,917 in + 642 out = 35,559)
BREACH: 106,829 / 60,000  → overshoot = 106,829 - 60,000 = 46,829 tokens
         overshoot %    = 46,829 / 60,000 x 100 = 78.0% above cap
         (17 calls)
```

### Pre-freeze healthy token population

Qualifying runs captured before the 01:28:02Z freeze (control-basis totals;
span-derived usage deduplicated by ÷2 normalization — anchors: fault-…-5e3126
→ 35,559 and fault-…-bdd7e3 → 2,828,243 both reproduce exactly):

| Run | Calls | Total tokens |
|---|---|---|
| fault-1791160393-344490 | 11 | ~49,969 |
| fault-1791160491-d961be | 9 | ~40,167 |
| fault-1791160617-59b8bc | 9 | ~40,681 |

N_RUNS=3 — too small for percentiles: MIN=40,167 · MAX=49,969 · MEAN=43,606 ·
MEDIAN=40,681 · STDDEV≈5,430. All three completed their intended task.

Observed arithmetic: `49,969 x 1.20 = 59,962.8`; `ROUNDING_DELTA =
60,000 - 59,962.8 = 37.2` — 60,000 is the rounded governance cap corresponding
approximately to a 20% reserve over the maximum qualified healthy run.
This is consistent with **MAX_HEALTHY_PLUS_RECOVERY_RESERVE**, but the policy
notes record no derivation — so the honest classification is
**ENGINEERING_BOUND + INSUFFICIENT_PRE_FREEZE_RATIONALE**: the recovered
population supports the arithmetic consistency claim only.
**The 60,000-token cap was not derived from the breach.**

Excluded from calibration: runaway fault-1791164066-bdd7e3 (2,828,243 tokens —
anomaly, not healthy); all runs captured post-freeze (temporal ineligibility —
the C16 breach/pass assessed runs themselves must not serve as calibration).

**C16 vs `modaas-ceiling` (separate):** the platform's hourly Agentgateway token
limit (2,500,000 tokens/Hours, one proxy replica, post-completion charging) is
a platform guardrail, not the HAIEC C16 per-run cap. SEC-02's enforcement
anomaly (2,828,243 tokens accepted, no token-based 429) is a platform-finding;
C16's deterministic measurement at 60,000 is unaffected.

**C16_THRESHOLD_DEFENSIBILITY = DEFENSIBLE_WITH_LIMITATION** — clean comparator
and corroborated measurements; thin pre-freeze calibration (N=3) and no recorded
selection rationale.

---

## 5. Summary table

| CONTROL | METRIC | CALIBRATION_POPULATION | DESCRIPTIVE_STATS | OBSERVATION_LIMIT | EXCEPTION_TOLERANCE | COVERAGE | SELECTION_METHOD | ENGINEERING_MARGIN | REJECTED_ALTERNATIVES | POLICY_VERSION | FROZEN_AT | LIMITATION |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AIA-LOG-001 | required-event coverage; consecutive-record gap | 504 healthy write-cadence gaps | max 67,682ms; median 451.5; P95 3,621 | 10 required events; gap <30s | B7=10% (policy-declared; absent in manifest) | 100% (9/10=90% → NOT_SATISFIED) | STALL_SEPARATION_BOUND; rationale PARTIAL | 30s = 8.29× healthy P95; rare boundary stalls exceed it; B7 integer effect: 1/9=11.11% >10% → effectively zero-tolerance at 9 gaps | n/a (organizer manifest fixed) | c7-thresholds-v1 | 2026-10-05T01:28:01.997Z | seq=write cadence ≠ action latency; LT/LTE inconsistency; B7 absent in manifest |
| AIA-ARC-006 | duration_ms MEAN per agent-window | 37 windows / 12 runs (2 outliers excl.) | normalized: mean 0, median -8.2, max +86.3 | D=100% | B9=0% | per declared window | STATISTICALLY_DERIVED + CONSERVATIVE_EVENT_BOUND | +13.7pt over worst healthy window | D=25/50/75% reject healthy windows | c9-duration-thresholds-v2 | 2026-10-05T06:51:04.002Z | N=37 single-event population; baseline ≡ calibration mean by construction |
| ACN-COST-001 | qualified tokens/run (SUM) | 3 healthy pre-freeze runs | min 40,167; max 49,969; mean 43,606 | 60,000/run LTE | 0 over-cap | per run | ENGINEERING_BOUND (arithmetic consistent with max+20%); rationale PARTIAL | +20% over healthy max | n/a tested | c16-cap-v1 | 2026-10-05T01:28:02.294Z | N=3 calibration; no recorded derivation; retry completeness NOT_ESTABLISHED |

Threshold governance lifecycle:

```
CALIBRATE → HUMAN SELECT → FREEZE/VERSION → ASSESS → PRESERVE FAILURES → RETEST UNDER SAME RULE
```

> Deterministic assurance removes discretion from how the threshold is
> evaluated; it does not remove the need for a threshold when the control
> itself is quantitative.

> Tolerance, where required, is explicit, frozen and policy-owned. Exact
> controls may use zero tolerance; variable operational metrics use a
> declared allowance.
