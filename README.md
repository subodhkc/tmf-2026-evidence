# HAIEC — TM Forum 2026 Agentic Assurance Evidence Pack

Publisher-identified, integrity-verifiable copy of the HAIEC evidence package
prepared during the **TM Forum 2026 Agentic Assurance** competition, built and
exercised inside the AWS Workshop IDE (participant-sanctioned `team-evidence-*`
S3 namespace). The published artifact's relationship to the organizer-held
submission is a separate provenance question; no organizer upload receipt is
included in this repository.

This repository exists so the submission can be cited as a stable public
reference (e.g., from the ISAF research paper and related publications).

## Package identity

| Field | Value |
|---|---|
| Package | `haiec-package-final-7a0bb5f3.tar.gz` |
| SHA-256 | `0321b7127e544c5dcad453608f5e22f72c0c409735f07a1b924eaa4ecc4d966a` |
| Payload files | 506 (all verified against `MANIFEST.sha256`) |
| Assessed system | TM Forum MoDaaS agentic environment (AWS workshop) |

The original tarball and its `.sha256` sidecar are attached to the
[Releases](../../releases) section. The 506 manifest-listed paths in the frozen tagged tree have a published
byte-for-byte verification route — `sha256sum -c MANIFEST.sha256` is expected
to report 506/506 OK on an unmodified checkout. Passing this check validates
the archived Git bytes against the manifest, not organizer hand-in identity.

## Verify integrity

```bash
# after cloning
sha256sum -c MANIFEST.sha256 | grep -v ': OK$'   # expected: no output

# or verify the release tarball itself
sha256sum haiec-package-final-7a0bb5f3.tar.gz
# expected: 0321b7127e544c5dcad453608f5e22f72c0c409735f07a1b924eaa4ecc4d966a
```

## Contents

| Path | What it is |
|---|---|
| `register.yaml` | Consolidated control-test register: control states, assessed runs, enforcement evidence, live-monitoring evidence, security findings, limitations |
| `gap-list.md` | Known gaps and honest non-claims for the assessed system |
| `run-ids.txt` | Canonical run identifiers |
| `evidence/` | Evidence payloads: audit records, pass/breach run traces, enforcement results, judgment-day matrices, monitoring-chain receipts, security findings |
| `logsense-event/` | LogSense TM Forum workbench bundle (the interactive judge interface) with event evidence and install/verify scripts |
| `MANIFEST.sha256` | Per-file SHA-256 manifest of all 506 payload files |
| `PACKAGE-DIGEST.txt` | Package-level digest summary |
| `KUSHAL_REVIEW_CARD.md` | Independent reviewer (stranger-test) card |
| `IDE_PULL_AND_VERIFY.md` | Pull-and-verify procedure used inside the Workshop IDE |
| `C9_TIMESTAMP_ERRATUM.md` | Timestamp labeling erratum (documented; values/verdicts unaffected) |

## Reading guidance

- Verdicts (`SATISFIED` / `NOT_SATISFIED` / `NOT_EVALUATED`) are scoped to the
  frozen policies and available evidence recorded in `register.yaml`.
- `security_findings` are organizer-owned environment findings, documented —
  not remediated — as part of the assurance scope.
- All limitations in `register.yaml` and `gap-list.md` are part of the record.

## Verification and known errata

- [Archive-versus-organizer submission provenance](SUBMISSION_PROVENANCE_AND_VERIFICATION.md)
- [C7 source catalog crosswalk erratum](C7_CROSSWALK_ERRATUM.md)
- [Read-only frozen evidence verifier](scripts/verify_frozen_evidence.py) —
  run from a fresh checkout of the current branch with `python3 scripts/verify_frozen_evidence.py`.
  These additions are **post-event editorial/verification materials**, not files
  in the original `v7a0bb5f3` tag or competition submission.
- The separate October 6 C7 remediation and C9 pass/breach evidence concerns a
  different participant-system scope; those later records are not in the original tag.

## License

MIT — see [LICENSE](LICENSE). Vendored components retain their original
licenses (LogSense is MIT; see `logsense-event/code/LOGSENSE_VERSION.txt`).
