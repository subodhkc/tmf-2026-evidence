"""Competition run declarations and deterministic run resolution.

One case may eventually contain evidence for several competition runs. A
``CompetitionRun`` declaration binds evidence to a run only through explicit
deterministic identifiers — never through timestamp proximity, heuristics, or
AI inference. Declarations are operator inputs and are always marked
``USER_DECLARED``; the declaration never pretends its bindings came from
telemetry.

Resolution precedence, highest to lowest:

1. explicit scenario/run identifier carried by the event
   (``scenarioRef``, ``runId``, ``scenarioRunId`` equal to the declaration),
2. declared identifier sets (traceIds, requestIds, sessionIds,
   agentExecutionIds, modelCallIds, toolCallIds, mcpCallIds, plus an
   open ``identifiers`` map for other deterministic shared identifiers),
3. explicit parent/action relations (``declaredRelationRefs``) to a bound
   event, then
4. shared identifier values of an allowlisted identifier kind with an
   already-bound event.

Only the kinds in ``IDENTIFIER_KINDS`` — plus identifier kinds the operator
explicitly declared on a run — may establish or propagate membership.
Ordinary semantic attributes (``agentId``, ``eventType``, ``operation``,
``status``, ``service.name``, …) never establish run membership on their
own, because two unrelated runs may legitimately share them.

Every binding records its basis. Events that look run-relevant but cannot be
bound stay visible in ``unresolvedEvidenceRefs``; evidence carrying
conflicting run-scoped identifiers lands in ``ambiguousEvidenceRefs`` and is
excluded from ``qualifiedEventRefs`` so it cannot influence measurements.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

RUN_DECLARATION_SCHEMA = "competition-run-declaration/0.1"
RUN_RESOLUTION_SCHEMA = "competition-run-resolution/0.1"

RESOLUTION_STATES = ("RESOLVED", "PARTIAL", "AMBIGUOUS", "NOT_RESOLVED")

# Bounded identifier vocabulary. Attribute/correlation keys are normalized
# through this alias table so ``session_id`` and ``sessionId`` resolve to the
# same declared kind. Unknown kinds are preserved verbatim (an operator may
# still declare them under the free-form ``identifiers`` map), but they never
# trigger the run-scoped ambiguity checks below.
_IDENTIFIER_ALIASES: dict[str, str] = {
    "runid": "runId",
    "run_id": "runId",
    "scenariorunid": "scenarioRunId",
    "scenario_run_id": "scenarioRunId",
    "traceid": "traceId",
    "trace_id": "traceId",
    "requestid": "requestId",
    "request_id": "requestId",
    "sessionid": "sessionId",
    "session_id": "sessionId",
    "agentexecutionid": "agentExecutionId",
    "agent_execution_id": "agentExecutionId",
    "modelcallid": "modelCallId",
    "model_call_id": "modelCallId",
    "toolcallid": "toolCallId",
    "tool_call_id": "toolCallId",
    "mcpcallid": "mcpCallId",
    "mcp_call_id": "mcpCallId",
    "mcprequestid": "mcpRequestId",
    "mcp_request_id": "mcpRequestId",
    "actioncorrelationid": "actionCorrelationId",
    "action_correlation_id": "actionCorrelationId",
    "correlationid": "correlationId",
    "correlation_id": "correlationId",
    "taskid": "taskId",
    "task_id": "taskId",
    "contextid": "contextId",
    "context_id": "contextId",
    "spanid": "spanId",
    "span_id": "spanId",
    "parentspanid": "parentSpanId",
    "parent_span_id": "parentSpanId",
}

RUN_SCOPED_KINDS = ("runId", "scenarioRunId")

# Identifier-kind allowlist. Only these normalized kinds (plus kinds the
# operator explicitly declares on a run declaration) may bind evidence to a
# run or propagate membership between events. Semantic attributes such as
# agentId, eventType, operation, status, or service.name are deliberately
# excluded — they describe what happened, not which run it belongs to.
IDENTIFIER_KINDS = frozenset(_IDENTIFIER_ALIASES.values())

# Kinds an operator can declare as named sets on the declaration itself.
DECLARED_IDENTIFIER_SETS: dict[str, str] = {
    "scenarioRunIds": "scenarioRunId",
    "traceIds": "traceId",
    "requestIds": "requestId",
    "sessionIds": "sessionId",
    "agentExecutionIds": "agentExecutionId",
    "modelCallIds": "modelCallId",
    "toolCallIds": "toolCallId",
    "mcpCallIds": "mcpCallId",
    "mcpRequestIds": "mcpRequestId",
    "actionCorrelationIds": "actionCorrelationId",
    "taskIds": "taskId",
    "contextIds": "contextId",
}

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class CompetitionRunError(ValueError):
    """Raised for malformed run declarations or resolution inputs."""


def normalize_identifier_kind(kind: Any) -> str:
    raw = str(kind or "").strip()
    return _IDENTIFIER_ALIASES.get(raw.lower(), raw)


def _values(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise CompetitionRunError(f"{key} must be an array of identifier strings")
    values: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def normalize_run_declaration(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one operator run declaration.

    The declaration is an explicit operator input; provenance is always
    ``USER_DECLARED`` regardless of where the identifier strings originated.
    """
    if not isinstance(payload, Mapping):
        raise CompetitionRunError("run declaration must be an object")
    run_id = str(payload.get("runId") or payload.get("scenarioRunId") or "").strip()
    if not _RUN_ID_RE.fullmatch(run_id):
        raise CompetitionRunError(
            "runId must start with an alphanumeric character and use only "
            "letters, numbers, '.', '_' or '-'"
        )
    declared: dict[str, tuple[str, ...]] = {}
    for key, kind in DECLARED_IDENTIFIER_SETS.items():
        values = _values(payload, key)
        if values:
            declared[kind] = tuple(dict.fromkeys((*declared.get(kind, ()), *values)))
    extra = payload.get("identifiers")
    if extra is not None:
        if not isinstance(extra, Mapping):
            raise CompetitionRunError("identifiers must be an object of kind -> [values]")
        for kind in extra:
            kind_key = normalize_identifier_kind(kind)
            merged = tuple(dict.fromkeys((*declared.get(kind_key, ()), *_values(extra, kind))))
            if merged:
                declared[kind_key] = merged
    return {
        "schemaVersion": RUN_DECLARATION_SCHEMA,
        "runId": run_id,
        "label": str(payload.get("label") or run_id),
        "declaredBy": "USER",
        "provenance": "USER_DECLARED",
        "declaredIdentifiers": {kind: list(values) for kind, values in sorted(declared.items())},
        "notes": str(payload["notes"]) if payload.get("notes") is not None else None,
        "source": str(payload["source"]) if payload.get("source") is not None else None,
        "declaredAt": str(payload["declaredAt"]) if payload.get("declaredAt") is not None else None,
    }


