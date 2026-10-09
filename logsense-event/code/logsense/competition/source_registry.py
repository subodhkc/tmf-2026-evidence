"""Event-day source acquisition projections.

One operator-facing layer that turns the existing intake/profiling/mapping
state into first-hour answers:

- ``source_registry`` — per-source readiness row: what arrived, what parsed,
  what mapped, what qualified, and what the deterministic next action is.
- ``capability_matrix`` — per source, which competition facts it can
  currently produce (run identity, run start, C7 events, C9 KPI, C16
  tokens, enforcement-point visibility). A promising *field name* is at
  most ``OBSERVED``/``ONSITE_VERIFY`` — never ``QUALIFIED``.
- ``enforcement_point_discovery`` — observed interception-point candidates
  projected only from evidence actually present, merged with operator-
  declared points. Nothing pre-labels the lab architecture.
- ``control_source_feasibility`` — READY / LIMITED / BLOCKED per control
  from the source facts currently present, with the exact missing facts.
  This is acquisition readiness, complementary to the measurement-pipeline
  ``control_feasibility`` projection.
- ``first_hour_dashboard`` — the compact first-hour status block:
  sources, run identity, run start, enforcement points, control
  readiness, and prioritized deterministic next actions.

Locks preserved here:

- A field name or timestamp is never silently promoted into a qualified
  competition fact. ``QUALIFIED`` requires evidence already bound by
  ``resolve_competition_run`` / ``resolve_run_activity``.
- ``RUN_START`` capability means an explicit lifecycle/start semantic —
  the same vocabulary ``run_activity.py`` accepts. Timestamps, ``startedAt``
  fields, and earliest-observed activity only ever yield ``OBSERVED`` or
  ``ONSITE_VERIFY``.
- Nothing here invents vendor adapters or lab architecture. Named adapters
  stay behind the evidence gate; ``ONSITE_VERIFY`` is the honest label for
  "looks promising — prove it on the floor."
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from logsense.competition.run import event_identifiers
from logsense.competition.run_activity import is_run_lifecycle_event

CONTROL7_CODE = "AIA-LOG-001"
CONTROL9_CODE = "AIA-ARC-006"
CONTROL16_CODE = "ACN-COST-001"

SOURCE_REGISTRY_SCHEMA = "competition-source-registry/0.1"
CAPABILITY_MATRIX_SCHEMA = "competition-capability-matrix/0.1"
EP_DISCOVERY_SCHEMA = "competition-ep-discovery/0.1"
ACQUISITION_FEASIBILITY_SCHEMA = "competition-acquisition-feasibility/0.1"
FIRST_HOUR_SCHEMA = "competition-first-hour/0.1"

SOURCE_STATUSES = (
    "NOT_CONFIGURED",
    "CONNECTED",
    "DATA_RECEIVED",
    "PROFILED",
    "MAPPED",
    "READY",
    "LIMITED",
    "BLOCKED",
)
CAPABILITY_STATES = (
    "OBSERVED",
    "MAPPED",
    "QUALIFIED",
    "NOT_FOUND",
    "NOT_APPLICABLE",
    "ONSITE_VERIFY",
)
EP_STATES = ("OBSERVED", "DECLARED", "QUALIFIED", "UNCONFIRMED")
ACQUISITION_STATES = ("READY", "LIMITED", "BLOCKED")


def _norm(name: Any) -> str:
    return str(name).lower().replace("_", "").replace(".", "").replace("-", "")


# --- bounded field-name hint vocabularies ---------------------------------
# These are *hints for candidates*. Presence earns OBSERVED/ONSITE_VERIFY at
# most — only run-bound qualified evidence can earn QUALIFIED.

_RUN_ID_HINTS = frozenset(
    {
        "runid", "runidentifier", "scenariorunid", "scenarioexecutionid",
        "traceid", "requestid", "sessionid", "agentexecutionid",
        "executionid", "correlationid", "faultid", "faultinjectionid",
        "scenarioid", "spanid", "conversationid",
    }
)
_TIMESTAMP_HINTS = frozenset(
    {
        "timestamp", "ts", "time", "datetime", "eventtime", "observedat",
        "occurredat", "createdat", "logtime", "starttimeunixnano",
        "endtimeunixnano", "unixnano",
    }
)
_EVENT_TYPE_HINTS = frozenset(
    {
        "eventtype", "type", "name", "action", "operation", "eventname",
        "recordtype", "spanname", "kind", "opcode",
    }
)
_AGENT_HINTS = frozenset(
    {
        "agentid", "agent", "agentname", "actorid", "actor", "servicename",
        "service", "componentid", "agentexecutionid", "workerid",
        "spanid",
    }
)
_TOKEN_HINTS = frozenset(
    {
        "inputtokens", "outputtokens", "prompttokens", "completiontokens",
        "totaltokens", "tokensused", "tokencount", "usage",
        "prompttokencount", "candidatestokencount",
    }
)
_MODEL_CALL_HINTS = frozenset(
    {
        "modelid", "model", "modelname", "provider", "providername",
        "callid", "modelcallid", "invocationid", "completionid",
        "requestid", "chatcompletionid",
    }
)
_RETRY_HINTS = frozenset(
    {
        "retry", "retries", "retrycount", "attempt", "attemptnumber",
        "retryattempt", "retryindex", "invocationattempt",
    }
)
_KPI_NAME_HINTS = frozenset(
    {"metricname", "kpiname", "metric", "kpi", "metricid", "kpiid", "measurename"}
)
_KPI_VALUE_HINTS = frozenset(
    {
        "metricvalue", "value", "latency", "throughput", "responsetime",
        "availability", "errorrate", "measurementvalue", "observedvalue",
    }
)
_KPI_UNIT_HINTS = frozenset({"unit", "units", "metricunit", "unitofmeasure"})
_KPI_DIRECTION_HINTS = frozenset(
    {
        "direction", "higherisbetter", "thresholddirection", "gooddirection",
        "improvementdirection", "preferredirection", "optimizefor",
    }
)
_KPI_WINDOW_HINTS = frozenset(
    {
        "observedat", "window", "windowstart", "windowend", "period",
        "scope", "profile", "cadence", "interval", "sampletime",
    }
)
_EP_FIELD_HINTS = frozenset(
    {
        "gateway", "gatewayname", "gatewayid", "proxy", "enforcementpoint",
        "policydecision", "decision", "allowdeny", "guardrail", "boundary",
        "zone", "zonename", "mcpboundary", "ztna", "interceptionpoint",
        "enforcementdecision", "policydecisionpoint", "enforcementaction",
        "verdict", "actiontaken", "disposition",
    }
)
_EP_DECISION_VALUES = frozenset(
    {
        "allow", "allowed", "deny", "denied", "blocked", "block", "halt",
        "halted", "stopped", "stop", "rejected", "reject", "permitted",
        "throttled", "rate_limited",
    }
)
_RUN_START_FIELD_HINTS = frozenset(
    {
        "runstart", "runstartedat", "runstarttime", "runbegin",
        "assessedrunstart", "scenariostart", "scenariostartedat",
        "executionstarttime",
    }
)
_EVENT_TYPE_FIELD_KEYS = frozenset(
    {"eventtype", "type", "eventname", "name", "recordtype", "kind"}
)
# Candidate start-looking *values* — they earn ONSITE_VERIFY, never QUALIFIED.
_RUN_START_VALUE_HINTS = frozenset(
    {
        "run_started", "runstarted", "scenario_started", "fault_injected",
        "fault_injection_started", "execution_started", "scenario_start",
        "run_start", "assessed_run_started", "assessed_activity_started",
        "run_completed", "scenario_completed",
    }
)


def _artifact_events(
    canonical_events: Sequence[Mapping[str, Any]], artifact_id: str
) -> list[Mapping[str, Any]]:
    """Canonical events produced by one artifact — via rawRecordRefs lineage."""
    out: list[Mapping[str, Any]] = []
    for event in canonical_events:
        refs = event.get("rawRecordRefs") or ()
        for ref in refs:
            if str(ref.get("artifactId") or "") == artifact_id:
                out.append(event)
                break
    return out


def _field_set(field_paths: Sequence[str]) -> frozenset[str]:
    return frozenset(_norm(path) for path in field_paths)


def _hinted(fields: frozenset[str], hints: frozenset[str]) -> frozenset[str]:
    return fields & hints


def _source_status(row: Mapping[str, Any]) -> str:
    """Deterministic registry status from existing overview states.

    File-import artifacts arrive already received — the honest floor is
    ``DATA_RECEIVED``. ``LIMITED`` outranks ``PROFILED``: a source with an
    unactionable proposal or partial parse is not quietly "profiled".
    """
    state = str(row.get("mappingState") or "")
    profile_state = str(row.get("profileState") or "")
    events = int(row.get("canonicalEventCount") or 0)
    parsed = int(row.get("parsedRecordCount") or 0)
    failed = int(row.get("failedRecordCount") or 0)
    if state == "OPAQUE_PRESERVED" or profile_state == "FAILED":
        return "BLOCKED"
    if state in ("NO_MAPPING_AVAILABLE", "APPROVAL_REJECTED_NEEDS_REVIEW"):
        return "LIMITED"
    if profile_state == "PARTIAL" or (failed and parsed):
        return "LIMITED"
    if state in ("APPROVED_USER", "PREMAPPED"):
        return "READY" if events else "MAPPED"
    if state == "PROPOSAL_AVAILABLE":
        return "PROFILED"
    return "DATA_RECEIVED"


def _capability_cell(
    *,
    qualified: bool,
    canonical_fact: bool,
    mapped: bool,
    field_hint: bool,
    source_blocked: bool,
) -> str:
    """One capability-matrix cell. QUALIFIED only for run-bound truth."""
    if qualified:
        return "QUALIFIED"
    if canonical_fact:
        return "MAPPED" if mapped else "OBSERVED"
    if field_hint:
        return "OBSERVED" if mapped else "ONSITE_VERIFY"
    if source_blocked:
        return "NOT_APPLICABLE"
    return "NOT_FOUND"


def _usage_fact_on(events: Sequence[Mapping[str, Any]]) -> bool:
    """Whether canonical events carry token-usage attributes (mapped fact)."""
    for event in events:
        attrs = {_norm(k) for k in (event.get("attributes") or {})}
        if attrs & _TOKEN_HINTS:
            return True
    return False


def _metric_fact_on(events: Sequence[Mapping[str, Any]]) -> bool:
    for event in events:
        attrs = {_norm(k) for k in (event.get("attributes") or {})}
        if (attrs & _KPI_NAME_HINTS) and (attrs & _KPI_VALUE_HINTS):
            return True
    return False


def _lifecycle_events(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [event for event in events if is_run_lifecycle_event(event)]


def _has_decision_values(events: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """EP-decision values actually observed (allow/deny/…), as normalized set."""
    seen: set[str] = set()
    for event in events:
        attrs = event.get("attributes") or {}
        for key, value in attrs.items():
            if (
                _norm(key) in _EP_FIELD_HINTS
                and isinstance(value, str)
                and _norm(value) in _EP_DECISION_VALUES
            ):
                seen.add(_norm(value))
    return frozenset(seen)


def capability_row(
    *,
    source: Mapping[str, Any],
    artifact_events: Sequence[Mapping[str, Any]],
    bound_event_ids: frozenset[str],
    run_start_event_ids: frozenset[str],
) -> dict[str, str]:
    """The six-fact capability row for one source.

    States: OBSERVED (fact data seen in raw/mapped form), MAPPED (fact
    fields projected into canonical events), QUALIFIED (fact present on
    run-bound qualified evidence), ONSITE_VERIFY (hints on unmapped
    source — promising, unproven), NOT_FOUND, NOT_APPLICABLE.
    """
    fields = _field_set(list(source.get("fieldPaths") or ()))
    mapped = str(source.get("mappingState") or "") in ("APPROVED_USER", "PREMAPPED")
    blocked = str(source.get("profileState") or "") == "FAILED" or str(
        source.get("format") or ""
    ) == "opaque"
    bound = [
        event
        for event in artifact_events
        if str(event.get("eventId")) in bound_event_ids
    ]
    lifecycle = _lifecycle_events(artifact_events)
    lifecycle_bound = [
        event for event in lifecycle if str(event.get("eventId")) in bound_event_ids
    ]
    start_qualified = any(
        str(event.get("eventId")) in run_start_event_ids for event in artifact_events
    )

    def _cell(
        *,
        qualified: bool = False,
        canonical_fact: bool = False,
        field_hint: bool = False,
    ) -> str:
        return _capability_cell(
            qualified=qualified,
            canonical_fact=canonical_fact,
            mapped=mapped,
            field_hint=field_hint,
            source_blocked=blocked,
        )

    identity_on_events = any(event_identifiers(event) for event in artifact_events)
    run_id_hint = bool(_hinted(fields, _RUN_ID_HINTS))

    start_fact = bool(lifecycle) or start_qualified
    start_hint = bool(_hinted(fields, _RUN_START_FIELD_HINTS))
    if not start_fact and not start_hint:
        # Event-type values that *look* like start signals count as hints.
        for event in artifact_events:
            attrs = event.get("attributes") or {}
            for key, value in attrs.items():
                if (
                    _norm(key) in _EVENT_TYPE_FIELD_KEYS
                    and isinstance(value, str)
                    and _norm(value) in _RUN_START_VALUE_HINTS
                ):
                    start_hint = True

    c7_hint = bool(_hinted(fields, _EVENT_TYPE_HINTS | _TIMESTAMP_HINTS))
    usage_hint = bool(_hinted(fields, _TOKEN_HINTS) and _hinted(fields, _MODEL_CALL_HINTS))
    usage_fact = _usage_fact_on(artifact_events)
    kpi_hint = bool(_hinted(fields, _KPI_NAME_HINTS) and _hinted(fields, _KPI_VALUE_HINTS))
    kpi_fact = _metric_fact_on(artifact_events)
    ep_hint = bool(_hinted(fields, _EP_FIELD_HINTS)) or bool(
        _has_decision_values(artifact_events)
    )

    return {
        "runIdentity": _cell(
            qualified=any(event_identifiers(event) for event in bound),
            canonical_fact=identity_on_events,
            field_hint=run_id_hint,
        ),
        "runStart": _cell(
            qualified=start_qualified or bool(lifecycle_bound),
            canonical_fact=start_fact,
            field_hint=start_hint,
        ),
        "c7Events": _cell(
            qualified=bool(bound),
            canonical_fact=bool(artifact_events),
            field_hint=c7_hint,
        ),
        "c9Kpi": _cell(
            qualified=bool(bound) and _metric_fact_on(bound),
            canonical_fact=kpi_fact,
            field_hint=kpi_hint,
        ),
        "c16Tokens": _cell(
            qualified=bool(bound) and _usage_fact_on(bound),
            canonical_fact=usage_fact,
            field_hint=usage_hint,
        ),
        "enforcementPoint": _cell(
            qualified=False,  # EP qualification is operator/HAIEC work — never inferred
            canonical_fact=ep_hint and bool(artifact_events),
            field_hint=ep_hint,
        ),
    }


def _last_observed(events: Sequence[Mapping[str, Any]]) -> str | None:
    times = sorted(
        str(event.get("eventTime"))
        for event in events
        if event.get("eventTime")
    )
    return times[-1] if times else None


def _registry_next_action(
    status: str, source: Mapping[str, Any], row: dict[str, str]
) -> str:
    if status == "BLOCKED":
        return (
            "Cannot be parsed — export this source in a supported format "
            "(JSON/JSONL/CSV/YAML/LOG/OTLP) or keep it preserved as opaque evidence."
        )
    if row["runStart"] in ("OBSERVED", "ONSITE_VERIFY"):
        return (
            "Possible run-start signal present — map/approve the field and "
            "declare semantic RUN_START so it can qualify."
        )
    if status == "PROFILED":
        return "Review and approve the available mapping proposal."
    if status == "LIMITED":
        return (
            "Not mapped yet — approve a proposal or capture an alternate export; "
            "unmapped records stay preserved, never silently promoted."
        )
    if status == "MAPPED":
        return "Mapping approved — verify canonical events and run binding."
    return str(source.get("nextAction") or "Verify this source's role in the run.")


def source_registry_row(
    *,
    source: Mapping[str, Any],
    artifact_events: Sequence[Mapping[str, Any]],
    bound_event_ids: frozenset[str],
    run_start_event_ids: frozenset[str],
) -> dict[str, Any]:
    """One Source Intake Registry row — readiness metadata, not new storage."""
    fields = _field_set(list(source.get("fieldPaths") or ()))
    status = _source_status(source)
    capabilities = capability_row(
        source=source,
        artifact_events=artifact_events,
        bound_event_ids=bound_event_ids,
        run_start_event_ids=run_start_event_ids,
    )
    parsed = int(source.get("parsedRecordCount") or 0)
    events_count = int(source.get("canonicalEventCount") or 0)
    run_id_fields = sorted(
        {
            str(k)
            for event in artifact_events
            for k in event_identifiers(event)
        }
        | {_norm(f) for f in _hinted(fields, _RUN_ID_HINTS)}
    )
    ep_fields = sorted(_hinted(fields, _EP_FIELD_HINTS))
    return {
        "sourceRef": source.get("artifactId"),
        "sourceType": source.get("format"),
        "displayName": source.get("path"),
        "connectionMode": "FILE_IMPORT",
        "adapterRef": source.get("syntaxAdapterId"),
        "mappingProfileRef": source.get("approvedProfileId"),
        "status": status,
        "lastObservedAt": _last_observed(artifact_events),
        "recordsObserved": source.get("recordCount"),
        "qualifiedRecords": events_count,
        "unmappedRecords": max(parsed - events_count, 0),
        "quarantinedRecords": source.get("failedRecordCount"),
        "controlsSupported": [
            code
            for code, cell in (
                (CONTROL7_CODE, capabilities["c7Events"]),
                (CONTROL9_CODE, capabilities["c9Kpi"]),
                (CONTROL16_CODE, capabilities["c16Tokens"]),
            )
            if cell in ("OBSERVED", "MAPPED", "QUALIFIED")
        ],
        "capabilities": capabilities,
        "runIdentityFields": run_id_fields,
        "enforcementPointFields": ep_fields,
        "runStartCapability": capabilities["runStart"],
        "mappingState": source.get("mappingState"),
        "evidenceQualification": (source.get("evidenceQualification") or {}).get(
            "state"
        ),
        "limitations": list(source.get("limitations") or ()),
        "nextAction": _registry_next_action(status, source, capabilities),
    }


def source_registry(
    *,
    overview_sources: Sequence[Mapping[str, Any]],
    canonical_events: Sequence[Mapping[str, Any]],
    run_resolutions: Sequence[Mapping[str, Any]],
    run_activities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The Source Intake Registry — all committed sources, readiness rows."""
    bound: set[str] = set()
    for resolution in run_resolutions:
        bound.update(str(ref) for ref in (resolution.get("qualifiedEventRefs") or ()))
    start_ids: set[str] = set()
    for activity in run_activities:
        start_ids.update(str(ref) for ref in (activity.get("startEvidenceRefs") or ()))
    bound_ids = frozenset(bound)
    start_event_ids = frozenset(start_ids)
    rows = [
        source_registry_row(
            source=source,
            artifact_events=_artifact_events(
                canonical_events, str(source.get("artifactId") or "")
            ),
            bound_event_ids=bound_ids,
            run_start_event_ids=start_event_ids,
        )
        for source in overview_sources
    ]
    return {
        "schemaVersion": SOURCE_REGISTRY_SCHEMA,
        "sources": rows,
        "counts": {
            status: sum(1 for row in rows if row["status"] == status)
            for status in SOURCE_STATUSES
        },
    }


