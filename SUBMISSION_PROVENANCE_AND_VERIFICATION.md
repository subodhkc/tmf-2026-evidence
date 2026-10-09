# Event evidence provenance and independent verification boundary

**Evidence release:** [v7a0bb5f3](https://github.com/subodhkc/tmf-2026-evidence/releases/tag/v7a0bb5f3)

**Frozen tree commit:** `3cdfbc91ea010e40ae75de869176a8f038b4ce34`

**Published TAR:** `haiec-package-final-7a0bb5f3.tar.gz`, 1,158,356 bytes

**GitHub release asset SHA-256:** `0321b7127e544c5dcad453608f5e22f72c0c409735f07a1b924eaa4ecc4d966a`

## Verification categories

| Claim | Status | Basis |
| --- | --- | --- |
| Public repository, tag, commit, TAR and SHA-256 sidecar exist | VERIFIED | GitHub source and release metadata |
| All 506 manifest paths present at original tag | VERIFIED | Complete tagged tree inventory |
| Manifest hash and seven selected payload-file hashes | VERIFIED in prior reader audit | [Public Release Verification Record](https://docs.google.com/document/d/1PWKHuLWwUkGzRzDjUQpGoXWCin8xsENupcZ0dQmMLZk/edit) |
| All 506 actual payload hashes independently checked | RUNNABLE, not implied by the previous review | `python3 scripts/verify_frozen_evidence.py` in a byte-preserving clone |
| Original normalized C16/C9 arithmetic independently recomputed | RUNNABLE, source-qualified | Same read-only verifier; depends on archived normalized measurements |
| Organizer receipt, upload timestamp, and byte-exact organizer-held submission | NOT INDEPENDENTLY ESTABLISHED | Need organizer bucket receipt, platform record, exact submitted hash or attestation |
| Subsequent October 6 system `44f861cf` C7/C9 demonstrations in this release | NOT INCLUDED | Separate pinned HAIEC feature-branch release candidate, not the original public archive |
| External scientific validation, permission to redistribute all third-party content | NOT ESTABLISHED | Independent review and rights/privacy clearance required |

The original README and release body describe this payload as the submitted evidence package, reflecting the publisher's submission identity assertion. A later GitHub publication with a matching participant-provided TAR digest establishes an inspectable archived version, **not by itself an organizer-origin hand-in receipt**.

Run the included stdlib-only verifier from a clean checkout of `v7a0bb5f3` after obtaining the verification script from this subsequently authored branch or repository main. The original frozen tag itself deliberately lacks the later verifier; do not claim it was part of the competition submission.

The verifier checks exactly the archived source values it declares. It does not call AWS/ServiceNow, re-run event scenarios, reconstruct the missing original C7 primitive source from external systems, or convert the supplemental report into a canonical HAIEC Master Assurance Evaluation.

**Known source errata:** [C7 crosswalk](C7_CROSSWALK_ERRATUM.md) and the original [C9 timestamp-labeling erratum](C9_TIMESTAMP_ERRATUM.md). Neither changes a historical control result.

**Publication safety:** The original evidence discusses organizer-owned assets and exposed shared credentials. The public repository's MIT wrapper does not establish redistribution rights over every upstream source. Do not add unreviewed raw organizer or HAIEC private records, credentials, human-response links, or third-party data to a supplemental release.
