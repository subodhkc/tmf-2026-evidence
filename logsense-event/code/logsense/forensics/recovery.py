from __future__ import annotations

from collections.abc import Sequence


def assess_recovery_projection(
    *,
    recovery_id: str,
    incident_snapshot_ref: str,
    recovery_action_refs: Sequence[str] = (),
    rollback_requested_refs: Sequence[str] = (),
    rollback_completed_refs: Sequence[str] = (),
    state_restored_refs: Sequence[str] = (),
    service_health_restored_refs: Sequence[str] = (),
    downstream_impact_resolved_refs: Sequence[str] = (),
    verification_test_refs: Sequence[str] = (),
    replay_or_cancel_capability: str = "UNKNOWN",
    verification_state: str = "UNKNOWN",
    contradicted: bool = False,
    evidence_refs: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict:
    """Project recovery state without equating rollback completion with recovery.

    ESTABLISHED requires post-recovery evidence for restored state, restored
    service health, and resolved downstream impact. A completed rollback with
    missing post-state proof remains PARTIAL.
    """
    recovery_action_refs = tuple(dict.fromkeys(str(x) for x in recovery_action_refs))
    rollback_requested_refs = tuple(dict.fromkeys(str(x) for x in rollback_requested_refs))
    rollback_completed_refs = tuple(dict.fromkeys(str(x) for x in rollback_completed_refs))
    state_restored_refs = tuple(dict.fromkeys(str(x) for x in state_restored_refs))
    service_health_restored_refs = tuple(dict.fromkeys(str(x) for x in service_health_restored_refs))
    downstream_impact_resolved_refs = tuple(
        dict.fromkeys(str(x) for x in downstream_impact_resolved_refs)
    )
    verification_test_refs = tuple(dict.fromkeys(str(x) for x in verification_test_refs))
    evidence_refs = tuple(dict.fromkeys(str(x) for x in evidence_refs))
    limitations = tuple(dict.fromkeys(str(x) for x in limitations if str(x)))

    any_recovery_evidence = any(
        (
            recovery_action_refs,
            rollback_requested_refs,
            rollback_completed_refs,
            state_restored_refs,
            service_health_restored_refs,
            downstream_impact_resolved_refs,
            verification_test_refs,
        )
    )
    if verification_state not in {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"}:
        raise ValueError(f"unsupported verification_state: {verification_state}")

    out_limitations = list(limitations)
    if not any_recovery_evidence:
        state = "NOT_AVAILABLE"
        if verification_state != "UNKNOWN":
            out_limitations.append("RECOVERY_EVIDENCE_NOT_AVAILABLE")
    elif contradicted or (
        verification_state == "FAIL"
        and (state_restored_refs or service_health_restored_refs or downstream_impact_resolved_refs)
    ):
        state = "CONTRADICTED"
        if verification_state == "FAIL":
            out_limitations.append("RECOVERY_VERIFICATION_CONTRADICTS_RESTORATION_CLAIM")
    elif state_restored_refs and service_health_restored_refs and downstream_impact_resolved_refs:
        state = "ESTABLISHED"
    else:
        state = "PARTIAL"

    if verification_state != "UNKNOWN":
        if rollback_completed_refs and not state_restored_refs:
            out_limitations.append("ROLLBACK_COMPLETED_NE_STATE_RESTORED")
        if state_restored_refs and not service_health_restored_refs:
            out_limitations.append("STATE_RESTORED_NE_SERVICE_HEALTH_RESTORED")
        if service_health_restored_refs and not downstream_impact_resolved_refs:
            out_limitations.append("SERVICE_HEALTH_RESTORED_NE_IMPACT_RESOLVED")
        if verification_state == "FAIL" and not (
            state_restored_refs or service_health_restored_refs or downstream_impact_resolved_refs
        ):
            out_limitations.append("VERIFICATION_FAILED_RECOVERY_REMAINS_PARTIAL")

    not_claimed: list[str] = []
    if not state_restored_refs:
        not_claimed.append("STATE_RESTORED")
    if not downstream_impact_resolved_refs:
        not_claimed.append("IMPACT_RESOLVED")

    return {
        "recoveryId": recovery_id,
        "incidentSnapshotRef": incident_snapshot_ref,
        "recoveryActionRefs": list(recovery_action_refs),
        "rollbackRequestedRefs": list(rollback_requested_refs),
        "rollbackCompletedRefs": list(rollback_completed_refs),
        "stateRestoredRefs": list(state_restored_refs),
        "serviceHealthRestoredRefs": list(service_health_restored_refs),
        "downstreamImpactResolvedRefs": list(downstream_impact_resolved_refs),
        "verificationTestRefs": list(verification_test_refs),
        "replayOrCancelCapability": replay_or_cancel_capability,
        "state": state,
        "evidenceRefs": list(evidence_refs),
        "limitations": list(dict.fromkeys(out_limitations)),
        "notClaimed": not_claimed,
    }
