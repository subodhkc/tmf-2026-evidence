from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from typing import Any


def _gap(
    *,
    gap_id: str,
    gap_type: str,
    why: str,
    evidence_set_id: str | None,
    subject_refs: Sequence[str],
    action_group_refs: Sequence[str],
    blocks: Sequence[str],
    acceptable_evidence: Sequence[str],
    evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "gapId": gap_id,
        "gapType": gap_type,
        "evidenceSetId": evidence_set_id,
        "comparisonId": None,
        "subjectRefs": list(subject_refs),
        "actionGroupRefs": list(action_group_refs),
        "blocks": list(blocks),
        "whyItMatters": why,
        "acceptableEvidence": list(acceptable_evidence),
        "evidenceRefs": list(evidence_refs),
        "status": "OPEN",
        "limitations": list(limitations),
    }


def coverage_gaps(
    *,
    action_group_ref: str,
    evidence_set_id: str,
    subject_refs: Sequence[str],
    lifecycle: Mapping[str, Any],
    five_plane: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Project evidence gaps without converting UNKNOWN/MISSING into failure."""
    gaps: list[dict[str, Any]] = []

    def absent(cell: Mapping[str, Any]) -> bool:
        return cell.get("state") in {"UNKNOWN", "MISSING", "PARTIAL"}

    if absent(five_plane["effectivelyGranted"]):
        gaps.append(_gap(
            gap_id=f"{action_group_ref}:gap:effective-grant",
            gap_type="EFFECTIVE_GRANT_MISSING",
            why="Effective credential/IAM grant evidence is insufficient.",
            evidence_set_id=evidence_set_id,
            subject_refs=subject_refs,
            action_group_refs=[action_group_ref],
            blocks=["EFFECTIVE_GRANT"],
            acceptable_evidence=["effective IAM grant", "credential scope record", "runtime authorization binding"],
        ))
    if absent(five_plane["codeCapable"]):
        gaps.append(_gap(
            gap_id=f"{action_group_ref}:gap:code-capability",
            gap_type="CODE_CAPABILITY_MISSING",
            why="Static or executable code-capability evidence is insufficient.",
            evidence_set_id=evidence_set_id,
            subject_refs=subject_refs,
            action_group_refs=[action_group_ref],
            blocks=["CODE_CAPABLE"],
            acceptable_evidence=["static code path", "capability manifest", "executable reachability proof"],
        ))
    if absent(lifecycle["actionApplied"]):
        gaps.append(_gap(
            gap_id=f"{action_group_ref}:gap:execution",
            gap_type="EXECUTION_EVIDENCE_MISSING",
            why="Accepted/request evidence does not establish action application.",
            evidence_set_id=evidence_set_id,
            subject_refs=subject_refs,
            action_group_refs=[action_group_ref],
            blocks=["ACTION_APPLIED"],
            acceptable_evidence=["platform execution record", "service-native audit event", "bound operation-state evidence"],
        ))
    if absent(lifecycle["actionConfirmed"]):
        gaps.append(_gap(
            gap_id=f"{action_group_ref}:gap:effect-confirmation",
            gap_type="EFFECT_CONFIRMATION_MISSING",
            why="A bound post-state/effect confirmation is not established.",
            evidence_set_id=evidence_set_id,
            subject_refs=subject_refs,
            action_group_refs=[action_group_ref],
            blocks=["ACTION_CONFIRMED"],
            acceptable_evidence=["bound StateTransition", "independent authoritative state observation"],
        ))
    return tuple(gaps)


def cause_evaluation_gaps(
    evaluation: Mapping[str, Any],
    *,
    evidence_set_id: str | None,
) -> tuple[dict[str, Any], ...]:
    """Translate explicit missing cause predicates into rule-declared GapFindings."""
    payload = files("logsense.contracts").joinpath("rules/cause-rules-v0.1.json").read_text(encoding="utf-8")
    rules = {str(x["ruleId"]): x for x in json.loads(payload)["rules"]}
    rule = rules.get(str(evaluation["ruleId"]))
    if rule is None:
        raise KeyError(f"unknown cause rule: {evaluation['ruleId']}")
    missing = [
        str(row["predicateId"])
        for row in evaluation.get("predicateResults", [])
        if row.get("state") in {"MISSING", "NOT_EVALUATED"}
        and str(row["predicateId"]) in {str(x["predicateId"]) for x in rule.get("requiredPredicates", [])}
    ]
    if not missing:
        return ()
    gap_types = list(rule.get("gapTypes", [])) or ["CAUSE_MECHANISM_INCOMPLETE"]
    gaps: list[dict[str, Any]] = []
    for idx, gap_type in enumerate(gap_types, start=1):
        gaps.append(_gap(
            gap_id=f"{evaluation['evaluationId']}:gap:{idx}",
            gap_type=str(gap_type),
            why=f"Cause rule {evaluation['ruleId']} is missing material predicate evidence: {', '.join(missing)}.",
            evidence_set_id=evidence_set_id,
            subject_refs=evaluation.get("subjectRefs", []),
            action_group_refs=evaluation.get("actionGroupRefs", []),
            blocks=["CAUSE_ESTABLISHMENT"],
            acceptable_evidence=[f"evidence satisfying predicate {pid}" for pid in missing],
            limitations=["MISSING_EVIDENCE_NE_NEGATIVE_FACT"],
        ))
    return tuple(gaps)


def action_status_contradiction(
    *,
    contradiction_id: str,
    analysis_run_id: str,
    subject_refs: Sequence[str],
    action_group_ref: str,
    lifecycle: Mapping[str, Any],
) -> dict[str, Any] | None:
    auth = lifecycle["actionAuthorized"]
    applied = lifecycle["actionApplied"]
    if auth.get("state") != "CONTRADICTED" or applied.get("state") != "PRESENT":
        return None
    refs = list(dict.fromkeys([*auth.get("evidenceRefs", []), *applied.get("evidenceRefs", [])]))
    return {
        "contradictionId": contradiction_id,
        "analysisRunId": analysis_run_id,
        "class": "ACTION_STATUS_CONTRADICTION",
        "subjectRefs": list(subject_refs),
        "claimScope": f"authorization contradiction vs applied action for {action_group_ref}",
        "comparabilityBasis": ["EXACT_ACTION_GROUP", "SAME_ACTION_SCOPE"],
        "evidenceRefs": refs,
        "state": "ESTABLISHED",
        "limitations": [],
        "rootCauseClaimed": False,
    }



def source_authority_contradiction(
    *,
    contradiction_id: str,
    analysis_run_id: str,
    subject_refs: Sequence[str],
    claim_scope: str,
    left_value_digest: str | None,
    right_value_digest: str | None,
    left_evidence_refs: Sequence[str],
    right_evidence_refs: Sequence[str],
    left_lineage_family: str | None,
    right_lineage_family: str | None,
    exact_subject_binding: bool,
    same_property: bool,
) -> dict[str, Any] | None:
    """Evaluate an evidence-bound source disagreement without calling it tampering.

    Establishment requires exact subject/property comparability and distinct,
    explicit evidence lineages. Same-lineage disagreement remains partial.
    Missing comparability remains unknown. Equal values are not a contradiction.
    """
    if (
        left_value_digest not in (None, "")
        and right_value_digest not in (None, "")
        and left_value_digest == right_value_digest
    ):
        return None

    refs = list(dict.fromkeys([*left_evidence_refs, *right_evidence_refs]))
    basis: list[str] = []
    limitations: list[str] = ["SOURCE_CONTRADICTION_NE_EVIDENCE_TAMPERING", "CONTRADICTION_NE_ROOT_CAUSE"]

    if exact_subject_binding:
        basis.append("EXACT_SUBJECT_BINDING")
    else:
        limitations.append("EXACT_SUBJECT_BINDING_REQUIRED")

    if same_property:
        basis.append("SAME_PROPERTY")
    else:
        limitations.append("SAME_PROPERTY_REQUIRED")

    values_present = left_value_digest not in (None, "") and right_value_digest not in (None, "")
    if not values_present:
        limitations.append("COMPARABLE_VALUES_REQUIRED")

    independent = (
        left_lineage_family not in (None, "")
        and right_lineage_family not in (None, "")
        and left_lineage_family != right_lineage_family
    )
    if independent:
        basis.append("INDEPENDENT_SOURCE_LINEAGES")
    elif left_lineage_family in (None, "") or right_lineage_family in (None, ""):
        limitations.append("SOURCE_LINEAGE_UNRESOLVED")
    else:
        limitations.append("SAME_LINEAGE_NE_INDEPENDENT_CORROBORATION")

    if not values_present or not exact_subject_binding or not same_property:
        state = "UNKNOWN"
    elif independent:
        state = "ESTABLISHED"
    else:
        state = "PARTIAL"

    return {
        "contradictionId": contradiction_id,
        "analysisRunId": analysis_run_id,
        "class": "SOURCE_AUTHORITY_CONTRADICTION",
        "subjectRefs": list(subject_refs),
        "claimScope": claim_scope,
        "comparabilityBasis": basis,
        "evidenceRefs": refs,
        "state": state,
        "limitations": sorted(set(limitations)),
        "rootCauseClaimed": False,
    }


def divergence(
    *,
    divergence_id: str,
    analysis_run_id: str,
    divergence_type: str,
    dimension: str,
    subject_refs: Sequence[str],
    action_group_refs: Sequence[str],
    evidence_refs: Sequence[str],
    ordering_basis: str,
    comparison_id: str | None = None,
    baseline_ref: str | None = None,
    candidate_ref: str | None = None,
    gap_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "divergenceId": divergence_id,
        "analysisRunId": analysis_run_id,
        "comparisonId": comparison_id,
        "type": divergence_type,
        "dimension": dimension,
        "baselineRef": baseline_ref,
        "candidateRef": candidate_ref,
        "subjectRefs": list(subject_refs),
        "actionGroupRefs": list(action_group_refs),
        "orderingBasis": ordering_basis,
        "evidenceRefs": list(evidence_refs),
        "gapRefs": list(gap_refs),
        "limitations": list(limitations),
        "rootCauseClaimed": False,
    }


def forensic_test(
    *,
    test_id: str,
    title: str,
    hypothesis: str,
    expected_behavior: str,
    preconditions: Sequence[str],
    required_evidence: Sequence[str],
    execution_steps: Sequence[str],
    expected_observations: Sequence[str],
    failure_criteria: Sequence[str],
    inconclusive_criteria: Sequence[str],
    evidence_refs: Sequence[str],
    verification_target: str | None,
    executed: bool,
    required_evidence_complete: bool,
    observed_violation: bool | None,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Create a forensic test without equating missing evidence with FAIL."""
    if not executed:
        result = "NOT_RUN"
    elif not required_evidence_complete:
        result = "INCONCLUSIVE"
    elif observed_violation is True:
        result = "FAIL"
    elif observed_violation is False:
        result = "PASS"
    else:
        result = "INCONCLUSIVE"

    return {
        "testId": test_id,
        "title": title,
        "hypothesis": hypothesis,
        "expectedBehavior": expected_behavior,
        "preconditions": list(preconditions),
        "requiredEvidence": list(required_evidence),
        "executionSteps": list(execution_steps),
        "expectedObservations": list(expected_observations),
        "failureCriteria": list(failure_criteria),
        "inconclusiveCriteria": list(inconclusive_criteria),
        "result": result,
        "evidenceRefs": list(evidence_refs),
        "limitations": list(limitations),
        "verificationTarget": verification_target,
    }
