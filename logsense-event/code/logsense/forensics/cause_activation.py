from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from logsense.forensics.causes import (
    evaluate_cause_rule,
    facts_cross_tenant_scope,
    facts_policy_deny_not_enforced,
    facts_wrong_resource_mutation,
)

_SUPPORTED_RULES = frozenset({"CR-AUTH-001", "CR-STATE-003", "CR-DATA-001"})


@dataclass(frozen=True)
class CauseEvaluationInstruction:
    """Explicit bounded request to evaluate one already-frozen cause rule.

    The instruction never selects a rule heuristically. Callers must identify
    the rule/action and supply any evidence dimensions that are not canonical
    owners in the current analysis spine.
    """

    rule_id: str
    action_group_ref: str
    ordering_qualified: bool
    independent_lineage_families: tuple[str, ...] = ()
    hard_negatives_checked: tuple[str, ...] = ()
    expected_target_ref: str | None = None
    observed_target_ref: str | None = None
    observed_target_identity_state: str = "UNKNOWN"
    actor_tenant_id: str | None = None
    resource_tenant_id: str | None = None
    tenant_identity_exact: bool = False
    access_evidence_refs: tuple[str, ...] = ()
    signal_evidence_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


def _rules() -> dict[str, dict[str, Any]]:
    payload = files("logsense.contracts").joinpath("rules/cause-rules-v0.1.json").read_text(
        encoding="utf-8"
    )
    return {str(rule["ruleId"]): rule for rule in json.loads(payload)["rules"]}


def required_hard_negatives(rule_id: str) -> tuple[str, ...]:
    rule = _rules().get(rule_id)
    if rule is None:
        raise KeyError(f"unknown cause rule: {rule_id}")
    return tuple(str(x) for x in rule.get("hardNegatives", []))


def _validate_instruction(instruction: CauseEvaluationInstruction) -> None:
    if instruction.rule_id not in _SUPPORTED_RULES:
        raise ValueError(
            f"cause rule {instruction.rule_id!r} is not enabled for spine activation"
        )
    required = set(required_hard_negatives(instruction.rule_id))
    supplied = set(instruction.hard_negatives_checked)
    missing = sorted(required - supplied)
    if missing:
        raise ValueError(
            "explicit cause activation requires all frozen hard negatives: "
            + ", ".join(missing)
        )


def _subject_refs(action_group: Mapping[str, Any]) -> list[str]:
    identity = action_group.get("actionIdentity") or {}
    return [
        str(x)
        for x in (identity.get("actorRef"), identity.get("targetRef"))
        if x not in (None, "")
    ]


def evaluate_cause_instruction(
    instruction: CauseEvaluationInstruction,
    *,
    action_group: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    analysis_run_id: str,
    evaluation_id: str,
) -> dict[str, Any]:
    """Evaluate one caller-selected frozen cause rule from canonical owners.

    Ordering is never inferred here. Independent lineage families are never
    inferred from source count. Missing caller evidence degrades rule state
    through the frozen cause evaluator instead of inventing facts.
    """
    _validate_instruction(instruction)
    identity = action_group.get("actionIdentity") or {}
    identity_state = str(identity.get("identityState", "UNRESOLVED"))

    if str(action_group.get("actionGroupId")) != instruction.action_group_ref:
        raise ValueError("cause instruction action reference does not match action group")

    if instruction.rule_id == "CR-AUTH-001":
        facts = facts_policy_deny_not_enforced(
            lifecycle=lifecycle,
            action_identity_state=identity_state,
        )
        identity_qualified = identity_state == "EXACT"

    elif instruction.rule_id == "CR-STATE-003":
        expected_target = instruction.expected_target_ref or identity.get("targetRef")
        if instruction.observed_target_ref is None:
            raise ValueError("wrong-resource evaluation requires observed_target_ref")
        facts = facts_wrong_resource_mutation(
            expected_target_ref=str(expected_target) if expected_target is not None else None,
            observed_target_ref=instruction.observed_target_ref,
            expected_identity_state=identity_state,
            observed_identity_state=instruction.observed_target_identity_state,
            lifecycle=lifecycle,
            evidence_refs=instruction.evidence_refs,
        )
        identity_qualified = (
            identity_state == "EXACT"
            and instruction.observed_target_identity_state == "EXACT"
        )

    else:
        if instruction.actor_tenant_id is None or instruction.resource_tenant_id is None:
            raise ValueError(
                "cross-tenant evaluation requires actor_tenant_id and resource_tenant_id"
            )
        facts = facts_cross_tenant_scope(
            actor_tenant_id=instruction.actor_tenant_id,
            resource_tenant_id=instruction.resource_tenant_id,
            tenant_identity_exact=instruction.tenant_identity_exact,
            access_evidence_refs=instruction.access_evidence_refs,
            signal_evidence_refs=instruction.signal_evidence_refs,
        )
        identity_qualified = identity_state == "EXACT" and instruction.tenant_identity_exact

    result = evaluate_cause_rule(
        rule_id=instruction.rule_id,
        evaluation_id=evaluation_id,
        analysis_run_id=analysis_run_id,
        subject_refs=_subject_refs(action_group),
        action_group_refs=[instruction.action_group_ref],
        predicate_facts=facts,
        independent_lineage_families=instruction.independent_lineage_families,
        identity_qualified=identity_qualified,
        ordering_qualified=instruction.ordering_qualified,
        hard_negatives_checked=instruction.hard_negatives_checked,
        limitations=("EXPLICIT_CAUSE_EVALUATION_INSTRUCTION",),
    )
    if result.semantic_errors:
        raise ValueError(
            "cause evaluation failed semantic validation: "
            + "; ".join(result.semantic_errors)
        )
    return result.evaluation
