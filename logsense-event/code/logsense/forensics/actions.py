from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_PRIORITY_CORRELATION_KINDS = (
    "actionCorrelationId",
    "traceId",
    "requestId",
    "taskId",
    "jobId",
    "sessionId",
    "conversationId",
    "correlationId",
)


@dataclass(frozen=True)
class ActionAssemblyResult:
    action_groups: tuple[dict[str, Any], ...]
    ungrouped_event_refs: tuple[str, ...]
    rejected_join_refs: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


def _trusted_correlation(event: Mapping[str, Any]) -> tuple[str, str] | None:
    ids = event.get("correlationIds") or []
    by_kind = {str(x.get("kind")): x for x in ids if x.get("value") not in (None, "")}
    for kind in _PRIORITY_CORRELATION_KINDS:
        item = by_kind.get(kind)
        if not item:
            continue
        if item.get("source") == "UNTRUSTED_CLIENT_SUPPLIED":
            continue
        return kind, str(item["value"])
    return None


def _one(values: Sequence[str]) -> str | None:
    unique = sorted({v for v in values if v})
    return unique[0] if len(unique) == 1 else None


def _native_operation(event: Mapping[str, Any]) -> str | None:
    op = event.get("operation") or {}
    value = op.get("nativeOperation")
    return str(value) if value not in (None, "") else None


def _canonical_operation(event: Mapping[str, Any]) -> str | None:
    op = event.get("operation") or {}
    for key in ("canonicalVerb", "normalizedEffect"):
        value = op.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _scenario_run(event: Mapping[str, Any]) -> str | None:
    ref = event.get("scenarioRef") or {}
    value = ref.get("scenarioRunId") if isinstance(ref, Mapping) else None
    return str(value) if value not in (None, "") else None


