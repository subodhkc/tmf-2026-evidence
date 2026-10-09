from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

_ALLOWED_DIMENSIONS = {
    "OPERATION",
    "TARGET",
    "RESOURCE_SCOPE",
    "TENANT_SCOPE",
    "MAGNITUDE",
    "DURATION",
    "APPROVAL",
    "DATA_CLASS",
    "ENVIRONMENT",
    "GEOGRAPHY",
    "CREDENTIAL_CONTEXT",
}
_PRECEDENCE = ("BROADER", "MISSING", "UNKNOWN", "NARROWER", "MATCHES")


def _as_set(value: Any) -> set[str] | None:
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(x) for x in value}
    return None


def _compare_value(delegated: Any, actual: Any, *, dimension: str) -> str:
    if delegated is None:
        return "MISSING"
    if actual is None:
        return "UNKNOWN"
    if dimension in {"MAGNITUDE", "DURATION"}:
        if (
            isinstance(delegated, Real)
            and not isinstance(delegated, bool)
            and isinstance(actual, Real)
            and not isinstance(actual, bool)
        ):
            d = abs(float(delegated))
            a = abs(float(actual))
            if a == d:
                return "MATCHES"
            return "BROADER" if a > d else "NARROWER"
        return "UNKNOWN"

    delegated_set = _as_set(delegated)
    actual_set = _as_set(actual)
    if delegated_set is not None:
        if actual_set is None:
            actual_set = {str(actual)}
        if actual_set == delegated_set:
            return "MATCHES"
        if actual_set.issubset(delegated_set):
            return "NARROWER"
        return "BROADER"

    if isinstance(delegated, Mapping) or isinstance(actual, Mapping):
        return "MATCHES" if delegated == actual else "UNKNOWN"

    return "MATCHES" if str(delegated) == str(actual) else "BROADER"


def _dimension_comparison(
    *,
    dimension: str,
    delegated_value: Any,
    code_capable_value: Any,
    effectively_granted_value: Any,
    observed_value: Any,
) -> tuple[str, list[str]]:
    limitations: list[str] = []
    if delegated_value is None:
        return "MISSING", ["DELEGATED_VALUE_MISSING"]

    comparisons: list[str] = []
    for label, value in (
        ("CODE_CAPABLE", code_capable_value),
        ("EFFECTIVELY_GRANTED", effectively_granted_value),
        ("OBSERVED", observed_value),
    ):
        state = _compare_value(delegated_value, value, dimension=dimension)
        comparisons.append(state)
        if state == "UNKNOWN":
            limitations.append(f"{label}_COMPARISON_UNKNOWN")

    for state in _PRECEDENCE:
        if state in comparisons:
            return state, limitations
    return "UNKNOWN", limitations


def evaluate_delegated_action_integrity(
    *,
    evaluation_id: str,
    action_group_ref: str,
    dimensions: Sequence[Mapping[str, Any]],
    evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Compare delegated authority with capability/grant/observed action facts.

    A value outside an explicit delegated scalar/set is treated as BROADER.
    Missing or structurally incomparable values remain MISSING/UNKNOWN. This
    evaluator does not infer delegation from handoff, context transfer, or
    runtime correlation.
    """
    rows: list[dict[str, Any]] = []
    overall_candidates: list[str] = []
    all_evidence = list(dict.fromkeys(str(x) for x in evidence_refs))

    for item in dimensions:
        dimension = str(item["dimension"])
        if dimension not in _ALLOWED_DIMENSIONS:
            raise ValueError(f"unsupported DAI dimension: {dimension}")

        comparison, derived_limits = _dimension_comparison(
            dimension=dimension,
            delegated_value=item.get("delegatedValue"),
            code_capable_value=item.get("codeCapableValue"),
            effectively_granted_value=item.get("effectivelyGrantedValue"),
            observed_value=item.get("observedValue"),
        )
        row_evidence = list(dict.fromkeys(str(x) for x in item.get("evidenceRefs", [])))
        for ref in row_evidence:
            if ref not in all_evidence:
                all_evidence.append(ref)
        row_limits = list(dict.fromkeys([
            *(str(x) for x in item.get("limitations", [])),
            *derived_limits,
        ]))
        rows.append({
            "dimension": dimension,
            "delegatedValue": item.get("delegatedValue"),
            "codeCapableValue": item.get("codeCapableValue"),
            "effectivelyGrantedValue": item.get("effectivelyGrantedValue"),
            "observedValue": item.get("observedValue"),
            "comparison": comparison,
            "mediationEvidenceRefs": list(dict.fromkeys(
                str(x) for x in item.get("mediationEvidenceRefs", [])
            )),
            "evidenceRefs": row_evidence,
            "limitations": row_limits,
            "pendingBusinessRule": item.get("pendingBusinessRule"),
        })
        overall_candidates.append(comparison)

    overall = "MATCHES"
    for state in _PRECEDENCE:
        if state in overall_candidates:
            overall = state
            break

    return {
        "evaluationId": evaluation_id,
        "actionGroupRef": action_group_ref,
        "dimensions": rows,
        "overallState": overall,
        "evidenceRefs": all_evidence,
        "limitations": list(dict.fromkeys(str(x) for x in limitations)),
    }
