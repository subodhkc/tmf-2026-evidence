# Prospective Policy Review — C7 / C9 / C16

Historical assessed policy versions are immutable. Nothing below modifies,
recomputes, or re-presents any frozen policy or verdict. This document separates:

- `HISTORICAL_POLICY_VALIDITY` — what governed the observed event (preserved)
- `PROSPECTIVE_POLICY_RECOMMENDATION` — what should govern FUTURE assessed runs

Versioning rule honored: existing results keep their frozen governing versions;
any improvement lands only as a new version, frozen, then assessed.

---

## C9 — AIA-ARC-006

### HISTORICAL_POLICY_VALIDITY (preserved — governs all existing results)

v2 `c9-duration-thresholds-v2` / baseline `c9-duration-baseline-tmf-modaas@v1`:
customer=6,781 · IT=8,917 · network=12,141 ms · D=100% · B9=0% ·
metric `aws.bedrock-agentcore.duration_ms` MEAN per agent-window ·
LOWER_IS_BETTER. Frozen 2026-10-05T06:51:04.002Z.

### Baseline quality test (37 qualified healthy windows, 12 runs)

| Agent | n | frozen mean | sample mean | median | trim-20% | σ | MAD | IQR | min | max | mean-w/o-max | outlier sensitivity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| customer | 13 | 6,781 | 6,781 | 6,833 | 6,909 | 1,915 | 1,057 | 2,683 | 2,417 | 9,412 | 6,562 (-3.2%) | LOW — mean≈median |
| IT | 12 | 8,917 | 8,917 | 8,041 | 9,130 | 4,133 | 4,478 | 7,929 | 3,037 | 14,329 | 8,425 (-5.5%) | MODERATE — right-skew, mean +10.9% over median |
| network | 12 | 12,141 | 12,141 | 10,596 | 11,813 | 5,401 | 2,908 | 7,939 | 3,406 | 22,624 | 11,188 (-7.8%) | MODERATE — right-skew, mean +14.6% over median |

Reading: customer baseline is well-behaved (mean ≈ median). IT and network
means sit 11–15% ABOVE their medians — the frozen means are pulled up by a
right tail. For a lower-is-better metric, the upward-skewed mean baseline is
conservative against false-positive drift declarations, but correspondingly
reduces sensitivity to moderate degradation. This tradeoff is disclosed.
Replacing mean is not automatically better: the frozen metric contract is
MEAN per agent-window, and a median baseline would need its own new version.
`BASELINE_METHOD_RECOMMENDATION_FOR_V3`: keep MEAN (metric-contract
consistency) but RECOMPUTE on a larger, multi-period stable baseline — the
skew is a sample-size artifact as much as a method artifact.

### C9 future-version decision

| Question | Answer |
|---|---|
| `IS_CURRENT_BASELINE_REPRESENTATIVE` | **PARTIAL** — per-agent matched means are legitimate, but right-skew inflates IT/network means ~11–15% over medians; N=37 windows, single event, one day |
| `IS_D_100_SUPPORTED_BY_HEALTHY_VARIABILITY` | **MODERATELY** — smallest of the coarse candidates tested (25/50/75/100) with 0/37 healthy rejections (13.7 percentage points over worst healthy +86.3%); but only 4 discrete candidates and a thin sample |
| `IS_THE_PROBLEM_BASELINE_OR_TOLERANCE` | **NEITHER** — policy performed as designed; the actual limitation is calibration-population thinness, not baseline method or D choice |
| `BEST_PROSPECTIVE_D_FROM_AVAILABLE_EVIDENCE` | **100 (retain)** — evidence-derived minimum is D≥86.3+margin; see derivation below. A tighter responsible candidate exists: **D=95** (+8.7pt over worst healthy, ≈10% relative headroom) |
| `BEST_PROSPECTIVE_B9` | **0% if D=100 retained**; **5%** only if D is tightened to ≤90% (the +86.3% window is 1/37 = 2.7%, covered by a 5% allowance) |
| `PROSPECTIVE_BASELINE_CHANGE_REQUIRED` | **NO value change required; METHOD/POPULATION refresh recommended** — BaselineVersion v2 = same MEAN method, larger stable observation window |

### Derivation of the evidence-derived candidates (not round numbers)

```
constraint (B9=0):      D >= worst healthy window = 86.3%
engineering margin:     +10% relative headroom over observed max
                        (N=37, single event — tail risk is under-sampled)
candidate_min:          86.3 x 1.10 = 94.9 → D = 95%
candidate_retained:     D = 100% → margin = +13.7pt = 15.9% relative headroom
                        over observed worst healthy; still 3x–36x below the
                        observed fault range (+300% to +3600%)
```

Sensitivity of the two defensible options:

| Candidate | Margins | Healthy rejections today | Trade-off |
|---|---|---|---|
| **D=100 (retained)** | +13.7pt / +15.9% | 0/37 | Maximum safety against unknown healthy tail; slightly looser |
| D=95 | +8.7pt / +10.1% | 0/37 | Tighter, still zero-rejection; thinner safety on unseen tail |
| D=90 | +3.7pt / +4.3% | 0/37 | Margin too thin for N=37 without raising B9 |
| D=75 | below max | 1/37 | Rejects observed healthy — invalid at B9=0 unless B9≥3% |

