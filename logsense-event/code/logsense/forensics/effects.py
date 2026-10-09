from __future__ import annotations

from collections.abc import Sequence
from numbers import Real
from typing import Any


def _numeric(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def assess_effect_envelope(
    *,
    assessment_id: str,
    envelope_ref: str,
    bound_ref: str,
    bound_provenance_ref: str,
    principal_ref: str,
    canonical_operation: str,
    target_key: str,
    target_id: str,
    property_name: str,
    direction: str,
    expected_limit: Any,
    observed_delta: Any,
    transition_ref: str,
    authority_established: bool,
    evidence_refs: Sequence[str],
    exact_target_identity: bool = True,
    property_comparable: bool = True,
    transition_bound: bool = True,
    envelope_version: str | None = None,
    envelope_digest: str | None = None,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Evaluate an explicit effect bound without promoting exceedance to cause."""
    out_limits = {str(x) for x in limitations if str(x)}

    if not exact_target_identity:
        state = "NOT_COMPARABLE"
        reason = "TARGET_IDENTITY_NOT_EXACT"
        out_limits.add("SAME_DISPLAY_NAME_NE_SAME_TARGET")
    elif not property_comparable:
        state = "NOT_COMPARABLE"
        reason = "PROPERTY_NOT_COMPARABLE"
    elif not _numeric(expected_limit) or not _numeric(observed_delta):
        state = "NOT_COMPARABLE"
        reason = "NON_NUMERIC_BOUND_OR_DELTA"
    elif not transition_bound:
        state = "NOT_ASSESSED"
        reason = "TRANSITION_NOT_BOUND_TO_ACTION"
        out_limits.add("OBSERVED_DELTA_NE_EFFECT_CAUSED_BY_ACTION")
    elif not authority_established:
        state = "NOT_ASSESSED"
        reason = "AUTHORITY_NOT_ESTABLISHED"
    else:
        limit = abs(float(expected_limit))
        delta = float(observed_delta)
        normalized_direction = direction.lower()
        if normalized_direction == "increase":
            exceeded = delta > limit
        elif normalized_direction == "decrease":
            exceeded = delta < -limit
        else:
            exceeded = abs(delta) > limit
        state = "EXCEEDED" if exceeded else "WITHIN_ENVELOPE"
        reason = "OBSERVED_DELTA_EXCEEDS_BOUND" if exceeded else "OBSERVED_DELTA_WITHIN_BOUND"

    return {
        "assessmentId": assessment_id,
        "envelopeRef": envelope_ref,
        "boundRef": bound_ref,
        "boundProvenanceRef": bound_provenance_ref,
        "principalRef": principal_ref,
        "canonicalOperation": canonical_operation,
        "targetKey": target_key,
        "targetId": target_id,
        "property": property_name,
        "direction": direction,
        "expectedLimit": expected_limit,
        "observedDelta": observed_delta,
        "transitionRef": transition_ref,
        "authorityEstablished": authority_established,
        "state": state,
        "reasonCode": reason,
        "evidenceRefs": list(evidence_refs),
        "limitations": sorted(out_limits),
        "envelopeVersion": envelope_version,
        "envelopeDigest": envelope_digest,
    }
