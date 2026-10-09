from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any

_SEMANTIC_PERIMETER_FIELDS = (
    "analyzerId",
    "rulePackDigest",
    "relationMatrixDigest",
    "identityPolicyDigest",
    "sourceQualificationDigest",
    "semanticProfileDigest",
)
_IMPLEMENTATION_PERIMETER_FIELDS = ("analyzerVersion", "buildIdentity", "commitSha")


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _refs(values: Iterable[str]) -> list[str]:
    return sorted({str(v) for v in values if str(v)})


def build_investigation_snapshot(
    *,
    case_id: str,
    evidence_set_id: str,
    analysis_run_id: str,
    created_at: str,
    entity_refs: Iterable[str] = (),
    event_refs: Iterable[str] = (),
    source_refs: Iterable[str] = (),
    correlation_group_refs: Iterable[str] = (),
    action_group_refs: Iterable[str] = (),
    relation_evaluation_refs: Iterable[str] = (),
    state_transition_refs: Iterable[str] = (),
    detection_signal_refs: Iterable[str] = (),
    contradiction_refs: Iterable[str] = (),
    divergence_refs: Iterable[str] = (),
    timeline_event_refs: Iterable[str] = (),
    five_plane_coverage_refs: Iterable[str] = (),
    action_lifecycle_coverage_refs: Iterable[str] = (),
    gap_refs: Iterable[str] = (),
    duplicate_group_refs: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a deterministic immutable-by-convention investigation snapshot."""
    body = {
        "caseId": case_id,
        "evidenceSetId": evidence_set_id,
        "analysisRunId": analysis_run_id,
        "createdAt": created_at,
        "entityRefs": _refs(entity_refs),
        "eventRefs": _refs(event_refs),
        "sourceRefs": _refs(source_refs),
        "correlationGroupRefs": _refs(correlation_group_refs),
        "actionGroupRefs": _refs(action_group_refs),
        "relationEvaluationRefs": _refs(relation_evaluation_refs),
        "stateTransitionRefs": _refs(state_transition_refs),
        "detectionSignalRefs": _refs(detection_signal_refs),
        "contradictionRefs": _refs(contradiction_refs),
        "divergenceRefs": _refs(divergence_refs),
        "timelineEventRefs": _refs(timeline_event_refs),
        "fivePlaneCoverageRefs": _refs(five_plane_coverage_refs),
        "actionLifecycleCoverageRefs": _refs(action_lifecycle_coverage_refs),
        "gapRefs": _refs(gap_refs),
        "duplicateGroupRefs": _refs(duplicate_group_refs),
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }
    digest = _stable_digest(body)
    return {
        "snapshotId": f"snapshot:{digest.split(':', 1)[1][:24]}",
        **body,
        "digest": digest,
    }


def build_analysis_perimeter(
    *,
    investigation_id: str,
    snapshot_digest: str,
    evidence_set_ids: Iterable[str],
    analysis_run_id: str,
    analyzer_id: str,
    analyzer_version: str,
    rule_pack_digest: str,
    relation_matrix_digest: str,
    identity_policy_digest: str,
    source_qualification_digest: str,
    semantic_profile_digest: str,
    created_at: str,
    build_identity: str | None = None,
    commit_sha: str | None = None,
    baseline_perimeter_ref: str | None = None,
    candidate_perimeter_ref: str | None = None,
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "investigationId": investigation_id,
        "snapshotDigest": snapshot_digest,
        "evidenceSetIds": _refs(evidence_set_ids),
        "analysisRunId": analysis_run_id,
        "analyzerId": analyzer_id,
        "analyzerVersion": analyzer_version,
        "rulePackDigest": rule_pack_digest,
        "relationMatrixDigest": relation_matrix_digest,
        "identityPolicyDigest": identity_policy_digest,
        "sourceQualificationDigest": source_qualification_digest,
        "semanticProfileDigest": semantic_profile_digest,
        "createdAt": created_at,
        "limitations": sorted({str(x) for x in limitations if str(x)}),
        "compatibilityState": "EXACT",
        "incompatibleDimensions": [],
        "changedAnalyzerDimensions": [],
        "buildIdentity": build_identity,
        "commitSha": commit_sha,
        "baselinePerimeterRef": baseline_perimeter_ref,
        "candidatePerimeterRef": candidate_perimeter_ref,
    }


def compare_analysis_perimeters(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    baseline_perimeter_ref: str | None = None,
    candidate_perimeter_ref: str | None = None,
) -> dict[str, Any]:
    """Annotate a candidate perimeter with analysis comparability.

    Evidence/snapshot changes are expected comparison inputs. Changes to
    semantic-owner configuration can make the analysis itself incomparable and
    must never be mislabeled as system drift.
    """
    out = deepcopy(dict(candidate))
    changed_semantic = [f for f in _SEMANTIC_PERIMETER_FIELDS if baseline.get(f) != candidate.get(f)]
    changed_impl = [f for f in _IMPLEMENTATION_PERIMETER_FIELDS if baseline.get(f) != candidate.get(f)]
    changed = changed_semantic + changed_impl
    missing = [
        f for f in _SEMANTIC_PERIMETER_FIELDS
        if baseline.get(f) in (None, "") or candidate.get(f) in (None, "")
    ]
    if missing:
        state = "PARTIAL"
        incompatible = []
        limitations = set(out.get("limitations", [])) | {"ANALYSIS_PERIMETER_INCOMPLETE"}
    elif changed_semantic:
        state = "INCOMPARABLE"
        incompatible = changed_semantic
        limitations = set(out.get("limitations", [])) | {"ANALYSIS_PERIMETER_CHANGED_NE_SYSTEM_DRIFT"}
    elif changed_impl:
        state = "COMPATIBLE"
        incompatible = []
        limitations = set(out.get("limitations", []))
    else:
        state = "EXACT"
        incompatible = []
        limitations = set(out.get("limitations", []))
    out["compatibilityState"] = state
    out["incompatibleDimensions"] = sorted(incompatible)
    out["changedAnalyzerDimensions"] = sorted(changed)
    out["limitations"] = sorted(limitations)
    out["baselinePerimeterRef"] = baseline_perimeter_ref
    out["candidatePerimeterRef"] = candidate_perimeter_ref
    return out


def assess_baseline_quality(
    *,
    baseline_id: str,
    dimensions: Mapping[str, Mapping[str, Any]],
    evidence_refs: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    normalized = {k: deepcopy(dict(v)) for k, v in sorted(dimensions.items())}
    states = [str(v.get("state", "NOT_ASSESSED")) for v in normalized.values()]
    if not states or all(x == "NOT_ASSESSED" for x in states):
        state = "NOT_ASSESSED"
    elif any(x == "INSUFFICIENT" for x in states):
        state = "INSUFFICIENT_BASELINE"
    elif all(x == "SUFFICIENT" for x in states):
        state = "BASELINE_ESTABLISHED"
    else:
        state = "BASELINE_PARTIAL"
    return {
        "baselineId": baseline_id,
        "state": state,
        "dimensions": normalized,
        "evidenceRefs": _refs(evidence_refs),
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }


def define_baseline(
    *,
    baseline_id: str,
    case_id: str,
    label: str,
    source_evidence_set_id: str,
    created_at: str,
    basis: str,
    artifact_digests: Iterable[str],
    source_coverage_ref: str,
    baseline_quality_ref: str,
    mapping_profile_digests: Iterable[str] = (),
    entity_inventory_digest: str | None = None,
    time_window: Mapping[str, Any] | None = None,
    schema_summary_digest: str | None = None,
    state_snapshot_digest: str | None = None,
    operation_surface_digest: str | None = None,
    relation_snapshot_digest: str | None = None,
    agent_tool_surface_digest: str | None = None,
    authority_snapshot_digest: str | None = None,
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    artifacts = _refs(artifact_digests)
    if not artifacts:
        raise ValueError("baseline requires at least one artifact digest")
    body = {
        "baselineId": baseline_id,
        "caseId": case_id,
        "label": label,
        "sourceEvidenceSetId": source_evidence_set_id,
        "createdAt": created_at,
        "basis": basis,
        "mappingProfileDigests": _refs(mapping_profile_digests),
        "artifactDigests": artifacts,
        "entityInventoryDigest": entity_inventory_digest,
        "sourceCoverageRef": source_coverage_ref,
        "timeWindow": deepcopy(dict(time_window)) if time_window is not None else None,
        "schemaSummaryDigest": schema_summary_digest,
        "stateSnapshotDigest": state_snapshot_digest,
        "operationSurfaceDigest": operation_surface_digest,
        "relationSnapshotDigest": relation_snapshot_digest,
        "agentToolSurfaceDigest": agent_tool_surface_digest,
        "authoritySnapshotDigest": authority_snapshot_digest,
        "baselineQualityRef": baseline_quality_ref,
        "frozen": True,
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }
    digest_payload = {k: v for k, v in body.items() if k != "baselineId"}
    return {**body, "baselineDigest": _stable_digest(digest_payload)}


def comparison_dimension(
    dimension: str,
    state: str,
    *,
    reason_codes: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "state": state,
        "reasonCodes": _refs(reason_codes),
        "evidenceRefs": _refs(evidence_refs),
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }


def build_comparison_compatibility(
    *,
    comparison_id: str,
    baseline_id: str,
    candidate_evidence_set_id: str,
    dimensions: Sequence[Mapping[str, Any]],
    evidence_refs: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    dims = [deepcopy(dict(x)) for x in dimensions]
    states = [str(x.get("state", "UNKNOWN")) for x in dims]
    if any(x == "INCOMPATIBLE" for x in states):
        overall, eligibility = "INCOMPATIBLE", "INELIGIBLE"
    elif any(x == "UNKNOWN" for x in states):
        overall, eligibility = "UNKNOWN", "LIMITED"
    elif any(x == "LIMITED" for x in states):
        overall, eligibility = "LIMITED", "LIMITED"
    elif any(x == "COMPATIBLE" for x in states):
        overall, eligibility = "COMPATIBLE", "ELIGIBLE"
    else:
        overall, eligibility = "EXACT", "ELIGIBLE"
    return {
        "comparisonId": comparison_id,
        "baselineId": baseline_id,
        "candidateEvidenceSetId": candidate_evidence_set_id,
        "overallState": overall,
        "driftComparisonEligibility": eligibility,
        "dimensions": dims,
        "evidenceRefs": _refs(evidence_refs),
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }


def observed_ref_delta(
    baseline_refs: Iterable[str],
    candidate_refs: Iterable[str],
) -> dict[str, Any]:
    before, after = set(_refs(baseline_refs)), set(_refs(candidate_refs))
    removed = sorted(before - after)
    added = sorted(after - before)
    limitations = ["REMOVED_FROM_OBSERVED_SET_NE_PROVEN_ABSENCE"] if removed else []
    return {"addedRefs": added, "removedRefs": removed, "limitations": limitations}