def capability_matrix(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Source × fact matrix — first-hour capability overview."""
    facts = [
        "runIdentity",
        "runStart",
        "c7Events",
        "c9Kpi",
        "c16Tokens",
        "enforcementPoint",
    ]
    return {
        "schemaVersion": CAPABILITY_MATRIX_SCHEMA,
        "facts": facts,
        "rows": [
            {
                "sourceRef": row["sourceRef"],
                "displayName": row["displayName"],
                "status": row["status"],
                **{fact: row["capabilities"][fact] for fact in facts},
            }
            for row in (registry.get("sources") or ())
        ],
    }


# --------------------------------------------------------------------------
# Enforcement-point discovery
# --------------------------------------------------------------------------

_EP_NAME_HINTS = frozenset({"gateway", "proxy", "enforcement", "guardrail"})


def _ep_candidates_from_events(
    canonical_events: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Observed interception-point candidates — evidence-only, no lab labeling."""
    candidates: dict[str, dict[str, Any]] = {}

    def _add(ref: str, *, basis: str, event: Mapping[str, Any]) -> None:
        row = candidates.setdefault(
            ref,
            {
                "enforcementPointRef": ref,
                "basis": basis,
                "sourceRefs": set(),
                "zonesSeen": set(),
                "agentsSeen": set(),
                "eventTypes": set(),
                "decisionValuesSeen": set(),
                "evidenceRefs": [],
                "state": "OBSERVED",
            },
        )
        for raw in event.get("rawRecordRefs") or ():
            if raw.get("artifactId"):
                row["sourceRefs"].add(str(raw["artifactId"]))
        attrs = event.get("attributes") or {}
        for key, value in attrs.items():
            if _norm(key) == "zone" and isinstance(value, str):
                row["zonesSeen"].add(value)
        for actor in event.get("actorRefs") or ():
            actor_text = str(actor)
            if "AGENT" in actor_text.upper():
                row["agentsSeen"].add(actor_text.split(":", 1)[-1])
        native = event.get("nativeEventType")
        if native:
            row["eventTypes"].add(str(native))
        for key, value in attrs.items():
            if (
                _norm(key) in _EP_FIELD_HINTS
                and isinstance(value, str)
                and _norm(value) in _EP_DECISION_VALUES
            ):
                row["decisionValuesSeen"].add(_norm(value))
        if len(row["evidenceRefs"]) < 8 and event.get("eventId"):
            row["evidenceRefs"].append(str(event["eventId"]))

    for event in canonical_events:
        attrs = event.get("attributes") or {}
        for key, value in attrs.items():
            if _norm(key) in _EP_FIELD_HINTS and isinstance(value, str) and value:
                if _norm(value) in _EP_DECISION_VALUES:
                    # A decision *value* is not a point name — point is the
                    # artifact boundary that produced the record.
                    for raw in event.get("rawRecordRefs") or ():
                        artifact = str(raw.get("artifactId") or "")
                        if artifact:
                            _add(
                                f"decision-boundary:{artifact}",
                                basis=f"DECISION_FIELD:{key}",
                                event=event,
                            )
                else:
                    _add(str(value), basis=f"FIELD:{key}", event=event)
        for actor in event.get("actorRefs") or ():
            actor_text = str(actor)
            if any(hint in actor_text.lower() for hint in _EP_NAME_HINTS):
                _add(actor_text, basis="ACTOR_NAME_HINT", event=event)

    return candidates


def _ep_controls(row: Mapping[str, Any]) -> list[str]:
    controls = [CONTROL7_CODE]
    if row["decisionValuesSeen"]:
        controls.append(CONTROL16_CODE)
    return controls


def enforcement_point_discovery(
    *,
    canonical_events: Sequence[Mapping[str, Any]],
    declared_points: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Observed + operator-declared enforcement-point candidates.

    ``OBSERVED`` = evidence attributes/actors hint at an interception point.
    ``DECLARED`` = operator-entered in the discovery workspace.
    Nothing reaches ``QUALIFIED`` from these projections — that requires
    operator verification against the real lab, which HAIEC may later use
    for assessed scope and guardrail positioning.
    """
    observed = _ep_candidates_from_events(canonical_events)
    declared_names = {
        str(ep.get("point") or "").strip() for ep in declared_points if ep.get("point")
    }
    rows: list[dict[str, Any]] = []
    for ref, row in sorted(observed.items()):
        state = "DECLARED" if ref in declared_names else row["state"]
        rows.append(
            {
                "enforcementPointRef": ref,
                "basis": row["basis"],
                "sourceRefs": sorted(row["sourceRefs"]),
                "zonesSeen": sorted(row["zonesSeen"]),
                "agentsSeen": sorted(row["agentsSeen"]),
                "eventTypes": sorted(row["eventTypes"]),
                "decisionValuesSeen": sorted(row["decisionValuesSeen"]),
                "controlsPotentiallySupported": _ep_controls(row),
                "evidenceRefs": list(row["evidenceRefs"]),
                "state": state,
            }
        )
    for ep in declared_points:
        name = str(ep.get("point") or "").strip()
        if not name or name in observed:
            continue
        rows.append(
            {
                "enforcementPointRef": name,
                "basis": "OPERATOR_DECLARED",
                "sourceRefs": [],
                "zonesSeen": [],
                "agentsSeen": [],
                "eventTypes": [],
                "decisionValuesSeen": [],
                "controlsPotentiallySupported": list(ep.get("candidateControls") or ()),
                "evidenceRefs": [],
                "state": "DECLARED",
            }
        )
    return {
        "schemaVersion": EP_DISCOVERY_SCHEMA,
        "points": rows,
        "counts": {state: sum(1 for r in rows if r["state"] == state) for state in EP_STATES},
        "note": (
            "Observed candidates are evidence hints only — verify each point "
            "against the real lab before HAIEC relies on it."
        ),
    }


# --------------------------------------------------------------------------
# Control acquisition feasibility — READY / LIMITED / BLOCKED from source facts
# --------------------------------------------------------------------------


def _row(state: str, missing: Sequence[str], detail: str) -> dict[str, Any]:
    return {"state": state, "missingFacts": list(missing), "detail": detail}


def _c7_source_feasibility(
    *,
    bound_events: Sequence[Mapping[str, Any]],
    manifests: Sequence[Mapping[str, Any]],
    ep_discovery: Mapping[str, Any],
    declared_run: bool,
) -> dict[str, Any]:
    missing: list[str] = []
    if not declared_run:
        missing.append("DECLARED_RUN")
    if not bound_events:
        missing.append("BOUND_RUN_EVENTS")
    has_timestamps = any(
        event.get("eventTime") or event.get("nativeTimestamp") for event in bound_events
    )
    if bound_events and not has_timestamps:
        missing.append("EVENT_TIMESTAMPS")
    ep_points = ep_discovery.get("points") or ()
    if not ep_points:
        missing.append("ENFORCEMENT_POINT_CANDIDATES")
    if not manifests:
        missing.append("EXPECTED_EVENT_BASIS")
    if "BOUND_RUN_EVENTS" in missing or "DECLARED_RUN" in missing:
        return _row(
            "BLOCKED",
            missing,
            "C7 needs a declared run with deterministically bound events. "
            "Missing: " + ", ".join(missing),
        )
    if missing:
        return _row(
            "LIMITED",
            missing,
            "Bound events exist; strengthen: " + ", ".join(missing),
        )
    return _row(
        "READY",
        [],
        "Run-bound events with timestamps, expected-event basis and "
        "enforcement-point candidates are present.",
    )


def _c9_source_feasibility(
    *,
    kpi_candidate: bool,
    fields: frozenset[str],
    profiles: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    missing: list[str] = []
    if not kpi_candidate:
        missing.append("KPI_CANDIDATE")
    else:
        if not _hinted(fields, _KPI_UNIT_HINTS):
            missing.append("KPI_UNIT")
        if not _hinted(fields, _KPI_DIRECTION_HINTS):
            missing.append("KPI_DIRECTION")
        if not _hinted(fields, _KPI_WINDOW_HINTS):
            missing.append("OBSERVATION_WINDOW")
    if not baselines:
        missing.append("BASELINE_CANDIDATE")
    if not profiles:
        missing.append("METRIC_PROFILE")
    if "KPI_CANDIDATE" in missing:
        return _row(
            "BLOCKED",
            missing,
            "No KPI/metric candidate observed in any source. "
            "Capture a digital-twin or KPI export first.",
        )
    if missing:
        return _row(
            "LIMITED",
            missing,
            "KPI candidate present; qualify: " + ", ".join(missing),
        )
    return _row(
        "READY",
        [],
        "KPI candidate with unit, direction, window and baseline "
        "candidates present — onsite selection still decides the metric.",
    )


def _c16_source_feasibility(
    *,
    fields: frozenset[str],
    bound_events: Sequence[Mapping[str, Any]],
    declared_run: bool,
) -> dict[str, Any]:
    missing: list[str] = []
    if not _hinted(fields, _TOKEN_HINTS):
        missing.append("TOKEN_USAGE_FIELDS")
    if not _hinted(fields, _MODEL_CALL_HINTS):
        missing.append("MODEL_CALL_IDENTITY")
    if not _hinted(fields, _RETRY_HINTS):
        missing.append("RETRY_IDENTITY")
    if not declared_run or not bound_events:
        missing.append("RUN_BINDING")
    if "TOKEN_USAGE_FIELDS" in missing:
        return _row(
            "BLOCKED",
            missing,
            "No token-usage fields in any source — capture the shared "
            "model gateway export first.",
        )
    if missing:
        return _row(
            "LIMITED",
            missing,
            "Usage fields present; qualify: " + ", ".join(missing)
            + ". Missing usage is not zero tokens; duplicate telemetry is "
            "not a retry.",
        )
    return _row(
        "READY",
        [],
        "Model-call identity, tokens, retry identity and run binding are "
        "all present on qualified sources.",
    )


def control_source_feasibility(
    *,
    canonical_events: Sequence[Mapping[str, Any]],
    overview_sources: Sequence[Mapping[str, Any]],
    resolution: Mapping[str, Any] | None,
    declared_run: bool,
    manifests: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    ep_discovery: Mapping[str, Any],
) -> dict[str, Any]:
    """READY / LIMITED / BLOCKED per control from *source facts* present now.

    Complements ``control_feasibility`` (measurement-pipeline readiness):
    this answers "can the current sources even produce what the control
    needs?" — with the exact missing facts, before any measurement runs.
    """
    bound_ids = {
        str(ref) for ref in ((resolution or {}).get("qualifiedEventRefs") or ())
    }
    bound_events = [
        event for event in canonical_events if str(event.get("eventId")) in bound_ids
    ]
    all_fields: set[str] = set()
    for source in overview_sources:
        all_fields.update(_norm(p) for p in (source.get("fieldPaths") or ()))
    for event in canonical_events:
        all_fields.update(_norm(k) for k in (event.get("attributes") or {}))
    fields = frozenset(all_fields)

    kpi_candidate = bool(
        _hinted(fields, _KPI_NAME_HINTS) and _hinted(fields, _KPI_VALUE_HINTS)
    ) or _metric_fact_on(canonical_events)
    return {
        "schemaVersion": ACQUISITION_FEASIBILITY_SCHEMA,
        "controls": {
            "C7": _c7_source_feasibility(
                bound_events=bound_events,
                manifests=manifests,
                ep_discovery=ep_discovery,
                declared_run=declared_run,
            ),
            "C9": _c9_source_feasibility(
                kpi_candidate=kpi_candidate,
                fields=fields,
                profiles=profiles,
                baselines=baselines,
            ),
            "C16": _c16_source_feasibility(
                fields=fields,
                bound_events=bound_events,
                declared_run=declared_run,
            ),
        },
    }


# --------------------------------------------------------------------------
# First-hour dashboard — compact deterministic status + next actions
# --------------------------------------------------------------------------


def _run_identity_state(
    runs: Sequence[Mapping[str, Any]],
    resolutions: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not runs:
        return "NOT_RESOLVED", []
    per_run = []
    states = []
    for run in runs:
        rid = str(run.get("runId") or "")
        state = str(
            (resolutions.get(rid) or {}).get("resolutionState")
            or run.get("resolutionState")
            or "NOT_RESOLVED"
        )
        states.append(state)
        per_run.append({"runId": rid, "resolutionState": state})
    if "AMBIGUOUS" in states:
        overall = "AMBIGUOUS"
    elif "NOT_RESOLVED" in states:
        overall = "NOT_RESOLVED" if all(s == "NOT_RESOLVED" for s in states) else "PARTIAL"
    elif "PARTIAL" in states:
        overall = "PARTIAL"
    else:
        overall = "RESOLVED"
    return overall, per_run


def _run_start_state(
    runs: Sequence[Mapping[str, Any]],
    run_activities: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not runs:
        return "NOT_ESTABLISHED", []
    per_run = []
    states = []
    for run in runs:
        rid = str(run.get("runId") or "")
        activity = run_activities.get(rid) or {}
        state = str(activity.get("startState") or "NOT_ESTABLISHED")
        states.append(state)
        per_run.append(
            {
                "runId": rid,
                "startState": state,
                "runStartedAt": activity.get("runStartedAt"),
                "earliestObservedActivityAt": activity.get(
                    "earliestObservedActivityAt"
                ),
            }
        )
    if "CONFLICTING" in states:
        overall = "CONFLICTING"
    elif "NOT_ESTABLISHED" in states:
        overall = "NOT_ESTABLISHED"
    else:
        overall = "ESTABLISHED"
    return overall, per_run


def _next_actions(
    *,
    registry: Mapping[str, Any],
    run_identity: str,
    run_start: str,
    feasibility: Mapping[str, Any],
    ep_counts: Mapping[str, int],
    run_start_candidates: Sequence[str],
) -> list[dict[str, Any]]:
    """Deterministic prioritized actions — no LLM involved."""
    actions: list[dict[str, Any]] = []

    def _add(priority: str, code: str, action: str) -> None:
        actions.append({"priority": priority, "code": code, "action": action})

    sources = registry.get("sources") or ()
    if not sources:
        _add(
            "P0",
            "CAPTURE_SAMPLES",
            "Capture one representative sample per lab source and commit "
            "it — nothing can be profiled until evidence exists.",
        )
        return actions
    unmapped = [s for s in sources if s["status"] in ("LIMITED", "PROFILED")]
    if unmapped:
        _add(
            "P0",
            "MAPPING_REVIEW",
            "Approve or resolve mappings for: "
            + ", ".join(str(s["displayName"]) for s in unmapped[:4])
            + ".",
        )
    if run_identity != "RESOLVED":
        _add(
            "P0",
            "RUN_IDENTITY",
            "Identify the deterministic run identifier (runId/traceId/"
            "requestId/scenarioRunId) and declare the assessed run.",
        )
    if run_start == "NOT_ESTABLISHED":
        hint = (
            " Candidate signals: " + ", ".join(run_start_candidates[:4]) + "."
            if run_start_candidates
            else ""
        )
        _add(
            "P0",
            "RUN_START",
            "Find and qualify the explicit assessed-run start signal "
            "(RUN_STARTED event or mapping-declared RUN_START field) before "
            "freezing scored policies." + hint,
        )
    elif run_start == "CONFLICTING":
        _add(
            "P0",
            "RUN_START_CONFLICT",
            "Two authoritative run-start facts conflict — reconcile the "
            "source semantics; do not pick the earlier timestamp.",
        )
    controls = feasibility.get("controls") or {}
    c9 = controls.get("C9") or {}
    if c9.get("state") == "BLOCKED":
        _add("P0", "C9_KPI", "Identify the C9 KPI source (digital twin/KPI export).")
    elif c9.get("state") == "LIMITED":
        _add(
            "P0",
            "C9_KPI_QUALIFY",
            "Qualify KPI facts: " + ", ".join(c9.get("missingFacts") or ()) + ".",
        )
    c16 = controls.get("C16") or {}
    if c16.get("state") == "BLOCKED":
        _add(
            "P0",
            "C16_GATEWAY",
            "Capture the shared model gateway usage export (call/model/"
            "tokens/retries).",
        )
    elif c16.get("state") == "LIMITED":
        _add(
            "P0",
            "C16_QUALIFY",
            "Qualify usage facts: "
            + ", ".join(c16.get("missingFacts") or ())
            + ".",
        )
    c7 = controls.get("C7") or {}
    if c7.get("state") == "BLOCKED":
        _add(
            "P1",
            "C7_EVENTS",
            "Establish event visibility for the declared three-zone scope.",
        )
    elif "ENFORCEMENT_POINT_CANDIDATES" in (c7.get("missingFacts") or ()):
        _add(
            "P1",
            "EP_VISIBILITY",
            "Verify enforcement-point telemetry (gateway/proxy/decision "
            "fields) for C7 assessed scope.",
        )
    elif not ep_counts.get("OBSERVED") and not ep_counts.get("DECLARED"):
        _add(
            "P1",
            "EP_VISIBILITY",
            "No enforcement-point candidates observed or declared yet.",
        )
    if not actions:
        _add(
            "P1",
            "MEASURE",
            "Sources look ready — generate preliminary C7/C9/C16 bundles "
            "and verify HAIEC ingestion.",
        )
    return actions


def first_hour_dashboard(
    *,
    registry: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    resolutions: Mapping[str, Mapping[str, Any]],
    run_activities: Mapping[str, Mapping[str, Any]],
    ep_discovery: Mapping[str, Any],
    feasibility: Mapping[str, Any],
) -> dict[str, Any]:
    """The compact first-hour view: sources, run identity, run start,
    enforcement points, control readiness, next actions."""
    run_identity, run_identity_rows = _run_identity_state(runs, resolutions)
    run_start, run_start_rows = _run_start_state(runs, run_activities)
    ep_counts = dict(ep_discovery.get("counts") or {})
    counts = registry.get("counts") or {}
    sources = registry.get("sources") or ()
    start_candidates = [
        str(row["displayName"])
        for row in sources
        if row.get("runStartCapability") in ("OBSERVED", "ONSITE_VERIFY", "MAPPED")
    ]
    receiving = sum(
        1 for row in sources if int(row.get("recordsObserved") or 0) > 0
    )
    ready = sum(1 for row in sources if row.get("status") == "READY")
    actions = _next_actions(
        registry=registry,
        run_identity=run_identity,
        run_start=run_start,
        feasibility=feasibility,
        ep_counts=ep_counts,
        run_start_candidates=start_candidates,
    )
    timed_sources = [
        str(row.get("displayName") or row.get("artifactId") or "?")
        for row in sources
        if int(row.get("canonicalEventCount") or row.get("recordsObserved") or 0) > 0
    ]
    return {
        "schemaVersion": FIRST_HOUR_SCHEMA,
        "sources": {
            "total": len(sources),
            "receivingData": receiving,
            "ready": ready,
            "limited": counts.get("LIMITED", 0),
            "blocked": counts.get("BLOCKED", 0),
        },
        # Time/clock integrity — a cross-system timing comparison is never
        # authoritative merely because two timestamps parse. Skew is
        # external operator knowledge: LogSense can never promote this to
        # ESTABLISHED from logs alone.
        "clockIntegrity": {
            "state": (
                "NOT_ESTABLISHED" if len(timed_sources) > 1 else "NOT_APPLICABLE"
            ),
            "timedSources": timed_sources,
            "systemsToCheck": [
                "ServiceNow",
                "AgentCore / AWS",
                "OTel / CloudWatch",
                "model gateway",
                "Digital Twin / KPI source",
            ],
            "capturePerSource": [
                "UTC or local timestamps",
                "authoritative clock source",
                "synchronized infrastructure clock",
                "timestamp precision",
                "expected cross-system skew",
            ],
            "note": (
                "Record the clock basis per source before relying on "
                "cross-system timing. If comparability cannot be "
                "established it stays a visible limitation — never silent."
            ),
        },
        "runIdentity": {"state": run_identity, "runs": run_identity_rows},
        "runStart": {
            "state": run_start,
            "runs": run_start_rows,
            "candidateSources": start_candidates,
        },
        "enforcementPoints": {
            "observed": ep_counts.get("OBSERVED", 0),
            "declared": ep_counts.get("DECLARED", 0),
            "points": [
                {"ref": p["enforcementPointRef"], "state": p["state"]}
                for p in (ep_discovery.get("points") or ())
            ],
        },
        "controls": feasibility.get("controls") or {},
        "nextActions": actions,
    }
