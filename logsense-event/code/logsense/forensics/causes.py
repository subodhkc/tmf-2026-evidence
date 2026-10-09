from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from logsense.contracts.semantic_validation import (
    validate_cause_candidate_semantics,
    validate_cause_evaluation_semantics,
)


@dataclass(frozen=True)
class CauseRuleEvaluation:
    evaluation: dict[str, Any]
    semantic_errors: tuple[str, ...]


def _load_rule_pack() -> dict[str, Any]:
    payload = files("logsense.contracts").joinpath("rules/cause-rules-v0.1.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(payload)
    return data


def _rule_by_id() -> dict[str, dict[str, Any]]:
    return {str(rule["ruleId"]): rule for rule in _load_rule_pack()["rules"]}


def predicate_fact(
    *,
    state: str,
    evidence_refs: Sequence[str] = (),
    gap_refs: Sequence[str] = (),
    detail: str | None = None,
) -> dict[str, Any]:
    if state not in {"SATISFIED", "MISSING", "CONTRADICTED", "NOT_EVALUATED"}:
        raise ValueError(f"unsupported predicate state: {state}")
    return {
        "state": state,
        "evidenceRefs": list(evidence_refs),
        "gapRefs": list(gap_refs),
        "detail": detail,
    }


def _predicate_specs(rule: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("requiredPredicates", "anyOfPredicates", "forbiddenPredicates", "corroborators"):
        out.extend(rule.get(key, []))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for spec in out:
        pid = str(spec["predicateId"])
        if pid in seen:
            continue
        seen.add(pid)
        unique.append(spec)
    return unique


def _result_rows(
    rule: Mapping[str, Any],
    facts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    required_ids = {str(x["predicateId"]) for x in rule.get("requiredPredicates", [])}
    rows: list[dict[str, Any]] = []
    for spec in _predicate_specs(rule):
        pid = str(spec["predicateId"])
        fact = facts.get(pid)
        if fact is None:
            state = "MISSING" if pid in required_ids else "NOT_EVALUATED"
            fact = predicate_fact(state=state)
        rows.append({
            "predicateId": pid,
            "state": str(fact["state"]),
            "evidenceRefs": list(fact.get("evidenceRefs", [])),
            "gapRefs": list(fact.get("gapRefs", [])),
            "detail": fact.get("detail"),
        })
    return rows


def _determine_state(
    rule: Mapping[str, Any],
    results: Mapping[str, str],
    *,
    independent_lineage_families: Sequence[str],
    identity_qualified: bool,
    ordering_qualified: bool,
) -> str:
    required = [str(x["predicateId"]) for x in rule.get("requiredPredicates", [])]
    any_of = [str(x["predicateId"]) for x in rule.get("anyOfPredicates", [])]
    forbidden = [str(x["predicateId"]) for x in rule.get("forbiddenPredicates", [])]

    if any(results.get(pid) == "CONTRADICTED" for pid in required):
        return "CONTRADICTED"
    if any(results.get(pid) == "SATISFIED" for pid in forbidden):
        return "CONTRADICTED"

    all_required = all(results.get(pid) == "SATISFIED" for pid in required)
    any_of_ok = not any_of or any(results.get(pid) == "SATISFIED" for pid in any_of)
    policy = rule.get("establishmentPolicy", {})

    if not all_required or not any_of_ok:
        non_signal = [
            str(p["predicateId"])
            for p in rule.get("requiredPredicates", [])
            if p.get("kind") != "DETECTION_SIGNAL"
        ]
        non_signal_satisfied = any(results.get(pid) == "SATISFIED" for pid in non_signal)
        signal_satisfied = any(
            results.get(str(p["predicateId"])) == "SATISFIED"
            for p in rule.get("requiredPredicates", [])
            if p.get("kind") == "DETECTION_SIGNAL"
        )
        if signal_satisfied and not non_signal_satisfied:
            return str(policy.get("detectionOnlyMaximumState", "POSSIBLE"))
        if any(results.get(pid) == "SATISFIED" for pid in required):
            return str(policy.get("missingMaterialPredicateMaximumState", "SUPPORTED_CANDIDATE"))
        return "INSUFFICIENT_EVIDENCE"

    if policy.get("requireQualifiedIdentity") and not identity_qualified:
        return "SUPPORTED_CANDIDATE"
    if policy.get("requireQualifiedOrdering") and not ordering_qualified:
        return "SUPPORTED_CANDIDATE"
    if policy.get("allowEstablished") is False:
        return "SUPPORTED_CANDIDATE"

    minimum = int(policy.get("corroboratedIndependentLineages", 2))
    if len(set(independent_lineage_families)) >= minimum:
        return "CORROBORATED"
    return "ESTABLISHED"


def evaluate_cause_rule(
    *,
    rule_id: str,
    evaluation_id: str,
    analysis_run_id: str,
    subject_refs: Sequence[str],
    action_group_refs: Sequence[str],
    predicate_facts: Mapping[str, Mapping[str, Any]],
    independent_lineage_families: Sequence[str] = (),
    identity_qualified: bool = False,
    ordering_qualified: bool = False,
    hard_negatives_checked: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> CauseRuleEvaluation:
    rules = _rule_by_id()
    try:
        rule = rules[rule_id]
    except KeyError as exc:
        raise KeyError(f"unknown cause rule: {rule_id}") from exc
    if not rule.get("enabled", True):
        raise ValueError(f"cause rule is disabled: {rule_id}")

    rows = _result_rows(rule, predicate_facts)
    states = {str(x["predicateId"]): str(x["state"]) for x in rows}
    result_state = _determine_state(
        rule,
        states,
        independent_lineage_families=independent_lineage_families,
        identity_qualified=identity_qualified,
        ordering_qualified=ordering_qualified,
    )

    evidence_refs: list[str] = []
    gap_refs: list[str] = []
    satisfied: list[str] = []
    missing: list[str] = []
    for row in rows:
        if row["state"] == "SATISFIED":
            satisfied.append(str(row["predicateId"]))
        elif str(row["predicateId"]) in {str(x["predicateId"]) for x in rule.get("requiredPredicates", [])}:
            missing.append(str(row["predicateId"]))
        for ref in row.get("evidenceRefs", []):
            if ref not in evidence_refs:
                evidence_refs.append(str(ref))
        for ref in row.get("gapRefs", []):
            if ref not in gap_refs:
                gap_refs.append(str(ref))

    cause_id = f"{evaluation_id}:candidate"
    candidate = {
        "causeId": cause_id,
        "causeFamily": str(rule["causeFamily"]),
        "causeMechanism": str(rule["causeMechanism"]),
        "causeRole": str(rule["defaultCauseRole"]),
        "establishmentState": result_state,
        "subjectRefs": list(subject_refs),
        "actionGroupRefs": list(action_group_refs),
        "evidenceRefs": evidence_refs,
        "independentLineageFamilies": list(dict.fromkeys(independent_lineage_families)),
        "mechanismPathRef": None,
        "requiredPredicatesSatisfied": satisfied,
        "missingPredicates": missing,
        "hardNegativesChecked": list(hard_negatives_checked),
        "alternativeCauseRefs": list(rule.get("alternativeMechanisms", [])),
        "remediationRefs": list(rule.get("remediationRefs", [])),
        "verificationRequirementRefs": [],
        "limitations": list(limitations) + (["PREDICATE_GAPS_PRESENT"] if gap_refs else []),
        "generatedBy": "DETERMINISTIC_RULE",
        "canonical": False,
    }
    evaluation = {
        "evaluationId": evaluation_id,
        "ruleId": rule_id,
        "subjectRefs": list(subject_refs),
        "actionGroupRefs": list(action_group_refs),
        "predicateResults": rows,
        "hardNegativesChecked": list(hard_negatives_checked),
        "alternativeMechanismsConsidered": list(rule.get("alternativeMechanisms", [])),
        "resultState": result_state,
        "candidate": candidate,
        "limitations": list(limitations),
        "analysisRunId": analysis_run_id,
        "evaluationVersion": str(rule["version"]),
    }
    errors = [
        *validate_cause_candidate_semantics(candidate),
        *validate_cause_evaluation_semantics(evaluation, rules),
    ]
    return CauseRuleEvaluation(evaluation=evaluation, semantic_errors=tuple(errors))


def facts_policy_deny_not_enforced(
    *,
    lifecycle: Mapping[str, Any],
    action_identity_state: str,
) -> dict[str, dict[str, Any]]:
    auth = lifecycle["actionAuthorized"]
    applied = lifecycle["actionApplied"]
    confirmed = lifecycle["actionConfirmed"]
    return {
        "policy-deny": predicate_fact(
            state="SATISFIED" if auth.get("state") == "CONTRADICTED" else "MISSING",
            evidence_refs=auth.get("evidenceRefs", []),
            detail="Exact action has explicit deny evidence" if auth.get("state") == "CONTRADICTED" else None,
        ),
        "action-applied": predicate_fact(
            state="SATISFIED" if applied.get("state") == "PRESENT" else "MISSING",
            evidence_refs=applied.get("evidenceRefs", []),
        ),
        "exact-action": predicate_fact(
            state="SATISFIED" if action_identity_state == "EXACT" else "MISSING",
        ),
        "effect-confirmed": predicate_fact(
            state="SATISFIED" if confirmed.get("state") == "PRESENT" else "NOT_EVALUATED",
            evidence_refs=confirmed.get("evidenceRefs", []),
        ),
    }


def facts_wrong_resource_mutation(
    *,
    expected_target_ref: str | None,
    observed_target_ref: str | None,
    expected_identity_state: str,
    observed_identity_state: str,
    lifecycle: Mapping[str, Any],
    evidence_refs: Sequence[str],
) -> dict[str, dict[str, Any]]:
    exact = expected_identity_state == "EXACT" and observed_identity_state == "EXACT"
    changed = bool(expected_target_ref and observed_target_ref and expected_target_ref != observed_target_ref)
    applied = lifecycle["actionApplied"].get("state") == "PRESENT"
    return {
        "target-delta": predicate_fact(
            state="SATISFIED" if changed else "MISSING",
            evidence_refs=evidence_refs,
            detail="Exact expected and observed targets differ" if changed else None,
        ),
        "exact-targets": predicate_fact(
            state="SATISFIED" if exact else "MISSING",
            evidence_refs=evidence_refs if exact else (),
        ),
        "action-bind": predicate_fact(
            state="SATISFIED" if applied else "MISSING",
            evidence_refs=lifecycle["actionApplied"].get("evidenceRefs", []),
        ),
    }


def facts_cross_tenant_scope(
    *,
    actor_tenant_id: str | None,
    resource_tenant_id: str | None,
    tenant_identity_exact: bool,
    access_evidence_refs: Sequence[str],
    signal_evidence_refs: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    cross_tenant = bool(
        tenant_identity_exact
        and actor_tenant_id
        and resource_tenant_id
        and actor_tenant_id != resource_tenant_id
    )
    return {
        "cross-tenant-signal": predicate_fact(
            state="SATISFIED" if signal_evidence_refs else "MISSING",
            evidence_refs=signal_evidence_refs,
        ),
        "tenant-exact": predicate_fact(
            state="SATISFIED" if cross_tenant else "MISSING",
            evidence_refs=access_evidence_refs if cross_tenant else (),
        ),
        "access-observed": predicate_fact(
            state="SATISFIED" if access_evidence_refs else "MISSING",
            evidence_refs=access_evidence_refs,
        ),
    }
