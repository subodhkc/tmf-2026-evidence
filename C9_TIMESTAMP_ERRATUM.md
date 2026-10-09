# C9 ERRATUM — Bundle Timestamp Labeling Defect

**Date discovered:** 2026-10-05 · **Status:** ORIGINAL_PRESERVED / CORRECTED_EVIDENCE_PENDING_FINAL_PACKAGE_REFRESH

## DEFECT

`c9_build.py` serialized botocore `tzlocal()` datetime objects with a literal
`"Z"` suffix (`strftime("%Y-%m-%dT%H:%M:%SZ")`). On the UTC−5 build machine, all
KPI observation `ts` / `windowStart` / `observedAt` fields in the four C9 bundles
carry **local time mislabeled as UTC (−5h)**.

Affected bundles:
- `c9-events-fault-1791182726-16a99e.jsonl`
- `c9-events-fault-1791182802-4905b1.jsonl`
- `c9-events-fault-1791183079-256a5e.jsonl`
- `c9-events-fault-1791183213-228329.jsonl`

## NOT AFFECTED

- Measured metric **values** — verified equal to raw CloudWatch datapoints
  (e.g. IT agent 9,582 ms; values are time-independent).
- Frozen policy `346b5f43`, baseline, D=100%, B9=0%, arithmetic, HAIEC verdicts.
- **Assessed status**: platform audit-store timestamps (server-side, true UTC)
  prove assessed activity at `06:51:44Z` / `06:53:45Z` on 2026-10-05 — after the
  v2 freeze. Temporal gate intact on real time.
- C16 bundles — carry platform audit timestamps, verified coherent.

## CORRECTION

`c9_build.py` now calls `.astimezone(timezone.utc)` before serialization.
Verified by rerun: same datapoints now label `06:51–06:54Z` (was `01:51–01:54`).

## LINEAGE

Originals preserved untouched. Corrected-lineage bundles will be regenerated
under new artifact names at the next package refresh; this erratum ships in the
package root.