def declared_identifier_sets(declaration: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Return kind -> declared values for one normalized declaration."""
    declared = declaration.get("declaredIdentifiers") or {}
    sets: dict[str, frozenset[str]] = {}
    for kind, values in declared.items():
        sets[normalize_identifier_kind(kind)] = frozenset(str(v) for v in values if str(v))
    sets.setdefault("runId", frozenset()).union()
    sets["runId"] = sets.get("runId", frozenset()) | {str(declaration["runId"])}
    sets["scenarioRunId"] = sets.get("scenarioRunId", frozenset()) | {str(declaration["runId"])}
    return sets


def event_identifiers(
    event: Mapping[str, Any], *, declared_kinds: Iterable[str] = ()
) -> dict[str, frozenset[str]]:
    """Extract deterministic identifier (kind -> values) pairs from an event.

    Sources: ``correlationIds`` entries, flat ``attributes`` keys, and
    ``scenarioRef``. Nested structures are not scanned — the canonical event
    projection is the bounded surface this resolver is defined over.

    Only ``IDENTIFIER_KINDS`` plus ``declared_kinds`` (operator-declared
    custom identifier kinds) are extracted. Arbitrary attributes are not
    identifiers and cannot participate in run binding or propagation.
    """
    allowed = IDENTIFIER_KINDS | {normalize_identifier_kind(kind) for kind in declared_kinds}
    found: dict[str, set[str]] = {}

    def add(kind: Any, value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        normalized = normalize_identifier_kind(kind)
        if normalized not in allowed:
            return
        found.setdefault(normalized, set()).add(text)

    correlations = event.get("correlationIds") or ()
    for item in correlations:
        if isinstance(item, Mapping):
            add(item.get("kind"), item.get("value"))
    attributes = event.get("attributes") or {}
    if isinstance(attributes, Mapping):
        for key, value in attributes.items():
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                add(key, value)
    scenario = event.get("scenarioRef")
    if scenario:
        add("scenarioRunId", scenario)
    return {kind: frozenset(values) for kind, values in found.items()}


def resolve_competition_run(
    canonical_events: Sequence[Mapping[str, Any]],
    declaration: Mapping[str, Any],
    *,
    other_declarations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Bind canonical events to one declared run — identifiers only.

    Returns the ``competition-run-resolution/0.1`` output described in the
    module docstring. No timestamps, no similarity, no inference.
    """
    if declaration.get("schemaVersion") != RUN_DECLARATION_SCHEMA:
        declaration = normalize_run_declaration(declaration)
    run_id = str(declaration["runId"])
    declared = declared_identifier_sets(declaration)
    other_sets = [
        (str(other["runId"]), declared_identifier_sets(other)) for other in other_declarations
    ]

    # Identifier kinds allowed to bind/propagate: the built-in allowlist plus
    # every kind any run declaration explicitly declared (operator-declared
    # custom kinds may participate — the operator asserted they identify runs).
    declared_kinds = set(declared)
    for _other_run, other_ids in other_sets:
        declared_kinds.update(other_ids)

    event_rows: list[tuple[str, Mapping[str, Any], dict[str, frozenset[str]]]] = []
    for event in canonical_events:
        ref = str(event.get("eventId") or "")
        if not ref:
            continue
        event_rows.append((ref, event, event_identifiers(event, declared_kinds=declared_kinds)))

    # Ambiguity is intrinsic to an event's own identifiers: a conflicting
    # run-scoped identifier, or overlap with another declared run's
    # identifier sets. It is decided before binding so ambiguous evidence can
    # never bind, seed propagation, or reach a measurement.
    ambiguous: list[str] = []
    for ref, _event, ids in event_rows:
        foreign_run = ids.get("runId", frozenset()) | ids.get("scenarioRunId", frozenset())
        if foreign_run - {run_id}:
            ambiguous.append(ref)
            continue
        for other_run, other_ids in other_sets:
            if other_run == run_id:
                continue
            overlap = any(
                values & other_ids.get(kind, frozenset())
                for kind, values in ids.items()
                if kind in other_ids
            )
            if overlap:
                ambiguous.append(ref)
                break
    ambiguous_set = set(ambiguous)

    bound: dict[str, set[str]] = {}
    for ref, _event, ids in event_rows:
        if ref in ambiguous_set:
            continue
        basis: set[str] = set()
        for kind, values in ids.items():
            if kind in RUN_SCOPED_KINDS and run_id in values:
                basis.add("RUN_ID_MATCH")
                continue
            declared_values = declared.get(kind)
            if declared_values and values & declared_values:
                basis.add(f"{_basis_token(kind)}_MATCH")
        if basis:
            bound[ref] = basis

    # Explicit relation/shared-identifier expansion. Bounded by event count;
    # only deterministic identifier equality or declared parent/action
    # relations may extend membership — never time proximity.
    index = {ref: ids for ref, _event, ids in event_rows}
    changed = True
    while changed:
        changed = False
        bound_values: dict[str, set[str]] = {}
        for ref in bound:
            for kind, values in index[ref].items():
                bound_values.setdefault(kind, set()).update(values)
        bound_refs = set(bound)
        for ref, event, ids in event_rows:
            if ref in bound or ref in ambiguous_set:
                continue
            relation = event.get("declaredRelationRefs") or ()
            relation_refs = {
                str(item.get("ref") or item.get("targetRef") or item.get("eventId") or "")
                for item in relation
                if isinstance(item, Mapping)
            }
            if relation_refs & bound_refs:
                bound[ref] = {"PARENT_RELATION_MATCH"}
                changed = True
                continue
            for kind, values in ids.items():
                if kind in RUN_SCOPED_KINDS:
                    continue
                if values & bound_values.get(kind, set()):
                    bound[ref] = {f"SHARED_IDENTIFIER_MATCH:{kind}"}
                    changed = True
                    break

    unresolved: list[str] = []
    unidentified_count = 0
    for ref, _event, ids in event_rows:
        if ref in bound or ref in ambiguous_set:
            continue
        if ids:
            unresolved.append(ref)
        else:
            unidentified_count += 1

    # Qualified evidence = bound events only; ambiguous evidence never enters
    # the qualified set and may never influence a measurement.
    qualified_refs = [ref for ref, _e, _i in event_rows if ref in bound]
    qualified_set = set(qualified_refs)

    basis_all: set[str] = {"USER_DECLARED"}
    for basis in bound.values():
        basis_all.update(basis)

    # Resolution semantics — conservative; never overstate qualification:
    #   AMBIGUOUS     at least one record could belong to multiple runs
    #   NOT_RESOLVED  no qualified deterministic binding exists
    #   PARTIAL       bound events exist, but unresolved or unattributable
    #                 (identifier-less) in-scope evidence remains
    #   RESOLVED      all assessable evidence is unambiguously assigned
    if ambiguous:
        state = "AMBIGUOUS"
    elif not qualified_refs:
        state = "NOT_RESOLVED"
    elif unresolved or unidentified_count:
        state = "PARTIAL"
    else:
        state = "RESOLVED"

    # Collect actor/agent identities for qualified events only.
    agent_ids: set[str] = set()
    for ref, event, _ids in event_rows:
        if ref not in qualified_set:
            continue
        for actor in event.get("actorRefs") or ():
            text = str(actor)
            agent_ids.add(text.split(":", 1)[-1] if ":" in text else text)

    observed_kinds: dict[str, set[str]] = {}
    for ref, _event, ids in event_rows:
        if ref not in qualified_set:
            continue
        for kind, values in ids.items():
            observed_kinds.setdefault(kind, set()).update(values)

    limitations: list[str] = []
    if unidentified_count:
        limitations.append(f"EVENTS_WITHOUT_IDENTIFIERS_NOT_ATTRIBUTABLE:{unidentified_count}")
    if unresolved:
        limitations.append("UNRESOLVED_IDENTIFIER_BEARING_EVIDENCE_PRESENT")
    if ambiguous:
        limitations.append("CONFLICTING_RUN_IDENTIFIERS_PRESENT")
        limitations.append(f"AMBIGUOUS_EVIDENCE_EXCLUDED_FROM_QUALIFIED_SET:{len(ambiguous)}")

    return {
        "schemaVersion": RUN_RESOLUTION_SCHEMA,
        "runId": run_id,
        "label": declaration.get("label") or run_id,
        "declaration": dict(declaration),
        "resolutionState": state,
        "bindingBasis": sorted(basis_all),
        # eventRefs is kept for compatibility and is defined as the qualified
        # set — ambiguous evidence is never included.
        "eventRefs": qualified_refs,
        "qualifiedEventRefs": qualified_refs,
        "traceIds": sorted(observed_kinds.get("traceId", set())),
        "requestIds": sorted(observed_kinds.get("requestId", set())),
        "sessionIds": sorted(observed_kinds.get("sessionId", set())),
        "agentIds": sorted(agent_ids),
        "identifiers": {kind: sorted(values) for kind, values in sorted(observed_kinds.items())},
        "unresolvedEvidenceRefs": unresolved,
        "ambiguousEvidenceRefs": ambiguous,
        "unidentifiedEventCount": unidentified_count,
        "limitations": limitations,
    }


def _basis_token(kind: str) -> str:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(kind))
    return re.sub(r"[^A-Za-z0-9]+", "_", spaced).strip("_").upper() or "IDENTIFIER"
