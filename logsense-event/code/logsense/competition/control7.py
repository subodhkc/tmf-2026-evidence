"""Control 7 — AIA-LOG-001 Event Recording measurement.

Deterministic reconciliation between an expected-event manifest and the
canonical events resolved to a competition run. The measurement answers:

    expected vs observed, what matched, what is missing, what is unexpected
    or duplicated, whether the observed order agrees with the expected
    order, and what timing gaps occurred between consecutive events.

This module never issues a governance verdict — ``verdict`` stays ``None``
and ``verdictOwner`` is ``HAIEC``. Invariants preserved here:

- a missing event is not proven event absence;
- a sequence divergence is not a root cause;
- a measured gap violation is a measurement fact, not SATISFIED/NOT
  SATISFIED.

Matching precedence (all deterministic, first satisfied wins):

1. ``eventId`` exact identity,
2. identifier-kind equality on ``correlationIds``/attributes
   (``traceId``, ``requestId``, ``sessionId``, ``modelCallId``,
   ``toolCallId``, ``actionCorrelationId``, …),
3. ``eventType`` against ``eventClass``/``nativeEventType``/event-type
   attributes,
4. ``actorId`` against ``actorRefs``/actor attributes,
5. ``operation`` against ``operation.nativeOperation``/operation
   attributes,
6. any other match key against canonical ``attributes[key]``.

Expected events are consumed in manifest ordinal order; each consumes the
earliest still-unconsumed observed event satisfying every declared match
field. A second observed event satisfying an already-satisfied expected
event is reported under ``duplicates`` — never silently absorbed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from logsense.competition.expected_events import EXPECTED_MANIFEST_SCHEMA, normalize_manifest
from logsense.competition.run import normalize_identifier_kind
from logsense.competition.run_activity import is_run_lifecycle_event

CONTROL7_CODE = "AIA-LOG-001"
CONTROL7_MEASUREMENT_SCHEMA = "control7-event-recording/0.1"

_EVENT_TYPE_ATTRS = ("eventType", "event_type")
_ACTOR_ATTRS = ("actorId", "actor", "agent", "agent_id", "principal", "sourceAgent")
_OPERATION_ATTRS = ("operation", "action", "nativeOperation")


def _is_run_lifecycle(event: Mapping[str, Any]) -> bool:
    """Whether an event is a run-lifecycle marker rather than assessed
    behavior. The manifest domain is behavioral events — a RUN_STARTED /
    RUN_COMPLETED record (or a record carrying mapping-declared run-activity
    semantics) is reported under ``runLifecycleEvents`` instead of
    ``unexpectedEvents``, which must mean unexpected assessed behavior."""
    return is_run_lifecycle_event(event)


def _scalar(value: Any) -> str | None:
    if value is None or isinstance(value, (bool, Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _attribute(event: Mapping[str, Any], *keys: str) -> list[str]:
    attributes = event.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        return []
    out: list[str] = []
    for key in keys:
        value = _scalar(attributes.get(key))
        if value is not None and value not in out:
            out.append(value)
    return out


def _candidate_values(event: Mapping[str, Any], match_key: str) -> set[str]:
    """Deterministic observed-side values for one expected match field."""
    kind = normalize_identifier_kind(match_key)
    values: set[str] = set()
    if kind == "eventId":
        ref = _scalar(event.get("eventId"))
        if ref:
            values.add(ref)
    if kind == "eventType":
        for field in ("eventClass", "nativeEventType"):
            value = _scalar(event.get(field))
            if value:
                values.add(value)
        values.update(_attribute(event, *_EVENT_TYPE_ATTRS))
    elif kind == "actorId":
        for ref in event.get("actorRefs") or ():
            text = str(ref)
            values.add(text)
            if ":" in text:
                values.add(text.split(":", 1)[-1])
        values.update(_attribute(event, *_ACTOR_ATTRS))
    elif kind == "operation":
        operation = event.get("operation")
        if isinstance(operation, Mapping):
            value = _scalar(operation.get("nativeOperation"))
            if value:
                values.add(value)
        values.update(_attribute(event, *_OPERATION_ATTRS))
    correlations = event.get("correlationIds") or ()
    for item in correlations:
        if isinstance(item, Mapping) and normalize_identifier_kind(item.get("kind")) == kind:
            value = _scalar(item.get("value"))
            if value:
                values.add(value)
    value = _scalar((event.get("attributes") or {}).get(match_key))
    if value is None:
        value = _scalar((event.get("attributes") or {}).get(kind))
    if value is not None:
        values.add(value)
    return values


def _matches(event: Mapping[str, Any], match: Mapping[str, Any]) -> bool:
    if not match:
        return False
    return all(str(expected) in _candidate_values(event, key) for key, expected in match.items())


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
    return parsed


def _percent(numerator: int, denominator: int) -> float | None:
    """Machine-exact percentage — never rounded.

    Rounding is presentation-only; the bundle feeds HAIEC's evaluator,
    which must compare the exact ratio against frozen thresholds."""
    if denominator == 0:
        return None
    return numerator / denominator * 100


def violates_declared_gap(gap_ms: float, limit_ms: float, comparator: str) -> bool:
    """Declared-limit comparison under the manifest's comparator.

    ``LT``  — the required condition is ``gap < G``; ``gapMs == limit``
    violates. ``LTE`` — the required condition is ``gap <= G``; equality
    does not violate. Any other comparator is a manifest defect — fail
    loudly rather than guessing.
    """
    if comparator == "LT":
        return gap_ms >= limit_ms
    if comparator == "LTE":
        return gap_ms > limit_ms
    raise ValueError(f"unsupported gap comparator: {comparator!r}")


# Assessed-scope source fields — explicit per-record facts only. When a
# source record names the zone/enforcement point an event was observed
# under, those identifiers are projected verbatim; they are never inferred
# or synthesized by the measurement.
_SCOPE_ZONE_KEYS = ("zone", "zoneRef")
_SCOPE_EP_KEYS = ("enforcementPoint", "enforcementPointRef", "pointRef")


def _scope_facts(event: Mapping[str, Any]) -> dict[str, Any]:
    attributes = event.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        return {}
    facts: dict[str, Any] = {}
    for key in _SCOPE_ZONE_KEYS:
        value = attributes.get(key)
        if isinstance(value, str) and value.strip():
            facts["zone"] = value
            break
    for key in _SCOPE_EP_KEYS:
        value = attributes.get(key)
        if isinstance(value, str) and value.strip():
            facts["enforcementPoint"] = value
            break
    return facts


def measure_event_recording(
    *,
    run_resolution: Mapping[str, Any],
    manifest: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile one expected-event manifest against run-scoped events.

    ``run_resolution`` is the ``competition-run-resolution/0.1`` output from
    :func:`logsense.competition.run.resolve_competition_run`. Only events in
    ``run_resolution["qualifiedEventRefs"]`` (``eventRefs`` is the same set,
    kept for compatibility) are measured — ambiguous and unresolved evidence
    can never influence coverage, matching, ordering, or timing. Observed
    order follows the canonical event list.
    """
    if manifest.get("schemaVersion") != EXPECTED_MANIFEST_SCHEMA:
        manifest = normalize_manifest(manifest)
    resolution_state = str(run_resolution.get("resolutionState") or "NOT_RESOLVED")
    run_id = str(run_resolution.get("runId") or manifest.get("runId") or "")
    qualified_refs = run_resolution.get("qualifiedEventRefs")
    if qualified_refs is None:
        qualified_refs = run_resolution.get("eventRefs") or ()
    bound = {str(ref) for ref in qualified_refs}
    excluded_ambiguous = [str(ref) for ref in run_resolution.get("ambiguousEvidenceRefs") or ()]
    excluded_unresolved = [str(ref) for ref in run_resolution.get("unresolvedEvidenceRefs") or ()]
    observed = [event for event in canonical_events if str(event.get("eventId")) in bound]

    expected = list(manifest["events"])
    consumed: dict[str, str] = {}  # observed eventId -> expectedEventId
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    matched_ref: dict[str, str] = {}

    for entry in expected:
        expected_id = str(entry["expectedEventId"])
        chosen: Mapping[str, Any] | None = None
        for event in observed:
            ref = str(event.get("eventId"))
            if ref in consumed:
                continue
            if _matches(event, entry["match"]):
                chosen = event
                break
        if chosen is None:
            missing.append(
                {
                    "expectedEventId": expected_id,
                    "ordinal": entry["ordinal"],
                    "eventType": entry.get("eventType"),
                    "actorId": entry.get("actorId"),
                    "operation": entry.get("operation"),
                    "required": bool(entry.get("required", True)),
                    "reason": "NO_OBSERVED_EVENT_SATISFIES_MATCH",
                    "note": "Missing from this measurement — not proof the event never occurred.",
                }
            )
            continue
        ref = str(chosen.get("eventId"))
        consumed[ref] = expected_id
        matched_ref[expected_id] = ref
        matched.append(
            {
                "expectedEventId": expected_id,
                "ordinal": entry["ordinal"],
                "observedEventRef": ref,
                "observedEventTime": chosen.get("eventTime"),
                "timeQuality": chosen.get("timeQuality"),
                "matchBasis": sorted(str(key) for key in entry["match"]),
                **_scope_facts(chosen),
            }
        )

    duplicates: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    lifecycle: list[dict[str, Any]] = []
    for event in observed:
        ref = str(event.get("eventId"))
        if ref in consumed:
            continue
        if _is_run_lifecycle(event):
            lifecycle.append(
                {
                    "observedEventRef": ref,
                    "eventTime": event.get("eventTime"),
                    "basis": "RUN_LIFECYCLE_MARKER_OUTSIDE_MANIFEST_DOMAIN",
                }
            )
            continue
        fits = [entry["expectedEventId"] for entry in expected if _matches(event, entry["match"])]
        if fits:
            duplicates.append(
                {
                    "expectedEventId": fits[0],
                    "observedEventRef": ref,
                    "basis": "ADDITIONAL_OBSERVED_MATCH_FOR_SATISFIED_EXPECTED_EVENT",
                    **_scope_facts(event),
                }
            )
        else:
            unexpected.append(
                {
                    "observedEventRef": ref,
                    "eventClass": event.get("eventClass"),
                    "eventTime": event.get("eventTime"),
                    "basis": "NO_EXPECTED_EVENT_MATCH",
                    **_scope_facts(event),
                }
            )

    observed_order = {str(event.get("eventId")): index for index, event in enumerate(observed)}
    sequence: list[dict[str, Any]] = []
    for index in range(len(expected) - 1):
        predecessor = expected[index]
        successor = expected[index + 1]
        pred_ref = matched_ref.get(str(predecessor["expectedEventId"]))
        succ_ref = matched_ref.get(str(successor["expectedEventId"]))
        if pred_ref is None and succ_ref is None:
            state = "NOT_ASSESSED"
        elif pred_ref is None:
            state = "MISSING_PREDECESSOR"
        elif succ_ref is None:
            state = "MISSING_SUCCESSOR"
        elif observed_order[pred_ref] < observed_order[succ_ref]:
            state = "MATCHED_ORDER"
        else:
            state = "OUT_OF_ORDER"
        sequence.append(
            {
                "predecessorExpectedEventId": predecessor["expectedEventId"],
                "successorExpectedEventId": successor["expectedEventId"],
                "predecessorObservedRef": pred_ref,
                "successorObservedRef": succ_ref,
                "sequenceState": state,
            }
        )

    timing = manifest.get("timing") or {}
    gap_limit = timing.get("declaredGapLimitMs")
    # R5-04B: the comparator is producer-declared measurement semantics —
    # never HAIEC governing policy. Manifests predating the field keep their
    # historical `<=` behavior but are marked as a compatibility default.
    declared_comparator = timing.get("declaredGapComparator")
    if declared_comparator is not None:
        effective_comparator = str(declared_comparator)
        comparator_source = "MANIFEST"
    elif gap_limit is not None:
        effective_comparator = "LTE"
        comparator_source = "LEGACY_DEFAULT"
    else:
        effective_comparator = None
        comparator_source = None
    event_by_ref = {str(event.get("eventId")): event for event in observed}
    timing_gaps: list[dict[str, Any]] = []
    for pair in sequence:
        pred_ref = pair["predecessorObservedRef"]
        succ_ref = pair["successorObservedRef"]
        if pred_ref is None or succ_ref is None:
            continue
        prev_event = event_by_ref[pred_ref]
        next_event = event_by_ref[succ_ref]
        prev_time = _parse_time(prev_event.get("eventTime"))
        next_time = _parse_time(next_event.get("eventTime"))
        gap_ms: float | None = None
        gap_state = "NOT_MEASURED"
        if prev_time is not None and next_time is not None:
            gap_ms = round((next_time - prev_time).total_seconds() * 1000, 3)
            gap_state = "MEASURED"
        violates: bool | None = None
        if gap_ms is not None and gap_limit is not None and effective_comparator is not None:
            violates = violates_declared_gap(gap_ms, float(gap_limit), effective_comparator)
        timing_gaps.append(
            {
                "previousEventRef": pred_ref,
                "nextEventRef": succ_ref,
                "previousExpectedEventId": pair["predecessorExpectedEventId"],
                "nextExpectedEventId": pair["successorExpectedEventId"],
                "previousTimestamp": prev_event.get("eventTime"),
                "nextTimestamp": next_event.get("eventTime"),
                "gapMs": gap_ms,
                "gapState": gap_state,
                "timestampQualification": [
                    prev_event.get("timeQuality"),
                    next_event.get("timeQuality"),
                ],
                "gapLimitMs": gap_limit,
                "violatesDeclaredLimit": violates,
            }
        )

    expected_count = len(expected)
    required = [entry for entry in expected if entry.get("required", True)]
    required_count = len(required)
    required_ids = {str(entry["expectedEventId"]) for entry in required}
    matched_required = sum(1 for item in matched if str(item["expectedEventId"]) in required_ids)
    eligible = len(timing_gaps)
    measured = sum(1 for gap in timing_gaps if gap["gapState"] == "MEASURED")
    violating = (
        sum(1 for gap in timing_gaps if gap["violatesDeclaredLimit"])
        if gap_limit is not None
        else None
    )

    limitations: list[str] = [
        "MISSING_EVENT_NOT_PROOF_OF_ABSENCE",
        "SEQUENCE_DIVERGENCE_NOT_ROOT_CAUSE",
        "MEASUREMENT_NOT_GOVERNANCE_VERDICT",
    ]
    if required_count == 0:
        limitations.append("ZERO_REQUIRED_EXPECTED_EVENTS")
    if gap_limit is None:
        limitations.append("DECLARED_GAP_LIMIT_NOT_SUPPLIED")
    elif comparator_source == "LEGACY_DEFAULT":
        limitations.append("LEGACY_GAP_COMPARATOR_DEFAULTED_TO_LTE")
    if eligible and measured == 0:
        limitations.append("NO_MEASURABLE_TIMING_GAPS")
    if eligible and measured < eligible:
        # The assessed exception rate is violating/eligible over the full
        # eligible denominator — a measured-subset ratio is never surfaced
        # as the complete timing rate.
        limitations.append("TIMING_VIOLATION_RATE_NOT_FULLY_MEASURED")
    if resolution_state != "RESOLVED":
        limitations.append(f"RUN_RESOLUTION_{resolution_state}")
    if excluded_ambiguous:
        limitations.append(
            f"AMBIGUOUS_EVIDENCE_EXCLUDED_FROM_MEASUREMENT:{len(excluded_ambiguous)}"
        )
    limitations.extend(str(item) for item in run_resolution.get("limitations") or ())

    # Measurement qualification — deliberately separate from the HAIEC
    # governance verdict (verdict stays None below):
    #   NOT_MEASURED  prerequisites unavailable (no resolvable run scope or
    #                 no qualified observed events)
    #   PARTIAL       measurements computed over the qualified subset, but
    #                 resolution or timestamp limitations constrain
    #                 completeness
    #   MEASURED      qualified resolution and every eligible gap measured
    if resolution_state == "NOT_RESOLVED" or not observed:
        measurement_state = "NOT_MEASURED"
    elif resolution_state in ("PARTIAL", "AMBIGUOUS") or (eligible and measured < eligible):
        measurement_state = "PARTIAL"
    else:
        measurement_state = "MEASURED"

    evidence_refs = sorted(
        {
            item["observedEventRef"]
            for item in (*matched, *duplicates, *unexpected, *lifecycle)
        }
    )

    # Assessed-scope coverage — the union of explicit zone/enforcement-point
    # identifiers observed on qualified evidence. Emitted only when at
    # least one source record carried such a fact; never synthesized.
    observed_zones = sorted(
        {
            str(item["zone"])
            for item in (*matched, *duplicates, *unexpected)
            if item.get("zone")
        }
    )
    observed_eps = sorted(
        {
            str(item["enforcementPoint"])
            for item in (*matched, *duplicates, *unexpected)
            if item.get("enforcementPoint")
        }
    )
    scope_coverage = (
        {
            "observedZones": observed_zones or None,
            "observedEnforcementPoints": observed_eps or None,
        }
        if observed_zones or observed_eps
        else None
    )

    return {
        "schemaVersion": CONTROL7_MEASUREMENT_SCHEMA,
        "controlCode": CONTROL7_CODE,
        "controlName": "Event Recording",
        "runId": run_id,
        "manifestId": manifest["manifestId"],
        "manifestSchemaVersion": manifest["schemaVersion"],
        "resolutionState": resolution_state,
        "measurementState": measurement_state,
        "expected": {
            "count": expected_count,
            "requiredCount": required_count,
        },
        "observed": {
            "count": len(observed),
            "matchedCount": len(matched),
            "unexpectedCount": len(unexpected),
            "duplicateCount": len(duplicates),
            "lifecycleCount": len(lifecycle),
        },
        "coverage": {
            "expectedRequired": required_count,
            "matchedRequired": matched_required,
            "percent": _percent(matched_required, required_count),
            "overallExpected": expected_count,
            "overallMatched": len(matched),
            "overallPercent": _percent(len(matched), expected_count),
            "missingRequired": required_count - matched_required,
        },
        "timing": {
            "declaredGapLimitMs": gap_limit,
            "declaredGapComparator": (
                str(declared_comparator) if declared_comparator is not None else None
            ),
            "effectiveGapComparator": effective_comparator,
            "gapComparatorSource": comparator_source,
            "thresholdSource": timing.get("thresholdSource"),
            "thresholdVersionRef": timing.get("thresholdVersionRef"),
            "eligibleGaps": eligible,
            "measuredGaps": measured,
            "unmeasuredGaps": eligible - measured,
            "violatingGaps": violating,
            # Full assessed exception rate is violating/eligible — emitted
            # only when the entire eligible denominator was measured.
            "violationPercent": (
                _percent(violating, eligible)
                if violating is not None and measured == eligible
                else None
            ),
        },
        "matched": matched,
        "missingEvents": missing,
        "unexpectedEvents": unexpected,
        # Run-lifecycle markers bound to the run (e.g. RUN_STARTED) are
        # listed separately — outside the manifest's behavioral domain, so
        # they are never counted as unexpected assessed behavior.
        "runLifecycleEvents": lifecycle,
        "duplicates": duplicates,
        "sequenceDivergences": sequence,
        "timingGaps": timing_gaps,
        "scopeCoverage": scope_coverage,
        "evidenceRefs": evidence_refs,
        "excludedEvidence": {
            "qualifiedEventRefs": sorted(bound),
            "ambiguousEvidenceRefs": excluded_ambiguous,
            "unresolvedEvidenceRefs": excluded_unresolved,
        },
        "limitations": sorted(set(limitations)),
        "verdict": None,
        "verdictOwner": "HAIEC",
    }