**PROSPECTIVE_POLICY_RECOMMENDATION (C9 v3):** retain D=100, B9=0, same
baseline method — the evidence does not support a tighter policy responsibly
at N=37. The justified v3 improvement is `BaselineVersion v2`: identical MEAN
method, recomputed on a larger multi-period stable baseline, with the same
derivation repeated. If a future event produces a deeper healthy population,
D=95 becomes defensible. No urgency to mint v3 before then.

---

## C7 — AIA-LOG-001

### HISTORICAL_POLICY_VALIDITY (preserved)

`c7-thresholds-v1`: coverage 100% of 10 required events; gap limit 30,000ms;
`allowedGapViolationRatePercent = 10` (B7 — declared in the frozen HAIEC
policy, absent in the organizer-supplied manifest); comparator: manifest `LT`
vs policy `LTE` (recorded inconsistency). 9/10 = 90% → NOT_SATISFIED stands.

### PROSPECTIVE_POLICY_RECOMMENDATION (C7 v2, prospective only)

| Field | Future value | Rationale |
|---|---|---|
| `FUTURE_COVERAGE_C` | **100%** (unchanged) | Coverage is a binary completeness contract; nothing in the evidence suggests relaxing it |
| `FUTURE_G` | **30,000ms** (unchanged) | `30,000 / P95 3,621 = 8.29×` (and 66.4× median, 9.74× P90); rare >30s boundary stalls exist (max 67,682ms, ~1.6%, between-turn operating condition — exact cause NOT_ESTABLISHED); G = STALL_SEPARATION_BOUND — raising it would hide real stalls |
| `FUTURE_B7` | **Recommendation below — integer effect must be declared** | Resolved from implementation: `violationRate = violatingGaps / eligibleGaps × 100` per run; rate > B7 fails. At the 9-gap denominator of a complete run, 1/9 = 11.111% > 10% — **B7=10% permits ZERO violating gaps in that shape** |

`FUTURE_B7_RECOMMENDATION`: choose by declared intent —

- If intent = *"permit no violating gaps"*: retain B7=10% — acceptable, but the
  integer effect (zero-tolerance at ≤10 gaps) must be documented as intended.
- If intent = *"permit at most one timing outlier in a complete 10-event /
  9-gap run"*: B7 must mathematically reach `1/9 × 100 = 11.111…%`, so the
  minimum percent is **> 11.111** — e.g. **11.12%** (smallest hundredth) or
  **12%** (readable, still allows only one gap at denominator 9 since
  2/9 = 22.2%). **Preferred representation: an explicit integer
  `maxViolatingGaps = 1`** if a future schema supports it — deterministic,
  judge-legible, denominator-independent, not pseudo-precise. Otherwise
  B7 = 12% with a note that percent denominators vary by run shape.

`INTENDED_INTEGER_EFFECT`: at 9 eligible gaps — B7=10% allows 0 gaps;
B7=12% allows exactly 1 (2/9=22.2% > 12%); `maxViolatingGaps=1` allows
exactly 1 at any denominator ≥1.

`RATIONALE`: percent-of-gaps denominators change with run shape (9 events →
8 gaps, 10 events → 9 gaps); an integer count expresses the actual intent
"one outlier per run" without denominator arithmetic. Whatever is chosen must
be declared in **both** the organizer-facing manifest and the HAIEC policy,
with a single comparator spelling (recommend `LTE` for the gap bound).

> Recommendation only — no new policy is created or frozen in this pass;
> nothing above alters the historical C7 result.

---

## C16 — ACN-COST-001

### HISTORICAL_POLICY_VALIDITY (preserved)

`c16-cap-v1`: hardCapTokens=60,000 LTE per run, over-cap allowance NONE,
frozen 2026-10-05T01:28:02.294Z. PASS 35,559 / BREACH 106,829 stand.

### PROSPECTIVE_POLICY_RECOMMENDATION (C16 v2)

`KEEP_60000_FOR_FUTURE` = **YES** — with a derivation-now-recorded basis:

```
healthy pre-freeze population (N=3): 40,167 / 40,681 / 49,969
max healthy + ~20% reserve = 49,969 x 1.20 ≈ 59,963 → 60,000
breach observed: 106,829 = 1.78x cap — genuinely anomalous, not marginal
```

The cap sits in the right band: above the healthy maximum with usable
headroom, far below observed pathology. It is NOT derived from the breach.
The v2 improvement (prospective, non-numeric): record the derivation at
freeze time (this doc), expand the healthy run population, and close the
frozen-note gap `retry completeness NOT_ESTABLISHED` so token accounting is
complete. No cap change justified by current evidence.

---

## Versioning statement

```
existing C9 v2 / C7 v1 / C16 v1        → preserved forever (govern all existing results)
new C9 v3 / C7 v2 / C16 v2 (if adopted) → freeze + timestamp FIRST
future assessed run                     → evaluated under the new version only
```

Never: existing run → new threshold → rewritten verdict.
