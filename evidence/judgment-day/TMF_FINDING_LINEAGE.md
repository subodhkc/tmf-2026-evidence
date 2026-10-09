# TM Forum — Final Finding Lineage (candidate -> canonical)

> Every early candidate observation accounted for. Canonical register IDs
> (SEC-01/02/03, EXP-04, HIS-05) are authoritative; older numbering is lineage.

| Original observation | Source evidence | Current disposition | Canonical ID | Control rel. | Detector rel. | Framework rel. | Package location |
|---|---|---|---|---|---|---|---|
| SEC-01 shared plaintext runtime credential | agent spec env + IAM matrix | CANONICAL_FINDING | SEC-01 | — | none (no canonical rule) | UNMAPPED | `../security-findings/SECURITY_FINDINGS_REGISTER.md` |
| SEC-02 token-ceiling enforcement anomaly | gateway logs + policy + schema | CANONICAL_FINDING | SEC-02 | != C16 cap | none | UNMAPPED (RELATED AR-28→ASI08 ref-only) | same |
| SEC-03 phantom tool-call/model-turn runaway | audit + gateway reconstruction | CANONICAL_FINDING | SEC-03 | — | none | UNMAPPED (RELATED AR-28 ref-only) | same |
| SEC-04 public listener scanner exposure | live listener responses | CAPABILITY_EXPOSURE | EXP-04 | — | none | UNMAPPED | same |
| SEC-05 config drift | two-point config snapshots | HISTORICAL/SUPERSEDED | HIS-05 | — | none | NOT_APPLICABLE | same |
| SEC-06 audit provenance (self-written records, shared token) | audit store + corroboration analysis | EVIDENCE_QUALITY_LIMITATION | — (folded into SEC-01 context + quality matrix) | informs C7 evidence weight | — | — | `TMF_EVIDENCE_QUALITY_MATRIX.md` |
| SEC-07 ServiceNow/AICT | CloudTrail AssumeRole + coverage docs | COVERAGE_GAP / capability exposure | SEC-07 (workstream state, not a security finding) | — | — | — | `SERVICENOW_AICT_COVERAGE_MATRIX.md`, `SERVICENOW_AWS_IDENTITY_RECONCILIATION.md` |
| SEC-08 notification-path absence (no SNS/CW alarms/EventBridge/SQS) | account resource enumeration | COVERAGE_GAP | — (gap-list platform dependency) | limits alert-path claims | — | — | `../../gap-list.md` |
| SEC-09 source coverage (not all supported surfaces exercised) | intake/surface inventory | COVERAGE_GAP | — (G-006) | bounds evidence-completeness claims | detector coverage bound | — | `06_Gap_Remediation_Retest_Register_WORKING.md` |
| SEC-10 declared != observed capability | spec vs runtime comparison | AUTHORITY/OBSERVATION LIMITATION | — (folded into five-plane + C7) | C7 lesson | — | — | `TMF_FIVE_PLANE_ASSURANCE_MATRIX.md` |

Notes:

- Nothing silently dropped; nothing promoted into a finding without evidence.
- SEC-06/09/10 survive as honest limitations, not security findings.
- SEC-07 is a named workstream state (PARTIAL), not a canonical finding ID.
