from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ForensicCaseState:
    state_id: str
    state_label: str
    scenario_sequence: int
    scenario_run_id: str
    evidence_set_id: str
    analysis_run_id: str
    snapshot_digest: str
    analysis_perimeter_ref: str
    evidence_refs: tuple[str, ...] = ()
    evidence_frontier_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


_DIVERGENCE_KEYS = (
    "firstEvidenceDivergence",
    "firstBehavioralDivergence",
    "firstIntegrityContradiction",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ordered_states(states: Sequence[ForensicCaseState]) -> list[ForensicCaseState]:
    if len(states) < 2:
        raise ValueError("forensic case requires at least two scenario states")
    ordered = sorted(states, key=lambda s: s.scenario_sequence)
    ids = [s.state_id for s in ordered]
    seqs = [s.scenario_sequence for s in ordered]
    if len(set(ids)) != len(ids):
        raise ValueError("forensic case state IDs must be unique")
    if len(set(seqs)) != len(seqs):
        raise ValueError("forensic case scenario sequence values must be unique")
    if any(b.scenario_sequence <= a.scenario_sequence for a, b in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("forensic case scenario sequence must be strictly increasing")
    return ordered


def _divergence_rows(divergence_projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in _DIVERGENCE_KEYS:
        row = divergence_projection.get(key)
        if row is None:
            continue
        if row.get("rootCauseClaimed") is not False:
            raise ValueError("forensic case accepts only non-root-cause divergence projections")
        rows.append(dict(row))
    return rows


def build_forensic_case_projection(
    states: Sequence[ForensicCaseState],
    *,
    case_id: str,
    scenario_id: str,
    divergence_projection: Mapping[str, Any],
    schema_version: str = "1.0",
    unresolved_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Compose exact multi-state forensic references without merging state truth.

    The projection identifies the earliest adjacent scenario boundary carrying a
    qualified divergence. It never turns temporal order or first divergence into
    a root-cause claim, and it blocks comparisons across changed analysis
    perimeters.
    """
    ordered = _ordered_states(states)
    state_by_evidence = {s.evidence_set_id: s for s in ordered}
    if len(state_by_evidence) != len(ordered):
        raise ValueError("forensic case evidence-set IDs must be unique")

    divergence_rows = _divergence_rows(divergence_projection)
    by_boundary: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in divergence_rows:
        before = str(row.get("baselineRef") or "")
        after = str(row.get("candidateRef") or "")
        if before not in state_by_evidence or after not in state_by_evidence:
            raise ValueError("divergence references evidence outside forensic case states")
        left = state_by_evidence[before]
        right = state_by_evidence[after]
        if right.scenario_sequence <= left.scenario_sequence:
            raise ValueError("divergence direction conflicts with explicit scenario sequence")
        by_boundary.setdefault((before, after), []).append(row)

    state_rows = [
        {
            "stateId": s.state_id,
            "stateLabel": s.state_label,
            "scenarioSequence": s.scenario_sequence,
            "scenarioRunId": s.scenario_run_id,
            "evidenceSetId": s.evidence_set_id,
            "analysisRunId": s.analysis_run_id,
            "snapshotDigest": s.snapshot_digest,
            "analysisPerimeterRef": s.analysis_perimeter_ref,
            "evidenceRefs": sorted(set(s.evidence_refs)),
            "evidenceFrontierRefs": sorted(set(s.evidence_frontier_refs)),
            "limitations": sorted(set(s.limitations)),
        }
        for s in ordered
    ]

    transitions: list[dict[str, Any]] = []
    first_divergence: dict[str, Any] | None = None
    global_limits = {str(x) for x in limitations if str(x)}
    global_limits.add("FIRST_DIVERGENCE_NE_ROOT_CAUSE")

    for left, right in zip(ordered, ordered[1:], strict=False):
        boundary_rows = by_boundary.get((left.evidence_set_id, right.evidence_set_id), [])
        transition_limits: set[str] = set()
        comparable = (
            bool(left.analysis_perimeter_ref)
            and left.analysis_perimeter_ref == right.analysis_perimeter_ref
        )
        if not comparable:
            availability = "INCOMPARABLE"
            transition_limits.add("ANALYSIS_PERIMETER_CHANGED_NE_SYSTEM_DRIFT")
            usable_rows: list[dict[str, Any]] = []
        else:
            availability = "AVAILABLE"
            usable_rows = boundary_rows

        divergence_refs = sorted(str(x["divergenceId"]) for x in usable_rows)
        divergence_kinds = sorted(str(x["type"]) for x in usable_rows)
        dimensions = sorted(str(x["dimension"]) for x in usable_rows)
        proof_refs = sorted({
            str(ref)
            for row in usable_rows
            for ref in row.get("evidenceRefs", [])
        })
        gap_refs = sorted({
            str(ref)
            for row in usable_rows
            for ref in row.get("gapRefs", [])
        })

        comparison_input = {
            "fromStateId": left.state_id,
            "toStateId": right.state_id,
            "fromSnapshotDigest": left.snapshot_digest,
            "toSnapshotDigest": right.snapshot_digest,
            "analysisPerimeterRef": left.analysis_perimeter_ref if comparable else None,
            "divergenceRefs": divergence_refs,
        }
        comparison_digest = _canonical_digest(comparison_input) if comparable else None
        transition = {
            "fromStateId": left.state_id,
            "toStateId": right.state_id,
            "availability": availability,
            "comparisonDigest": comparison_digest,
            "divergenceRefs": divergence_refs,
            "divergenceKinds": divergence_kinds,
            "dimensions": dimensions,
            "proofRefs": proof_refs,
            "gapRefs": gap_refs,
            "limitations": sorted(transition_limits),
        }
        transitions.append(transition)

        if first_divergence is None and availability == "AVAILABLE" and divergence_refs:
            first_divergence = {
                "fromStateId": left.state_id,
                "toStateId": right.state_id,
                "divergenceRefs": divergence_refs,
                "divergenceKinds": divergence_kinds,
                "dimensions": dimensions,
                "proofRefs": proof_refs,
                "gapRefs": gap_refs,
                "limitations": ["FIRST_DIVERGENCE_NE_ROOT_CAUSE"],
                "rootCauseClaimed": False,
            }

    component_digests = {
        "snapshotDigests": [s.snapshot_digest for s in ordered],
        "transitionComparisonDigests": [
            t["comparisonDigest"] for t in transitions if t["comparisonDigest"] is not None
        ],
    }
    semantic_identity = {
        "schemaVersion": schema_version,
        "caseId": case_id,
        "scenarioId": scenario_id,
        "states": state_rows,
        "transitions": transitions,
        "firstDeterministicDivergence": first_divergence,
        "unresolvedRefs": sorted({str(x) for x in unresolved_refs}),
        "componentDigests": component_digests,
    }
    case_digest = _canonical_digest(semantic_identity)

    return {
        **semantic_identity,
        "limitations": sorted(global_limits),
        "caseDigest": case_digest,
    }
