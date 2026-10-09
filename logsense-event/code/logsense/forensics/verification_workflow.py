from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from logsense.analysis.spine import ArtifactEvidence, analyze_artifacts
from logsense.forensics.evidence_sets import build_evidence_set
from logsense.forensics.verification import VerificationContractError, evaluate_frontier_closure

_SNAPSHOT_REF_FIELDS = (
    "entityRefs",
    "eventRefs",
    "sourceRefs",
    "correlationGroupRefs",
    "actionGroupRefs",
    "relationEvaluationRefs",
    "stateTransitionRefs",
    "detectionSignalRefs",
    "contradictionRefs",
    "divergenceRefs",
    "timelineEventRefs",
    "fivePlaneCoverageRefs",
    "actionLifecycleCoverageRefs",
    "gapRefs",
    "duplicateGroupRefs",
)


def _explicit_evidence_refs(value: Any, *, key: str | None = None) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            refs.update(_explicit_evidence_refs(child_value, key=str(child_key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if key == "evidenceRefs":
            refs.update(str(child) for child in value if child is not None and str(child))
        else:
            for child in value:
                refs.update(_explicit_evidence_refs(child, key=key))
    return refs


def analysis_reference_inventory(analysis: Mapping[str, Any]) -> list[str]:
    """Return analysis-emitted references eligible to bind verification evidence.

    Canonical event IDs are evidence anchors. Explicit `evidenceRefs` emitted by
    deterministic projections are also eligible. Internal object identifiers
    such as snapshotId, sourceId, artifactId, gapId, and analysisRunId are not
    automatically promoted into verification proof.
    """
    refs = _explicit_evidence_refs(analysis)
    refs.update(
        str(event.get("eventId"))
        for event in analysis.get("canonicalEvents") or ()
        if event.get("eventId")
    )
    return sorted(refs)


def _snapshot_delta(prior: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    for field in _SNAPSHOT_REF_FIELDS:
        before = {str(x) for x in prior.get(field, ()) if str(x)}
        after = {str(x) for x in new.get(field, ()) if str(x)}
        added = sorted(after - before)
        removed = sorted(before - after)
        if added or removed:
            deltas[field] = {
                "addedRefs": added,
                "removedRefs": removed,
                "limitations": ["REMOVED_FROM_OBSERVED_SET_NE_PROVEN_ABSENCE"] if removed else [],
            }
    return {
        "priorSnapshotRef": str(prior.get("snapshotId") or ""),
        "newSnapshotRef": str(new.get("snapshotId") or ""),
        "priorSnapshotDigest": str(prior.get("digest") or ""),
        "newSnapshotDigest": str(new.get("digest") or ""),
        "snapshotChanged": prior.get("digest") != new.get("digest"),
        "refDeltas": deltas,
        "semanticLimitations": ["SNAPSHOT_DELTA_NE_ROOT_CAUSE", "REMOVED_REF_NE_PROVEN_ABSENCE"],
    }


def prepare_frontier_verification(
    *,
    prior_snapshot: Mapping[str, Any],
    verification_artifacts: Sequence[ArtifactEvidence],
    evidence_set_id: str,
    analysis_run_id: str,
    created_at: str,
    evidence_set_label: str = "Verification",
    evidence_set_role: str = "VERIFICATION",
    evidence_set_limitations: Sequence[str] = (),
    analysis_kwargs: Mapping[str, Any] | None = None,
    analysis_runner: Callable[..., Mapping[str, Any]] = analyze_artifacts,
) -> dict[str, Any]:
    """Analyze verification evidence into a fresh immutable snapshot.

    No frontier closure occurs here. This stage exists so operators can inspect
    the new deterministic analysis and bind a test only to references that were
    actually emitted by it.
    """
    prior_before = deepcopy(dict(prior_snapshot))
    case_id = str(prior_snapshot.get("caseId") or "")
    prior_snapshot_ref = str(prior_snapshot.get("snapshotId") or "")
    if not case_id or not prior_snapshot_ref:
        raise VerificationContractError("prior snapshot requires caseId and snapshotId")

    evidence_set = build_evidence_set(
        verification_artifacts,
        evidence_set_id=evidence_set_id,
        case_id=case_id,
        label=evidence_set_label,
        role=evidence_set_role,
        imported_at=created_at,
        limitations=evidence_set_limitations,
    )
    kwargs = dict(analysis_kwargs or {})
    analysis = dict(
        analysis_runner(
            verification_artifacts,
            case_id=case_id,
            evidence_set_id=evidence_set_id,
            analysis_run_id=analysis_run_id,
            created_at=created_at,
            **kwargs,
        )
    )
    new_snapshot = dict(analysis.get("snapshot") or {})
    new_snapshot_ref = str(new_snapshot.get("snapshotId") or "")
    if not new_snapshot_ref:
        raise VerificationContractError("verification analysis did not emit a snapshot")
    if new_snapshot_ref == prior_snapshot_ref:
        raise VerificationContractError("verification analysis must emit a new immutable snapshot")
    if dict(prior_snapshot) != prior_before:
        raise RuntimeError("prior snapshot mutated during verification preparation")

    return {
        "evidenceSet": evidence_set,
        "analysis": analysis,
        "priorSnapshot": prior_before,
        "newSnapshot": new_snapshot,
        "availableEvidenceRefs": analysis_reference_inventory(analysis),
        "comparison": _snapshot_delta(prior_before, new_snapshot),
        "semanticLimitations": [
            "PREPARATION_DOES_NOT_CLOSE_FRONTIER",
            "NEW_SNAPSHOT_DOES_NOT_MUTATE_PRIOR_SNAPSHOT",
        ],
    }


def finalize_frontier_verification(
    prepared: Mapping[str, Any],
    *,
    frontier: Mapping[str, Any],
    forensic_test: Mapping[str, Any],
    closed_at: str,
    closure_basis: str = "TEST_RESULT",
    closure_reason: str | None = None,
    documented_non_execution_predicate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a ForensicTest to prepared analysis evidence and compute closure."""
    prior_snapshot = dict(prepared.get("priorSnapshot") or {})
    new_snapshot = dict(prepared.get("newSnapshot") or {})
    analysis = dict(prepared.get("analysis") or {})
    prior_snapshot_ref = str(prior_snapshot.get("snapshotId") or "")
    new_snapshot_ref = str(new_snapshot.get("snapshotId") or "")
    if not prior_snapshot_ref or not new_snapshot_ref:
        raise VerificationContractError("prepared verification requires prior and new snapshots")
    if prior_snapshot_ref == new_snapshot_ref:
        raise VerificationContractError("verification must use a new immutable snapshot")

    result = str(forensic_test.get("result") or "").upper()
    if result in {"PASS", "FAIL"}:
        emitted = set(prepared.get("availableEvidenceRefs") or analysis_reference_inventory(analysis))
        evidence_refs = {str(x) for x in forensic_test.get("evidenceRefs", ()) if str(x)}
        missing = sorted(evidence_refs - emitted)
        if missing:
            raise VerificationContractError(
                "forensic test evidenceRefs were not emitted as verification-eligible evidence by the new analysis: "
                + ", ".join(missing)
            )

    closure = evaluate_frontier_closure(
        frontier,
        forensic_test,
        prior_snapshot_ref=prior_snapshot_ref,
        new_snapshot_ref=new_snapshot_ref,
        closed_at=closed_at,
        closure_basis=closure_basis,
        closure_reason=closure_reason,
        documented_non_execution_predicate=documented_non_execution_predicate,
    )
    return {
        **dict(prepared),
        "closure": closure,
        "comparison": _snapshot_delta(prior_snapshot, new_snapshot),
        "semanticLimitations": sorted(
            set(prepared.get("semanticLimitations", ()))
            | {"VERIFICATION_CLOSURE_NE_ROOT_CAUSE", "NEW_SNAPSHOT_DOES_NOT_MUTATE_PRIOR_SNAPSHOT"}
        ),
    }


def run_frontier_verification(
    *,
    prior_snapshot: Mapping[str, Any],
    frontier: Mapping[str, Any],
    forensic_test: Mapping[str, Any],
    verification_artifacts: Sequence[ArtifactEvidence],
    evidence_set_id: str,
    analysis_run_id: str,
    created_at: str,
    evidence_set_label: str = "Verification",
    evidence_set_role: str = "VERIFICATION",
    evidence_set_limitations: Sequence[str] = (),
    analysis_kwargs: Mapping[str, Any] | None = None,
    closure_basis: str = "TEST_RESULT",
    closure_reason: str | None = None,
    documented_non_execution_predicate: Mapping[str, Any] | None = None,
    analysis_runner: Callable[..., Mapping[str, Any]] = analyze_artifacts,
) -> dict[str, Any]:
    """Compatibility wrapper composing prepare + finalize verification stages."""
    prepared = prepare_frontier_verification(
        prior_snapshot=prior_snapshot,
        verification_artifacts=verification_artifacts,
        evidence_set_id=evidence_set_id,
        analysis_run_id=analysis_run_id,
        created_at=created_at,
        evidence_set_label=evidence_set_label,
        evidence_set_role=evidence_set_role,
        evidence_set_limitations=evidence_set_limitations,
        analysis_kwargs=analysis_kwargs,
        analysis_runner=analysis_runner,
    )
    return finalize_frontier_verification(
        prepared,
        frontier=frontier,
        forensic_test=forensic_test,
        closed_at=created_at,
        closure_basis=closure_basis,
        closure_reason=closure_reason,
        documented_non_execution_predicate=documented_non_execution_predicate,
    )
