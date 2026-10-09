from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StateTransitionProjection:
    transitions: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


def _native_result(event: Mapping[str, Any]) -> str | None:
    result = event.get("result")
    value = result.get("native") if isinstance(result, Mapping) else result
    if value in (None, ""):
        value = (event.get("attributes") or {}).get("decision")
    return str(value) if value not in (None, "") else None


def _success(value: str | None) -> bool:
    if value is None:
        return False
    raw = value.strip().upper()
    if raw.isdigit():
        return 200 <= int(raw) < 300
    return raw in {
        "ALLOW", "ALLOWED", "APPROVE", "APPROVED", "GRANT", "GRANTED",
        "ACCEPTED", "SUCCESS", "SUCCEEDED", "COMPLETED", "APPLIED",
        "EXECUTED", "READ_OK", "WRITE_OK", "OK", "TRUE",
    }


def _deny(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().upper() in {
        "DENY", "DENIED", "BLOCK", "BLOCKED", "REJECT", "REJECTED",
        "FORBID", "FORBIDDEN", "FALSE",
    }


def _cell(state: str, refs: Sequence[str] = (), limitations: Sequence[str] = ()) -> dict[str, Any]:
    return {"state": state, "evidenceRefs": list(refs), "gapRefs": [], "limitations": list(limitations)}


def evaluate_action_lifecycle(
    action_group: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    coverage_id: str,
    confirmed_evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Evaluate lifecycle coverage without promoting API acceptance to effect.

    Confirmed evidence must be supplied by a later bound state-transition owner.
    Raw STATE_OBSERVATION events are intentionally insufficient here.
    """
    event_ids = {str(x) for x in action_group.get("eventRefs", [])}
    relevant = [e for e in events if str(e.get("eventId")) in event_ids]

    requested = [
        str(e["eventId"]) for e in relevant
        if e.get("eventClass") in {"TOOL_CALL_REQUEST", "API_REQUEST", "AUTHORIZATION_REQUEST", "TASK_CREATED"}
    ]

    auth_allow: list[str] = []
    auth_deny: list[str] = []
    for e in relevant:
        if e.get("eventClass") not in {"AUTHORIZATION_DECISION", "GUARDRAIL_EVALUATION"}:
            continue
        value = _native_result(e)
        if _deny(value):
            auth_deny.append(str(e["eventId"]))
        elif _success(value):
            auth_allow.append(str(e["eventId"]))

    accepted = [
        str(e["eventId"]) for e in relevant
        if e.get("eventClass") == "API_RESPONSE" and _success(_native_result(e))
    ]

    applied = [
        str(e["eventId"]) for e in relevant
        if e.get("eventClass") in {"EXECUTION_RESULT", "AUDIT_EVENT"} and _success(_native_result(e))
    ]

    if auth_deny:
        authorized = _cell("CONTRADICTED", auth_deny + auth_allow, ["EXPLICIT_DENY_PRESENT"])
    elif auth_allow:
        authorized = _cell("PRESENT", auth_allow)
    else:
        authorized = _cell("UNKNOWN", (), ["NO_EXPLICIT_AUTHORIZATION_DECISION"])

    confirmed = _cell("PRESENT", confirmed_evidence_refs) if confirmed_evidence_refs else _cell(
        "UNKNOWN", (), ["BOUND_STATE_TRANSITION_REQUIRED_FOR_CONFIRMATION"]
    )

    return {
        "coverageId": coverage_id,
        "actionGroupRef": str(action_group["actionGroupId"]),
        "actionRequested": _cell("PRESENT", requested) if requested else _cell("UNKNOWN"),
        "actionAuthorized": authorized,
        "actionAccepted": _cell("PRESENT", accepted) if accepted else _cell("UNKNOWN"),
        "actionApplied": _cell("PRESENT", applied) if applied else _cell(
            "UNKNOWN", (), ["API_ACCEPTED_NE_ACTION_APPLIED"]
        ),
        "actionConfirmed": confirmed,
        "localForensicLens": True,
        "limitations": ["HTTP_200_NE_ACTION_APPLIED", "API_ACCEPTED_NE_EFFECT_CONFIRMED"],
    }


def evaluate_five_plane_coverage(
    action_group: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    *,
    coverage_id: str,
) -> dict[str, Any]:
    event_ids = {str(x) for x in action_group.get("eventRefs", [])}
    relevant = [e for e in events if str(e.get("eventId")) in event_ids]
    grant_refs = [
        str(e["eventId"]) for e in relevant
        if e.get("eventClass") == "IAM_GRANT_EVENT" and not _deny(_native_result(e))
    ]
    observed_refs = list(lifecycle["actionApplied"].get("evidenceRefs", [])) + list(
        lifecycle["actionConfirmed"].get("evidenceRefs", [])
    )
    return {
        "coverageId": coverage_id,
        "actionGroupRef": str(action_group["actionGroupId"]),
        "requested": dict(lifecycle["actionRequested"]),
        "policyAuthorized": dict(lifecycle["actionAuthorized"]),
        "effectivelyGranted": _cell("PRESENT", grant_refs) if grant_refs else _cell(
            "UNKNOWN", (), ["EFFECTIVE_GRANT_EVIDENCE_MISSING"]
        ),
        "codeCapable": _cell("UNKNOWN", (), ["STATIC_CODE_CAPABILITY_NOT_EVALUATED"]),
        "observed": _cell("PRESENT", sorted(set(observed_refs))) if observed_refs else _cell("UNKNOWN"),
        "localForensicLens": True,
        "limitations": ["PERMISSION_NE_DELEGATION", "OBSERVED_NE_CAUSAL_ATTRIBUTION"],
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def reconstruct_state_transitions(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis_run_id: str,
) -> StateTransitionProjection:
    """Reconstruct paired state changes without attributing them to operations."""
    observations: dict[tuple[str, str], list[tuple[datetime, str, Mapping[str, Any], Mapping[str, Any]]]] = {}
    limitations: set[str] = {"OBSERVED_DELTA_NE_EFFECT_CAUSED_BY_ACTION"}

    for event in events:
        event_id = str(event.get("eventId"))
        targets = [str(x) for x in (event.get("targetRefs") or [])]
        if len(targets) != 1:
            continue
        event_time = _parse_time(str(event.get("eventTime")) if event.get("eventTime") else None)
        for obs in event.get("stateObservations") or []:
            effective = _parse_time(str(obs.get("effectiveAt")) if obs.get("effectiveAt") else None) or event_time
            if effective is None:
                limitations.add("UNORDERED_STATE_OBSERVATION_SKIPPED")
                continue
            key = (targets[0], str(obs["property"]))
            observations.setdefault(key, []).append((effective, event_id, event, obs))

    transitions: list[dict[str, Any]] = []
    ordinal = 1
    for (subject, prop), rows in sorted(observations.items()):
        rows.sort(key=lambda x: (x[0], x[1]))
        for prior, current in zip(rows, rows[1:], strict=False):
            prior_obs, current_obs = prior[3], current[3]
            if str(prior_obs.get("value")) == str(current_obs.get("value")):
                continue
            transitions.append({
                "transitionId": f"{analysis_run_id}:transition:{ordinal}",
                "analysisRunId": analysis_run_id,
                "subjectRef": subject,
                "property": prop,
                "stateFacet": current_obs.get("stateFacet") or prior_obs.get("stateFacet"),
                "priorObservationRef": prior[1],
                "currentObservationRef": current[1],
                "transitionKind": "RECONSTRUCTED_PAIR",
                "operationAttributionState": "UNBOUND",
                "operationEventRefs": [],
                "relationEvaluationRefs": [],
                "orderingBasis": "EVENT_TIME",
                "evidenceRefs": [prior[1], current[1]],
                "limitations": ["OPERATION_ATTRIBUTION_REQUIRES_RELATION_ADMISSION"],
            })
            ordinal += 1

    return StateTransitionProjection(
        transitions=tuple(transitions),
        limitations=tuple(sorted(limitations)),
    )
