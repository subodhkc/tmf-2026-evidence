from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_ALLOWED_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
_ALLOWED_CLOSURES = {"CLOSED", "DOCUMENTED_NON_EXECUTION", "STILL_OPEN", "CONTRADICTED"}


def project_evidence_frontier(
    gap: Mapping[str, Any],
    *,
    created_from_snapshot: str,
    proposed_test_ref: str | None = None,
    priority: str = "MEDIUM",
    frontier_id: str | None = None,
) -> dict[str, Any]:
    """Project a GapFinding into a frontier without turning it into a finding.

    GapFinding may bind both domain subjects and canonical ActionGroups. Both are
    legitimate frontier subjects under the frozen Phase 8.7 contract and must be
    retained so a ForensicTest targeting an exact action remains in scope.
    """
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"unsupported frontier priority: {priority}")
    gap_id = str(gap["gapId"])
    acceptable = [str(x) for x in gap.get("acceptableEvidence", []) if str(x)]
    blocks = [str(x) for x in gap.get("blocks", []) if str(x)]
    missing_fact = ", ".join(blocks) if blocks else str(gap.get("gapType") or "UNRESOLVED_FACT")
    requirement = (
        "Provide qualified evidence: " + "; ".join(acceptable)
        if acceptable
        else "Provide qualified evidence sufficient to close the unresolved fact."
    )
    subject_refs = list(
        dict.fromkeys(
            str(x)
            for x in list(gap.get("subjectRefs", [])) + list(gap.get("actionGroupRefs", []))
            if str(x)
        )
    )
    return {
        "frontierId": frontier_id or f"{gap_id}:frontier",
        "subjectRefs": subject_refs,
        "missingFact": missing_fact,
        "whyNeeded": str(gap.get("whyItMatters") or ""),
        "currentEvidenceRefs": list(dict.fromkeys(str(x) for x in gap.get("evidenceRefs", []))),
        "verificationRequirement": requirement,
        "proposedTestRef": proposed_test_ref,
        "priority": priority,
        "createdFromSnapshot": created_from_snapshot,
        "state": "TEST_DEFINED" if proposed_test_ref else "OPEN",
    }


def project_frontiers_from_gaps(
    gaps: Sequence[Mapping[str, Any]],
    *,
    created_from_snapshot: str,
    test_ref_by_gap_id: Mapping[str, str] | None = None,
    priority_by_gap_type: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], ...]:
    test_ref_by_gap_id = test_ref_by_gap_id or {}
    priority_by_gap_type = priority_by_gap_type or {}
    rows = [
        project_evidence_frontier(
            gap,
            created_from_snapshot=created_from_snapshot,
            proposed_test_ref=test_ref_by_gap_id.get(str(gap["gapId"])),
            priority=priority_by_gap_type.get(str(gap.get("gapType")), "MEDIUM"),
        )
        for gap in gaps
        if gap.get("status") in (None, "OPEN")
    ]
    return tuple(sorted(rows, key=lambda x: x["frontierId"]))


def record_frontier_closure(
    *,
    frontier_id: str,
    prior_snapshot_ref: str,
    new_snapshot_ref: str,
    closed_at: str,
    closure_state: str,
    evidence_refs: Sequence[str],
    closure_reason: str,
    test_run_ref: str | None = None,
) -> dict[str, Any]:
    """Record closure evidence without inventing negative capability facts."""
    if closure_state not in _ALLOWED_CLOSURES:
        raise ValueError(f"unsupported frontier closure state: {closure_state}")
    return {
        "frontierId": frontier_id,
        "priorSnapshotRef": prior_snapshot_ref,
        "testRunRef": test_run_ref,
        "closureState": closure_state,
        "evidenceRefs": list(dict.fromkeys(str(x) for x in evidence_refs)),
        "closureReason": closure_reason,
        "newSnapshotRef": new_snapshot_ref,
        "closedAt": closed_at,
    }
