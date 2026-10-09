from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from logsense.contracts.semantic_validation import validate_relation_evaluation_semantics


@dataclass(frozen=True)
class RelationAdmissionResult:
    evaluation: dict[str, Any]
    semantic_errors: tuple[str, ...]


def _load_matrix() -> dict[str, Any]:
    payload = files("logsense.contracts").joinpath("rules/relation-admission-matrix-v0.1.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(payload)
    return data


def _entry_by_type() -> dict[str, dict[str, Any]]:
    matrix = _load_matrix()
    return {str(x["relationType"]): x for x in matrix["entries"]}


def evaluate_relation(
    *,
    evaluation_id: str,
    analysis_run_id: str,
    relation_type: str,
    source_ref: str,
    target_ref: str,
    source_identity_state: str,
    target_identity_state: str,
    admission_basis: str,
    evidence_refs: Sequence[str],
    lineage_families: Sequence[str] = (),
    satisfied_conditions: Sequence[str] = (),
    hard_negatives_checked: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> RelationAdmissionResult:
    entries = _entry_by_type()
    try:
        entry = entries[relation_type]
    except KeyError as exc:
        raise KeyError(f"unknown relation type: {relation_type}") from exc

    required = set(entry.get("requiredConditions", []))
    satisfied = set(satisfied_conditions)
    forbidden = set(entry.get("forbiddenAdmissionBases", []))
    establishment_bases = set(entry.get("establishmentEvidenceBases", []))
    proposal_bases = set(entry.get("proposalEvidenceBases", []))

    exact_ok = True
    if entry.get("requiredSourceIdentityState") == "EXACT" and source_identity_state != "EXACT":
        exact_ok = False
    if entry.get("requiredTargetIdentityState") == "EXACT" and target_identity_state != "EXACT":
        exact_ok = False
    independent_ok = True
    if entry.get("requiresIndependentLineageForEstablishment"):
        independent_ok = len(set(lineage_families)) >= 2

    if admission_basis in forbidden:
        decision = "REJECTED"
    elif (
        admission_basis in establishment_bases
        and bool(evidence_refs)
        and required.issubset(satisfied)
        and exact_ok
        and independent_ok
    ):
        decision = "ESTABLISHED"
    elif admission_basis in establishment_bases | proposal_bases and evidence_refs:
        decision = "PARTIAL"
    else:
        decision = "UNKNOWN"

    missing = sorted(required - satisfied)
    evaluation = {
        "evaluationId": evaluation_id,
        "relationType": relation_type,
        "sourceRef": source_ref,
        "targetRef": target_ref,
        "sourceIdentityState": source_identity_state,
        "targetIdentityState": target_identity_state,
        "admissionBasis": admission_basis,
        "evidenceRefs": list(evidence_refs),
        "lineageFamilies": list(lineage_families),
        "satisfiedConditions": sorted(satisfied),
        "missingConditions": missing,
        "hardNegativesChecked": list(hard_negatives_checked),
        "decision": decision,
        "limitations": list(limitations),
        "analysisRunId": analysis_run_id,
        "evaluationVersion": str(_load_matrix()["version"]),
    }
    errors = validate_relation_evaluation_semantics(evaluation, entries)
    return RelationAdmissionResult(evaluation=evaluation, semantic_errors=tuple(errors))


def evaluate_changes_binding(
    *,
    evaluation_id: str,
    analysis_run_id: str,
    action_group: Mapping[str, Any],
    transition: Mapping[str, Any],
    target_identity_state: str,
    binding_evidence_refs: Sequence[str],
    lineage_families: Sequence[str] = (),
) -> RelationAdmissionResult:
    identity = action_group.get("actionIdentity") or {}
    actor_ref = identity.get("actorRef")
    target_ref = identity.get("targetRef") or identity.get("resourceScope")
    transition_target = transition.get("subjectRef")
    source_state = str(identity.get("identityState", "UNRESOLVED"))

    satisfied = ["EVIDENCE_REFS_PRESENT", "DIRECTION_PRESERVED", "SCENARIO_SCOPE_COMPATIBLE"]
    if target_ref and transition_target and target_ref == transition_target:
        satisfied.append("EXACT_SUBJECT_MATCH")
        if binding_evidence_refs:
            satisfied.append("QUALIFIED_OPERATION_STATE_BINDING")
    limitations: list[str] = []
    if target_ref != transition_target:
        limitations.append("ACTION_TARGET_NE_TRANSITION_SUBJECT")
    elif not binding_evidence_refs:
        limitations.append("QUALIFIED_OPERATION_STATE_BINDING_EVIDENCE_MISSING")

    evidence = list(dict.fromkeys([*action_group.get("eventRefs", []), *transition.get("evidenceRefs", []), *binding_evidence_refs]))
    return evaluate_relation(
        evaluation_id=evaluation_id,
        analysis_run_id=analysis_run_id,
        relation_type="CHANGES",
        source_ref=str(actor_ref or action_group["actionGroupId"]),
        target_ref=str(transition_target),
        source_identity_state=source_state,
        target_identity_state=target_identity_state,
        admission_basis="OPERATION_STATE_ATTRIBUTION_BOUND",
        evidence_refs=evidence,
        lineage_families=lineage_families,
        satisfied_conditions=satisfied,
        hard_negatives_checked=[
            "TIMESTAMP_PROXIMITY != RELATION",
            "CORRELATION_FACT != CAUSAL_RELATION",
            "TARGET_MATCH_ALONE != ATTRIBUTION",
            "HTTP_200 != ACTION_APPLIED",
        ],
        limitations=limitations,
    )


def bind_transition(
    transition: Mapping[str, Any],
    relation: Mapping[str, Any],
    *,
    operation_event_refs: Iterable[str],
) -> dict[str, Any]:
    if relation.get("relationType") != "CHANGES" or relation.get("decision") != "ESTABLISHED":
        raise ValueError("state transition can be bound only by an ESTABLISHED CHANGES relation")
    if str(relation.get("targetRef")) != str(transition.get("subjectRef")):
        raise ValueError("relation target does not match transition subject")
    out = dict(transition)
    out["operationAttributionState"] = "BOUND"
    out["operationEventRefs"] = list(operation_event_refs)
    out["relationEvaluationRefs"] = [str(relation["evaluationId"])]
    out["limitations"] = [x for x in out.get("limitations", []) if x != "OPERATION_ATTRIBUTION_REQUIRES_RELATION_ADMISSION"]
    return out
