from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from logsense.forensics.frontier import record_frontier_closure

_ALLOWED_RESULTS = {"PASS", "FAIL", "INCONCLUSIVE"}
_ALLOWED_CLOSURE_BASIS = {"TEST_RESULT", "DOCUMENTED_NON_EXECUTION"}


class VerificationContractError(ValueError):
    """Raised when verification inputs would overstate forensic semantics."""


def _refs(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def build_forensic_test(
    *,
    test_id: str,
    title: str,
    hypothesis: str,
    expected_behavior: str,
    verification_target: str,
    result: str,
    preconditions: Sequence[str] = (),
    required_evidence: Sequence[str] = (),
    execution_steps: Sequence[str] = (),
    expected_observations: Sequence[str] = (),
    failure_criteria: Sequence[str] = (),
    inconclusive_criteria: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
    predicate_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the frozen deterministic ForensicTest read contract.

    A test result is bounded to its verification target and optional predicate
    scope. It never creates a root-cause conclusion or capability-absence fact.
    """
    normalized_result = str(result).upper()
    if normalized_result not in _ALLOWED_RESULTS:
        raise VerificationContractError(f"unsupported forensic test result: {result}")
    if not str(test_id) or not str(verification_target):
        raise VerificationContractError("testId and verificationTarget are required")
    if normalized_result == "PASS" and not evidence_refs:
        raise VerificationContractError("PASS requires qualified evidence references")
    return {
        "testId": str(test_id),
        "title": str(title),
        "hypothesis": str(hypothesis),
        "expectedBehavior": str(expected_behavior),
        "preconditions": _refs(preconditions),
        "requiredEvidence": _refs(required_evidence),
        "executionSteps": _refs(execution_steps),
        "expectedObservations": _refs(expected_observations),
        "failureCriteria": _refs(failure_criteria),
        "inconclusiveCriteria": _refs(inconclusive_criteria),
        "result": normalized_result,
        "evidenceRefs": _refs(evidence_refs),
        "limitations": _refs(limitations),
        "verificationTarget": str(verification_target),
        "predicateScope": dict(predicate_scope) if predicate_scope is not None else None,
        "rootCauseClaimed": False,
    }


def evaluate_frontier_closure(
    frontier: Mapping[str, Any],
    forensic_test: Mapping[str, Any],
    *,
    prior_snapshot_ref: str,
    new_snapshot_ref: str,
    closed_at: str,
    closure_basis: str = "TEST_RESULT",
    closure_reason: str | None = None,
    documented_non_execution_predicate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute exact frontier closure state and delegate record shape to frontier.py.

    PASS closes only the bounded frontier item. FAIL means qualified evidence
    contradicted the expected behavior. INCONCLUSIVE remains open. Documented
    non-execution is a separate bounded closure state and never means capability
    absence.
    """
    basis = str(closure_basis).upper()
    if basis not in _ALLOWED_CLOSURE_BASIS:
        raise VerificationContractError(f"unsupported closure basis: {closure_basis}")
    if not prior_snapshot_ref or not new_snapshot_ref:
        raise VerificationContractError("prior and new snapshot refs are required")
    if prior_snapshot_ref == new_snapshot_ref:
        raise VerificationContractError("verification must create a new immutable snapshot")

    frontier_id = str(frontier.get("frontierId") or "")
    if not frontier_id:
        raise VerificationContractError("frontierId is required")
    test_id = str(forensic_test.get("testId") or "")
    if not test_id:
        raise VerificationContractError("forensic test must have testId")
    target = str(forensic_test.get("verificationTarget") or "")
    subject_refs = {str(x) for x in frontier.get("subjectRefs", ()) if str(x)}
    if subject_refs and target not in subject_refs:
        raise VerificationContractError("forensic test verificationTarget is outside frontier subject scope")

    result = str(forensic_test.get("result") or "").upper()
    if result not in _ALLOWED_RESULTS:
        raise VerificationContractError(f"unsupported forensic test result: {result}")
    evidence_refs = _refs(forensic_test.get("evidenceRefs", ()))

    if basis == "DOCUMENTED_NON_EXECUTION":
        if result != "PASS":
            raise VerificationContractError("documented non-execution closure requires PASS")
        predicate = documented_non_execution_predicate or forensic_test.get("predicateScope")
        if not isinstance(predicate, Mapping) or not predicate:
            raise VerificationContractError("documented non-execution requires exact predicate scope")
        closure_state = "DOCUMENTED_NON_EXECUTION"
        reason = closure_reason or "Bounded non-execution predicate established by qualified test evidence."
        semantic_limits = ["DOCUMENTED_NON_EXECUTION_NE_CAPABILITY_ABSENT", "CLOSED_BY_TEST_NE_ROOT_CAUSE"]
    elif result == "PASS":
        if not evidence_refs:
            raise VerificationContractError("PASS closure requires evidenceRefs")
        closure_state = "CLOSED"
        reason = closure_reason or "Verification requirement satisfied by qualified test evidence."
        semantic_limits = ["CLOSED_BY_TEST_NE_ROOT_CAUSE"]
    elif result == "FAIL":
        if not evidence_refs:
            raise VerificationContractError("FAIL closure requires evidenceRefs")
        closure_state = "CONTRADICTED"
        reason = closure_reason or "Qualified test evidence contradicted the expected behavior."
        semantic_limits = ["CONTRADICTED_TEST_NE_ROOT_CAUSE"]
    else:
        closure_state = "STILL_OPEN"
        reason = closure_reason or "Verification remains inconclusive; required evidence is insufficient."
        semantic_limits = ["INCONCLUSIVE_TEST_NE_CLOSED_FRONTIER"]

    record = record_frontier_closure(
        frontier_id=frontier_id,
        prior_snapshot_ref=prior_snapshot_ref,
        new_snapshot_ref=new_snapshot_ref,
        closed_at=closed_at,
        closure_state=closure_state,
        evidence_refs=evidence_refs,
        closure_reason=reason,
        test_run_ref=test_id,
    )
    return {
        **record,
        "verificationTarget": target,
        "predicateScope": (
            dict(documented_non_execution_predicate or forensic_test.get("predicateScope") or {})
            if basis == "DOCUMENTED_NON_EXECUTION"
            else forensic_test.get("predicateScope")
        ),
        "semanticLimitations": semantic_limits,
        "rootCauseClaimed": False,
        "capabilityAbsentClaimed": False,
    }
