from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from logsense.contracts.semantic_validation import validate_scenario_sequence_semantics
from logsense.forensics.findings import divergence


@dataclass(frozen=True)
class ScenarioStateFingerprint:
    evidence_set_id: str
    scenario_level: str
    scenario_sequence: int
    analysis_perimeter_ref: str
    evidence_fingerprint: str | None
    behavioral_fingerprint: str | None
    integrity_fingerprint: str | None
    subject_refs: tuple[str, ...] = ()
    action_group_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


def build_scenario_sequence(
    states: Sequence[ScenarioStateFingerprint],
    *,
    case_id: str,
    scenario_run_id: str,
    sequence_id: str | None = None,
) -> dict[str, Any]:
    ordered = sorted(states, key=lambda x: x.scenario_sequence)
    sequence = {
        "sequenceId": sequence_id or f"{scenario_run_id}:sequence",
        "caseId": case_id,
        "scenarioRunId": scenario_run_id,
        "states": [
            {
                "evidenceSetId": state.evidence_set_id,
                "scenarioLevel": state.scenario_level,
                "scenarioSequence": state.scenario_sequence,
            }
            for state in ordered
        ],
        "orderingBasis": "EXPLICIT",
        "limitations": [],
    }
    errors = validate_scenario_sequence_semantics(sequence)
    if errors:
        raise ValueError(";".join(errors))
    return sequence


def _first_changed_boundary(
    states: Sequence[ScenarioStateFingerprint],
    attribute: str,
) -> tuple[ScenarioStateFingerprint, ScenarioStateFingerprint] | None:
    ordered = sorted(states, key=lambda x: x.scenario_sequence)
    for left, right in zip(ordered, ordered[1:], strict=False):
        before = getattr(left, attribute)
        after = getattr(right, attribute)
        if before in (None, "") or after in (None, ""):
            continue
        if before != after:
            return left, right
    return None


def _refs(*values: Sequence[str]) -> list[str]:
    return sorted({str(v) for seq in values for v in seq if str(v)})


def reconstruct_divergence_triad(
    states: Sequence[ScenarioStateFingerprint],
    *,
    case_id: str,
    scenario_run_id: str,
    analysis_run_id: str,
) -> dict[str, Any]:
    """Reconstruct first evidence/behavior/integrity divergence boundaries.

    This is a comparison projection, not root-cause evaluation. Scenario order
    must be explicit and all states must share one analysis perimeter. Missing
    fingerprints remain missing; they are never converted into "no divergence".
    """
    if len(states) < 2:
        raise ValueError("scenario divergence reconstruction requires at least two states")

    sequence = build_scenario_sequence(
        states,
        case_id=case_id,
        scenario_run_id=scenario_run_id,
    )
    ordered = sorted(states, key=lambda x: x.scenario_sequence)
    limitations: set[str] = {"DIVERGENCE_ORDER_NE_ROOT_CAUSE"}

    perimeter_refs = {state.analysis_perimeter_ref for state in ordered if state.analysis_perimeter_ref}
    if len(perimeter_refs) != 1 or any(not state.analysis_perimeter_ref for state in ordered):
        limitations.add("ANALYSIS_PERIMETER_CHANGED_NE_SYSTEM_DRIFT")
        return {
            "scenarioSequence": sequence,
            "firstEvidenceDivergence": None,
            "firstBehavioralDivergence": None,
            "firstIntegrityContradiction": None,
            "limitations": sorted(limitations),
        }

    specs = (
        (
            "evidence_fingerprint",
            "EVIDENCE_DIVERGENCE",
            "evidence_membership_or_coverage",
            "firstEvidenceDivergence",
            "EVIDENCE_FINGERPRINT_MISSING",
        ),
        (
            "behavioral_fingerprint",
            "BEHAVIORAL_DIVERGENCE",
            "observed_behavior",
            "firstBehavioralDivergence",
            "BEHAVIORAL_FINGERPRINT_MISSING",
        ),
        (
            "integrity_fingerprint",
            "INTEGRITY_CONTRADICTION",
            "evidence_integrity_or_source_contradiction",
            "firstIntegrityContradiction",
            "INTEGRITY_FINGERPRINT_MISSING",
        ),
    )

    result: dict[str, Any] = {"scenarioSequence": sequence}
    for attribute, kind, dimension, output_key, missing_code in specs:
        if any(getattr(state, attribute) in (None, "") for state in ordered):
            limitations.add(missing_code)
        boundary = _first_changed_boundary(ordered, attribute)
        if boundary is None:
            result[output_key] = None
            continue
        left, right = boundary
        result[output_key] = divergence(
            divergence_id=f"{analysis_run_id}:{kind.lower()}:{left.scenario_sequence}->{right.scenario_sequence}",
            analysis_run_id=analysis_run_id,
            divergence_type=kind,
            dimension=dimension,
            subject_refs=_refs(left.subject_refs, right.subject_refs),
            action_group_refs=_refs(left.action_group_refs, right.action_group_refs),
            evidence_refs=_refs(left.evidence_refs, right.evidence_refs),
            ordering_basis="EXPLICIT_SCENARIO_SEQUENCE",
            baseline_ref=left.evidence_set_id,
            candidate_ref=right.evidence_set_id,
            limitations=["DIVERGENCE_ORDER_NE_ROOT_CAUSE"],
        )

    result["limitations"] = sorted(limitations)
    return result
