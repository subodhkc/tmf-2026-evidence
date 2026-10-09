from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser as date_parser


@dataclass(frozen=True)
class TemporalProjection:
    clock_domains: tuple[dict[str, Any], ...]
    alignments: tuple[dict[str, Any], ...]
    normalizations: tuple[dict[str, Any], ...]
    continuity: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...] = ()


def _id(value: str) -> str:
    return value.replace(" ", "-")


def clock_domain(
    *,
    clock_domain_id: str,
    source_ref: str,
    clock_type: str = "WALL_CLOCK",
    timezone_name: str | None = None,
    timezone_basis: str | None = None,
    source_clock_identity: str | None = None,
    precision: str | None = None,
    evidence_refs: Iterable[str] = (),
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "clockDomainId": clock_domain_id,
        "sourceRef": source_ref,
        "clockType": clock_type,
        "timezone": timezone_name,
        "timezoneBasis": timezone_basis,
        "sourceClockIdentity": source_clock_identity,
        "precision": precision,
        "evidenceRefs": list(evidence_refs),
        "limitations": list(limitations),
    }


def alignment_from_sync_record(
    sync_record: Mapping[str, Any],
    *,
    analysis_run_id: str,
    alignment_id: str,
    reference_clock_domain_ref: str,
    candidate_clock_domain_ref: str,
    evidence_ref: str,
    tolerance_ms: float = 100.0,
) -> dict[str, Any]:
    """Create a bounded clock alignment only from explicit clock-sync evidence."""
    if "offset_ms" not in sync_record:
        return {
            "alignmentId": alignment_id,
            "analysisRunId": analysis_run_id,
            "referenceClockDomainRef": reference_clock_domain_ref,
            "candidateClockDomainRef": candidate_clock_domain_ref,
            "state": "UNKNOWN",
            "offsetEstimateMs": None,
            "offsetRangeMs": None,
            "basis": [],
            "evidenceRefs": [evidence_ref],
            "limitations": ["CLOCK_OFFSET_MISSING"],
        }
    offset = float(sync_record["offset_ms"])
    raw_basis = str(sync_record.get("basis", "EXPLICIT_CLOCK_SYNC")).strip()
    basis = raw_basis.upper().replace("-", "_").replace(" ", "_")
    state = "ALIGNED" if basis == "NTP_SYNC_RECORD" else "APPROXIMATE"
    return {
        "alignmentId": alignment_id,
        "analysisRunId": analysis_run_id,
        "referenceClockDomainRef": reference_clock_domain_ref,
        "candidateClockDomainRef": candidate_clock_domain_ref,
        "state": state,
        "offsetEstimateMs": offset,
        "offsetRangeMs": {"min": offset - tolerance_ms, "max": offset + tolerance_ms},
        "basis": [basis],
        "evidenceRefs": [evidence_ref],
        "limitations": [] if state == "ALIGNED" else ["NON_NTP_CLOCK_BASIS"],
    }


