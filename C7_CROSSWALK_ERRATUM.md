# C7 catalog crosswalk erratum — original package unchanged

**Applies to:** public TM Forum Agentic Assurance evidence release `v7a0bb5f3` at commit `3cdfbc91ea010e40ae75de869176a8f038b4ce34`.

The original `register.yaml` identifies `controls.c7.id` as `AIA-ARC-004`. The same archived package's `evidence/judgment-day/TMF_DETECTION_COVERAGE_MATRIX.md` identifies **C7 (AIA-LOG-001)**. This is an internal catalog-identifier discrepancy in the preserved package, not a missing artifact or an integrity/hash failure.

The later October 6 participant-system evaluation and separately recorded organizer control crosswalk use **AIA-LOG-001** for the audit-trail coverage rule. The historical source remains `AIA-ARC-004` in the original register; this addendum does not retroactively change a frozen policy or its assessed verdict.

## Interpretation for ISAF readers

- Original assessed system `4043efee`, policy `ae6dda36`: **9/10**, NEGOTIATION unobserved, **NOT_SATISFIED**. The original failed result is preserved.
- Later participant/remediation system `44f861cf`, policy `dcfa6d38`: separately demonstrated **10/10**, **SATISFIED**. That is not an identical-system/identical-policy rerun and is **not included in the original v7a0bb5f3 archive**.
- Crosswalk claims must cite the *organizer mapping plus the exact policy instance*. Do not infer source authority from one archived shorthand field.
- No new agent tests were executed to prepare this clarification.

This editorial erratum is subsequent to the historical tagged release. It does not modify that release, its `MANIFEST.sha256`, TAR, or any historical control verdict.
