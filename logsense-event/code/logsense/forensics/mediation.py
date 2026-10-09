from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime


def _parse_time(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("mediation timestamps must carry an explicit timezone")
    return parsed


def assess_guardrail_mediation(
    *,
    mediation_id: str,
    action_group_ref: str,
    guardrail_ref: str,
    requirement_declared: bool | None,
    confirmation_presented: bool | None,
    confirmation_completed: bool | None,
    decision: str,
    decision_time_ref: str | None,
    action_time_ref: str | None,
    decision_time: str | None,
    action_time: str | None,
    deny_branch_blocked_action: bool | None,
    approved_argument_digest: str | None,
    executed_argument_digest: str | None,
    mediation_evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict:
    """Project guardrail mediation without promoting presence to enforcement.

    Ordering is computed only when both qualified timestamps are supplied.
    Argument identity is computed only when both approved and executed digests
    are available. The projection never establishes intent, cause, or authority.
    """
    decision_dt = _parse_time(decision_time)
    action_dt = _parse_time(action_time)
    out_limitations = list(dict.fromkeys(str(x) for x in limitations if str(x)))

    if decision_dt is None or action_dt is None:
        ordering = "UNKNOWN"
        if "MEDIATION_ORDERING_UNRESOLVED" not in out_limitations:
            out_limitations.append("MEDIATION_ORDERING_UNRESOLVED")
    elif decision_dt < action_dt:
        ordering = "BEFORE_EFFECT"
    elif decision_dt > action_dt:
        ordering = "AFTER_EFFECT"
    else:
        ordering = "SAME_BOUNDARY_UNRESOLVED"

    if approved_argument_digest in (None, "") or executed_argument_digest in (None, ""):
        argument_identity_preserved = None
    else:
        argument_identity_preserved = approved_argument_digest == executed_argument_digest

    return {
        "mediationId": mediation_id,
        "actionGroupRef": action_group_ref,
        "guardrailRef": guardrail_ref,
        "requirementDeclared": requirement_declared,
        "confirmationPresented": confirmation_presented,
        "confirmationCompleted": confirmation_completed,
        "decision": decision,
        "decisionTimeRef": decision_time_ref,
        "actionTimeRef": action_time_ref,
        "ordering": ordering,
        "denyBranchBlockedAction": deny_branch_blocked_action,
        "approvedArgumentDigest": approved_argument_digest,
        "executedArgumentDigest": executed_argument_digest,
        "argumentIdentityPreserved": argument_identity_preserved,
        "mediationEvidenceRefs": list(dict.fromkeys(str(x) for x in mediation_evidence_refs)),
        "limitations": out_limitations,
    }