def _compatible(anchor: Mapping[str, Any], event: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    a_actor = {str(x) for x in (anchor.get("actorRefs") or [])}
    e_actor = {str(x) for x in (event.get("actorRefs") or [])}
    if a_actor and e_actor and a_actor.isdisjoint(e_actor):
        reasons.append("ACTOR_CONFLICT")

    a_target = {str(x) for x in (anchor.get("targetRefs") or [])}
    e_target = {str(x) for x in (event.get("targetRefs") or [])}
    if a_target and e_target and a_target.isdisjoint(e_target):
        reasons.append("TARGET_CONFLICT")

    a_op, e_op = _native_operation(anchor), _native_operation(event)
    if a_op and e_op and a_op != e_op:
        reasons.append("OPERATION_CONFLICT")

    a_scenario, e_scenario = _scenario_run(anchor), _scenario_run(event)
    if a_scenario and e_scenario and a_scenario != e_scenario:
        reasons.append("SCENARIO_CONFLICT")
    return not reasons, reasons


def _build_group(
    events: Sequence[Mapping[str, Any]],
    *,
    correlation_kind: str,
    correlation_value: str,
    case_id: str,
    evidence_set_id: str,
    analysis_run_id: str,
    ordinal: int,
) -> dict[str, Any]:
    event_refs = sorted(str(e["eventId"]) for e in events)
    source_refs = sorted({str(e.get("sourceRef")) for e in events if e.get("sourceRef")})
    actors = [str(v) for e in events for v in (e.get("actorRefs") or [])]
    targets = [str(v) for e in events for v in (e.get("targetRefs") or [])]
    operations = [x for e in events if (x := _native_operation(e))]
    canonical = [x for e in events if (x := _canonical_operation(e))]

    actor = _one(actors)
    target = _one(targets)
    native_operation = _one(operations)
    canonical_operation = _one(canonical)
    exact = bool(actor and target and native_operation and correlation_value)
    identity_state = "EXACT" if exact else "PARTIAL"
    basis = ["EXACT_CORRELATION_ID"]
    if actor:
        basis.append("ACTOR_MATCH")
    if target:
        basis.append("TARGET_MATCH")
    if native_operation:
        basis.append("OPERATION_MATCH")

    operation_ref = next((str(e["eventId"]) for e in events if _native_operation(e)), None)
    task_ref = correlation_value if correlation_kind == "taskId" else None
    workflow_ref = correlation_value if correlation_kind == "workflowId" else None
    logical_key = f"action:{actor or '?'}:{native_operation or '?'}:{target or '?'}:{correlation_kind}:{correlation_value}"
    identity_limitations = [] if exact else ["ACTION_IDENTITY_PARTIAL"]

    return {
        "actionGroupId": f"{analysis_run_id}:action:{ordinal}",
        "caseId": case_id,
        "evidenceSetId": evidence_set_id,
        "analysisRunId": analysis_run_id,
        "correlationGroupRefs": [f"corr:{correlation_kind}:{correlation_value}"],
        "actionIdentity": {
            "actorRef": actor,
            "operationRef": operation_ref,
            "nativeOperation": native_operation,
            "canonicalOperation": canonical_operation,
            "targetRef": target,
            "resourceScope": target,
            "actionCorrelationId": correlation_value,
            "taskRef": task_ref,
            "workflowRef": workflow_ref,
            "buildDigest": None,
            "profileReference": None,
            "envelopeReference": None,
            "evidenceSetId": evidence_set_id,
            "scenarioRunId": _one([x for e in events if (x := _scenario_run(e))]),
            "identityState": identity_state,
            "identityBasis": basis,
            "logicalActionKey": logical_key,
            "evidenceRefs": event_refs,
            "limitations": identity_limitations,
        },
        "eventRefs": event_refs,
        "sourceRefs": source_refs,
        "requestedEventRefs": [],
        "authorizationEventRefs": [],
        "acceptedEventRefs": [],
        "appliedEventRefs": [],
        "confirmedEventRefs": [],
        "establishmentState": "ESTABLISHED" if exact else "PARTIAL",
        "limitations": ["ACTION_LIFECYCLE_NOT_EVALUATED_PR06"],
    }


def assemble_action_groups(
    events: Sequence[Mapping[str, Any]],
    *,
    case_id: str,
    evidence_set_id: str,
    analysis_run_id: str,
) -> ActionAssemblyResult:
    """Join CanonicalEvents into logical actions using exact correlation only.

    Timestamp proximity is never a join key. A matching correlation identifier
    is also insufficient when actor, target, operation, or scenario evidence
    contradicts. Lifecycle phase arrays are intentionally left empty for PR-06.
    """
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    ungrouped: list[str] = []
    rejected: list[dict[str, Any]] = []

    for event in sorted(events, key=lambda e: str(e["eventId"])):
        key = _trusted_correlation(event)
        if key is None:
            ungrouped.append(str(event["eventId"]))
            continue
        buckets = keyed.setdefault(key, [])
        placed = False
        for bucket in buckets:
            members = bucket["__members__"]
            compatible = True
            reasons: list[str] = []
            for existing in members:
                ok, why = _compatible(existing, event)
                if not ok:
                    compatible = False
                    reasons.extend(why)
            if compatible:
                members.append(event)
                placed = True
                break
            rejected.append({
                "eventRef": str(event["eventId"]),
                "correlationKind": key[0],
                "correlationValue": key[1],
                "againstEventRefs": sorted(str(x["eventId"]) for x in members),
                "reasonCodes": sorted(set(reasons)),
            })
        if not placed:
            buckets.append({"__members__": [event]})

    groups: list[dict[str, Any]] = []
    ordinal = 1
    for (kind, value), buckets in sorted(keyed.items()):
        for bucket in buckets:
            members = bucket["__members__"]
            groups.append(_build_group(
                members,
                correlation_kind=kind,
                correlation_value=value,
                case_id=case_id,
                evidence_set_id=evidence_set_id,
                analysis_run_id=analysis_run_id,
                ordinal=ordinal,
            ))
            ordinal += 1

    return ActionAssemblyResult(
        action_groups=tuple(groups),
        ungrouped_event_refs=tuple(sorted(ungrouped)),
        rejected_join_refs=tuple(rejected),
        limitations=("RAW_TIMESTAMP_ORDER_NOT_CAUSAL_ORDER", "CORRELATION_NOT_CAUSAL_PROOF"),
    )
