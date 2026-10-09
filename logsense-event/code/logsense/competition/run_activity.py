"""Qualified run-activity provenance for competition runs.

After ``resolve_competition_run`` has deterministically bound evidence to a
declared run, this module answers one narrow question about that run:

    did a qualified source fact explicitly establish when the assessed
    run/activity actually began?

The output is the shared ``competition-run-activity/0.1`` provenance block.
It is deliberately fail-closed:

- ``runStartedAt`` is set only when qualified, run-bound evidence carries an
  *explicit* run-start semantic — a producer-declared ``RUN_STARTED`` event
  type, a mapping-profile-declared ``RUN_START``/``ASSESSED_ACTIVITY_START``
  semantic, or a normalized adapter fact. Conflicting explicit starts yield
  ``CONFLICTING`` and ``runStartedAt: null``.
- ``earliestObservedActivityAt`` is the earliest ``eventTime`` observed on
  qualified run-bound evidence. It is *observed activity*, never proof of
  run start.

Permanent locks:

- ``RUN_DECLARATION_TIME != RUN_START`` — ``declaration.declaredAt`` is
  operator provenance, never a run-start fact.
- ``EARLIEST_OBSERVED_ACTIVITY != RUN_START`` — the earliest qualified
  timestamp is never promoted into ``runStartedAt``.
- ``TIMESTAMP_PROXIMITY != RUN_MEMBERSHIP`` — run activity is computed only
  over evidence already bound by ``resolve_competition_run``; this module
  never binds evidence itself.
- KPI ``observedAt``, call ``startedAt``/``completedAt``, bundle/measurement
  ``createdAt``, analysis/import/ingestion time, and timestamp proximity
  between records never establish ``runStartedAt``.

LogSense establishes/describes run-activity provenance. HAIEC decides
whether the frozen governing policy preceded the assessed run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

RUN_ACTIVITY_SCHEMA = "competition-run-activity/0.1"

START_STATES = ("ESTABLISHED", "NOT_ESTABLISHED", "CONFLICTING")

# Producer-declared lifecycle vocabulary. Only a record that literally
# declares one of these event types asserts run-start/run-complete meaning —
# generic classes such as EXECUTION_START or AGENT_STARTED do not qualify on
# their own.
RUN_START_EVENT_TYPES = frozenset(
    {"RUN_STARTED", "ASSESSED_RUN_STARTED", "ASSESSED_ACTIVITY_STARTED"}
)
RUN_COMPLETE_EVENT_TYPES = frozenset(
    {"RUN_COMPLETED", "ASSESSED_RUN_COMPLETED", "ASSESSED_ACTIVITY_COMPLETED"}
)

# Mapping-profile semantics (declared on a mapping entry via ``"semantic"``)
# and the normalized-fact vocabulary future source adapters may emit.
RUN_START_SEMANTICS = frozenset({"RUN_START", "ASSESSED_ACTIVITY_START"})
RUN_COMPLETE_SEMANTICS = frozenset({"RUN_COMPLETE", "ASSESSED_ACTIVITY_COMPLETE"})
RUN_ACTIVITY_SEMANTICS = RUN_START_SEMANTICS | RUN_COMPLETE_SEMANTICS

# Canonical attribute carrying mapping-declared run-activity semantics
# (emitted by logsense.adapters.canonical_events.project_canonical_events).
RUN_ACTIVITY_SEMANTIC_ATTRIBUTE = "runActivitySemantics"

_EVENT_TYPE_KEYS = ("eventType", "event_type", "eventtype", "type")

_BASIS_DECLARED_EVENT = "DECLARED_RUN_LIFECYCLE_EVENT"
_BASIS_MAPPED_SEMANTIC = "MAPPED_RUN_ACTIVITY_SEMANTIC"
_BASIS_ADAPTER_FACT = "ADAPTER_NORMALIZED_FACT"


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _event_time(event: Mapping[str, Any]) -> datetime | None:
    """Source-asserted activity time for one canonical event.

    ``eventTime`` is the qualified source timestamp; ``nativeTimestamp`` is
    the unnormalized source field kept for provenance — usable only when it
    parses. ``ingestedAt``/``receivedAt``/``observedAt`` are pipeline or
    observation times and never qualify as activity time here.
    """
    parsed = _parse_time(event.get("eventTime"))
    if parsed is not None:
        return parsed
    return _parse_time(event.get("nativeTimestamp"))


def _declared_types(event: Mapping[str, Any]) -> frozenset[str]:
    """All producer-declared event-type values on the canonical event."""
    found: set[str] = set()
    native = event.get("nativeEventType")
    if isinstance(native, str) and native.strip():
        found.add(native.strip())
    attributes = event.get("attributes") or {}
    if isinstance(attributes, Mapping):
        for key in _EVENT_TYPE_KEYS:
            value = attributes.get(key)
            if isinstance(value, str) and value.strip():
                found.add(value.strip())
    return frozenset(found)


def _mapped_semantics(event: Mapping[str, Any]) -> frozenset[str]:
    attributes = event.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        return frozenset()
    raw = attributes.get(RUN_ACTIVITY_SEMANTIC_ATTRIBUTE)
    if isinstance(raw, str):
        raw = (raw,)
    if not isinstance(raw, Sequence):
        return frozenset()
    return frozenset(str(item) for item in raw) & RUN_ACTIVITY_SEMANTICS


def _marker_bases(event: Mapping[str, Any], *, for_start: bool) -> set[str]:
    """Which explicit run-lifecycle semantics this event asserts."""
    bases: set[str] = set()
    vocabulary = RUN_START_EVENT_TYPES if for_start else RUN_COMPLETE_EVENT_TYPES
    if _declared_types(event) & vocabulary:
        bases.add(_BASIS_DECLARED_EVENT)
    semantics = RUN_START_SEMANTICS if for_start else RUN_COMPLETE_SEMANTICS
    if _mapped_semantics(event) & semantics:
        bases.add(_BASIS_MAPPED_SEMANTIC)
    return bases


def is_run_lifecycle_event(event: Mapping[str, Any]) -> bool:
    """Whether an event carries any run-lifecycle marker — a declared
    RUN_STARTED/RUN_COMPLETED-family event type or a mapping-declared
    run-activity semantic. Lifecycle markers are run-bound provenance, not
    assessed-behavior evidence: they never belong in C7 unexpected-event
    accounting or drafted expected-event manifests."""
    return bool(
        _declared_types(event) & (RUN_START_EVENT_TYPES | RUN_COMPLETE_EVENT_TYPES)
        or _mapped_semantics(event)
    )


def resolve_run_activity(
    canonical_events: Sequence[Mapping[str, Any]] | None,
    run_resolution: Mapping[str, Any] | None,
    *,
    adapter_facts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Compute the shared run-activity provenance for one resolved run.

    Inputs are the already-bound resolution plus the canonical event
    snapshot. ``adapter_facts`` is the normalized seam for future source
    adapters: ``{"semantic": "RUN_START"|..., "timestamp": ...,
    "evidenceRef": ..., "sourceRef": ..., "mappingProfileRef": ...}`` — a
    fact contributes only when its ``evidenceRef`` names a qualified,
    run-bound event.
    """
    resolution = run_resolution or {}
    run_id = str(resolution.get("runId") or "") or None
    qualified = {
        str(ref)
        for ref in (resolution.get("qualifiedEventRefs") or resolution.get("eventRefs") or ())
    }
    events = list(canonical_events or ())

    limitations: list[str] = []
    if run_resolution is None:
        limitations.append("RUN_RESOLUTION_UNAVAILABLE")
    elif canonical_events is None:
        limitations.append("RUN_ACTIVITY_EVIDENCE_SNAPSHOT_UNAVAILABLE")

    # start/complete facts keyed by the asserted instant; corroborating refs
    # for the same instant are preserved rather than deduplicated.
    start_facts: dict[datetime, dict[str, Any]] = {}
    complete_facts: dict[datetime, dict[str, Any]] = {}
    excluded_start_refs: list[str] = []
    missing_timestamp = False

    def _credit(bucket: dict[datetime, dict[str, Any]], at: datetime, *, ref: str, basis: str, source: str | None) -> None:
        entry = bucket.setdefault(at, {"refs": [], "bases": set(), "sources": set()})
        if ref not in entry["refs"]:
            entry["refs"].append(ref)
        entry["bases"].add(basis)
        if source:
            entry["sources"].add(str(source))

    for event in events:
        ref = str(event.get("eventId") or "")
        if not ref:
            continue
        start_bases = _marker_bases(event, for_start=True)
        complete_bases = _marker_bases(event, for_start=False)
        if ref not in qualified:
            # A run-start-looking record that never survived deterministic
            # binding is excluded evidence — it can never establish start.
            if start_bases:
                excluded_start_refs.append(ref)
            continue
        at = _event_time(event)
        for bases, bucket in ((start_bases, start_facts), (complete_bases, complete_facts)):
            if not bases:
                continue
            if at is None:
                missing_timestamp = True
                continue
            for basis in bases:
                _credit(bucket, at, ref=ref, basis=basis, source=event.get("sourceRef"))

    for fact in adapter_facts or ():
        if not isinstance(fact, Mapping):
            continue
        ref = str(fact.get("evidenceRef") or "")
        semantic = str(fact.get("semantic") or "")
        source = fact.get("sourceRef")
        if semantic not in RUN_ACTIVITY_SEMANTICS:
            limitations.append("RUN_ACTIVITY_FACT_UNKNOWN_SEMANTIC")
            continue
        bucket = start_facts if semantic in RUN_START_SEMANTICS else complete_facts
        if ref not in qualified:
            excluded_start_refs.append(ref or "(adapter-fact)")
            continue
        at = _parse_time(fact.get("timestamp"))
        if at is None:
            missing_timestamp = True
            continue
        _credit(bucket, at, ref=ref, basis=_BASIS_ADAPTER_FACT, source=source)

    # Observed activity window — eventTime over qualified events only.
    earliest: datetime | None = None
    latest: datetime | None = None
    earliest_refs: list[str] = []
    latest_refs: list[str] = []
    source_refs: set[str] = set()
    for event in events:
        ref = str(event.get("eventId") or "")
        if ref not in qualified:
            continue
        at = _event_time(event)
        if at is None:
            continue
        if event.get("sourceRef"):
            source_refs.add(str(event["sourceRef"]))
        if earliest is None or at < earliest:
            earliest, earliest_refs = at, [ref]
        elif at == earliest:
            earliest_refs.append(ref)
        if latest is None or at > latest:
            latest, latest_refs = at, [ref]
        elif at == latest:
            latest_refs.append(ref)

    if earliest is None and qualified:
        limitations.append("NO_QUALIFIED_TIMED_ACTIVITY")

    observed_refs = sorted(set(earliest_refs) | set(latest_refs))
    distinct_starts = sorted(start_facts)

    if not distinct_starts:
        start_state = "NOT_ESTABLISHED"
        run_started_at = None
        start_basis: list[str] = []
        start_refs: list[str] = []
        limitations.append("RUN_START_NOT_ESTABLISHED")
    elif len(distinct_starts) > 1:
        # Two or more explicit qualified starts disagree — never pick one.
        start_state = "CONFLICTING"
        run_started_at = None
        start_basis = sorted(
            {b for entry in start_facts.values() for b in entry["bases"]}
        )
        start_refs = sorted(
            {ref for entry in start_facts.values() for ref in entry["refs"]}
        )
        limitations.append("RUN_START_EVIDENCE_CONFLICT")
    else:
        entry = start_facts[distinct_starts[0]]
        start_basis = sorted(entry["bases"])
        start_refs = sorted(entry["refs"])
        source_refs.update(entry["sources"])
        if earliest is not None and distinct_starts[0] > earliest:
            # An asserted start after already-qualified run activity cannot
            # be the real start — fail closed instead of trusting it.
            start_state = "CONFLICTING"
            run_started_at = None
            limitations.append("RUN_START_AFTER_QUALIFIED_ACTIVITY")
        else:
            start_state = "ESTABLISHED"
            run_started_at = _iso(distinct_starts[0])

    run_completed_at: str | None = None
    complete_times = sorted(complete_facts)
    if len(complete_times) == 1:
        run_completed_at = _iso(complete_times[0])
        source_refs.update(complete_facts[complete_times[0]]["sources"])
    elif len(complete_times) > 1:
        limitations.append("RUN_COMPLETE_EVIDENCE_CONFLICT")

    if excluded_start_refs:
        limitations.append("RUN_START_CANDIDATE_NOT_QUALIFIED")
    if missing_timestamp:
        limitations.append("RUN_ACTIVITY_FACT_MISSING_TIMESTAMP")

    return {
        "schemaVersion": RUN_ACTIVITY_SCHEMA,
        "runId": run_id,
        "startState": start_state,
        "runStartedAt": run_started_at,
        "runCompletedAt": run_completed_at,
        "earliestObservedActivityAt": _iso(earliest) if earliest is not None else None,
        "latestObservedActivityAt": _iso(latest) if latest is not None else None,
        "startBasis": start_basis,
        "startEvidenceRefs": start_refs,
        "observedActivityEvidenceRefs": observed_refs,
        "excludedStartCandidateRefs": sorted(set(excluded_start_refs)),
        "sourceRefs": sorted(source_refs),
        "limitations": limitations,
    }