def _parse_time(value: str) -> datetime:
    dt = date_parser.isoparse(value)
    if dt.tzinfo is None:
        raise ValueError("event time must carry an explicit timezone")
    return dt.astimezone(timezone.utc)


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_event_time(
    event: Mapping[str, Any],
    *,
    analysis_run_id: str,
    normalization_id: str,
    clock_domain_ref: str | None,
    alignment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize event time without fabricating missing timestamps.

    An offset is applied only when an explicit alignment refers to the supplied
    clock domain. Native time is always retained and the transformation is
    reversible when a qualified offset is used.
    """
    native = event.get("nativeTimestamp") or event.get("eventTime")
    if not native:
        return {
            "normalizationId": normalization_id,
            "analysisRunId": analysis_run_id,
            "eventRef": str(event["eventId"]),
            "clockDomainRef": clock_domain_ref,
            "nativeTimestamp": None,
            "parsedTimestamp": None,
            "normalizedEventTime": None,
            "timezoneAssumption": None,
            "offsetAppliedMs": None,
            "basis": ["SOURCE_TIMESTAMP_MISSING"],
            "state": "MISSING",
            "reversible": False,
            "limitations": ["MISSING_TIMESTAMP_NOT_FABRICATED"],
        }

    parsed = _parse_time(str(native))
    parsed_text = _rfc3339(parsed)
    if alignment is None:
        return {
            "normalizationId": normalization_id,
            "analysisRunId": analysis_run_id,
            "eventRef": str(event["eventId"]),
            "clockDomainRef": clock_domain_ref,
            "nativeTimestamp": str(native),
            "parsedTimestamp": parsed_text,
            "normalizedEventTime": parsed_text,
            "timezoneAssumption": None,
            "offsetAppliedMs": None,
            "basis": ["SOURCE_EXACT_TIMESTAMP"],
            "state": "EXACT",
            "reversible": True,
            "limitations": [],
        }

    if clock_domain_ref is None:
        raise ValueError("clock alignment cannot be applied without a clock domain")
    if alignment.get("candidateClockDomainRef") != clock_domain_ref:
        raise ValueError("alignment candidate clock does not match event clock domain")
    if alignment.get("state") not in {"EXACT", "ALIGNED", "APPROXIMATE"}:
        return {
            "normalizationId": normalization_id,
            "analysisRunId": analysis_run_id,
            "eventRef": str(event["eventId"]),
            "clockDomainRef": clock_domain_ref,
            "nativeTimestamp": str(native),
            "parsedTimestamp": parsed_text,
            "normalizedEventTime": None,
            "timezoneAssumption": None,
            "offsetAppliedMs": None,
            "basis": list(alignment.get("basis", [])),
            "state": "CONTRADICTED" if alignment.get("state") == "CONTRADICTED" else "MISSING",
            "reversible": False,
            "limitations": ["CLOCK_ALIGNMENT_NOT_USABLE"],
        }
    offset = alignment.get("offsetEstimateMs")
    if offset is None:
        raise ValueError("qualified clock alignment requires an offset estimate")
    normalized = parsed + timedelta(milliseconds=float(offset))
    state = "NORMALIZED" if alignment.get("state") in {"EXACT", "ALIGNED"} else "APPROXIMATE"
    return {
        "normalizationId": normalization_id,
        "analysisRunId": analysis_run_id,
        "eventRef": str(event["eventId"]),
        "clockDomainRef": clock_domain_ref,
        "nativeTimestamp": str(native),
        "parsedTimestamp": parsed_text,
        "normalizedEventTime": _rfc3339(normalized),
        "timezoneAssumption": None,
        "offsetAppliedMs": float(offset),
        "basis": list(alignment.get("basis", [])),
        "state": state,
        "reversible": True,
        "limitations": list(alignment.get("limitations", [])),
    }


def sequence_continuity(
    records: Sequence[Mapping[str, Any]],
    *,
    continuity_id: str,
    analysis_run_id: str,
    source_ref: str,
    sequence_field: str = "seq",
    evidence_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Assess observed sequence integrity without claiming stream completeness."""
    values: list[int] = []
    for record in records:
        raw = record.get(sequence_field)
        if raw in (None, ""):
            continue
        try:
            values.append(int(raw))
        except (TypeError, ValueError):
            return {
                "continuityId": continuity_id,
                "analysisRunId": analysis_run_id,
                "sourceRef": source_ref,
                "sequenceKind": "SEQUENCE_NUMBER",
                "state": "CONTRADICTED",
                "startValue": None,
                "endValue": None,
                "missingRanges": [{"kind": "INVALID_SEQUENCE_VALUE", "value": str(raw)}],
                "evidenceRefs": list(evidence_refs),
                "limitations": ["SEQUENCE_VALUE_NOT_INTEGER"],
            }
    if not values:
        return {
            "continuityId": continuity_id,
            "analysisRunId": analysis_run_id,
            "sourceRef": source_ref,
            "sequenceKind": "UNKNOWN",
            "state": "UNKNOWN",
            "startValue": None,
            "endValue": None,
            "missingRanges": [],
            "evidenceRefs": list(evidence_refs),
            "limitations": ["NO_SEQUENCE_EVIDENCE"],
        }

    issues: list[dict[str, Any]] = []
    seen: set[int] = set()
    previous: int | None = None
    for value in values:
        if value in seen:
            issues.append({"kind": "DUPLICATE", "value": value})
        seen.add(value)
        if previous is not None:
            if value < previous:
                issues.append({"kind": "REORDER", "previous": previous, "current": value})
            elif value > previous + 1:
                issues.append({"kind": "GAP", "start": previous + 1, "end": value - 1})
        previous = value

    if any(x["kind"] in {"DUPLICATE", "REORDER"} for x in issues):
        state = "CONTRADICTED"
    elif issues:
        state = "GAP_DETECTED"
    elif len(values) >= 2:
        state = "PROVEN_CONTIGUOUS"
    else:
        state = "PARTIAL"
    limitations = ["OBSERVED_WINDOW_ONLY_NOT_GLOBAL_STREAM_COMPLETENESS"]
    return {
        "continuityId": continuity_id,
        "analysisRunId": analysis_run_id,
        "sourceRef": source_ref,
        "sequenceKind": "SEQUENCE_NUMBER",
        "state": state,
        "startValue": values[0],
        "endValue": values[-1],
        "missingRanges": issues,
        "evidenceRefs": list(evidence_refs),
        "limitations": limitations,
    }


def timeline_event(
    event: Mapping[str, Any],
    normalization: Mapping[str, Any],
    *,
    analysis_run_id: str,
    timeline_event_id: str,
    sequence_index: int | None = None,
) -> dict[str, Any]:
    normalized_time = normalization.get("normalizedEventTime")
    basis = "EVENT_TIME" if normalized_time else "UNKNOWN"
    if sequence_index is not None:
        basis = "MONOTONIC_COUNTER"
    return {
        "timelineEventId": timeline_event_id,
        "analysisRunId": analysis_run_id,
        "eventRef": event.get("eventId"),
        "actionGroupRef": None,
        "semanticClass": str(event.get("eventClass", "UNKNOWN_EVENT")),
        "normalizedTime": normalized_time,
        "sequenceIndex": sequence_index,
        "orderingBasis": basis,
        "sourceRefs": [str(event["sourceRef"])],
        "evidenceRefs": [str(event["eventId"])],
        "timeQuality": str(normalization.get("state", "UNKNOWN")),
        "limitations": list(normalization.get("limitations", [])),
    }


def source_coverage_profile(
    *,
    coverage_profile_id: str,
    evidence_set_id: str,
    observed_source_roles: Sequence[str],
    artifact_count: int,
    record_count: int,
    parsed_record_count: int,
    failed_record_count: int,
    expected_source_roles: Sequence[str] = (),
    time_start: str | None = None,
    time_end: str | None = None,
    completeness_proven: bool = False,
    completeness_basis_refs: Sequence[str] = (),
    unsupported_artifact_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Describe collection coverage without inferring completeness from silence.

    `PROVEN_COMPLETE` requires an explicit caller assertion backed by one or
    more evidence references. Merely observing expected roles or contiguous
    sequence values is never enough to prove global stream completeness.
    """
    observed = tuple(observed_source_roles)
    expected = tuple(expected_source_roles)
    counts = {role: observed.count(role) for role in sorted(set(observed))}
    limitations: list[str] = []
    if completeness_proven:
        if not completeness_basis_refs:
            raise ValueError("proven completeness requires evidence references")
        if failed_record_count or unsupported_artifact_refs:
            raise ValueError("proven completeness conflicts with failed or unsupported evidence")
        state = "PROVEN_COMPLETE"
    elif record_count > 0 and parsed_record_count == 0:
        state = "BROKEN"
        limitations.append("NO_RECORDS_PARSED")
    elif failed_record_count or unsupported_artifact_refs or (expected and not set(expected) <= set(observed)):
        state = "PARTIAL"
        limitations.append("COLLECTION_OR_PARSE_GAPS_PRESENT")
    else:
        state = "UNKNOWN"
        limitations.append("COMPLETENESS_NOT_PROVEN")
    window = None
    if time_start is not None or time_end is not None:
        window = {"startTime": time_start, "endTime": time_end}
    return {
        "coverageProfileId": coverage_profile_id,
        "evidenceSetId": evidence_set_id,
        "sourceRolesObserved": list(observed),
        "sourceRolesExpected": list(expected),
        "sourceRoleCounts": counts,
        "artifactCount": artifact_count,
        "recordCount": record_count,
        "parsedRecordCount": parsed_record_count,
        "failedRecordCount": failed_record_count,
        "timeCoverage": window,
        "completenessState": state,
        "completenessBasisRefs": list(completeness_basis_refs),
        "unsupportedArtifactRefs": list(unsupported_artifact_refs),
        "limitations": limitations,
    }
