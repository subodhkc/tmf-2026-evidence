"""Control 9 / AIA-ARC-006 — generic drift & performance measurement.

The scored forensic quantity is::

    relativeDegradation = (baseline - live) / abs(baseline)   # HIGHER_IS_BETTER
    relativeDegradation = (live - baseline) / abs(baseline)   # LOWER_IS_BETTER

per comparable baseline/live measurement window, plus ``absoluteDelta``
(``live - baseline``) wherever both values exist.

The engine is metric-agnostic: the operator binds a versioned, immutable
``KpiMetricProfile`` (metric id, unit, explicit direction, aggregation,
window semantics, value source) and an immutable evidence-bound baseline.
The real workshop KPI is configured later through the profile, Source
Setup mapping, and baseline selection — never through engine changes.

This module is measurement-only. It never decides whether drift satisfied
a policy — ``verdict`` is always ``None`` and ``verdictOwner`` is
``HAIEC``. Drift thresholds, violating-window allowances, and the
governing baseline version belong to HAIEC.

Determinism contract:

- KPI values come only from canonical-event ``attributes`` (the preserved
  raw record) — never from AI, similarity, or timestamp proximity;
- run membership is inherited verbatim from ``resolve_competition_run``;
- direction is explicit profile data — it is never inferred from the
  metric name;
- only finite numeric KPI values qualify. Strings, bools, NaN/inf are
  ``UNQUALIFIED`` — never silently coerced;
- a baseline of exactly zero makes relative degradation undefined:
  ``relativeDegradation`` stays ``None`` — no epsilon, no clamping;
- a missing window is never zero drift, and incompatible semantics never
  produce an authoritative comparison;
- a semantic profile change is not system drift — a baseline bound to an
  older profile version fails compatibility requalification.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

CONTROL9_CODE = "AIA-ARC-006"
CONTROL9_MEASUREMENT_SCHEMA = "control9-drift-measurement/0.1"
METRIC_PROFILE_SCHEMA = "kpi-metric-profile/0.1"
BASELINE_SCHEMA = "control9-baseline/0.1"
OBSERVATION_SCHEMA = "kpi-observation/0.1"

DIRECTIONS = ("HIGHER_IS_BETTER", "LOWER_IS_BETTER")
AGGREGATIONS = ("SOURCE_VALUE", "MEAN", "MIN", "MAX", "SUM", "LAST", "P50", "P95")
WINDOW_MODES = ("SOURCE_WINDOWED", "FIXED_DURATION")
BASELINE_MODES = ("FIXED_REFERENCE_VALUE", "MATCHED_WINDOWS")
# Reuses the BaselineDefinition basis vocabulary — the same evidence-bound
# descriptive reference semantics, not a second registry.
BASELINE_BASES = (
    "EXPLICIT_USER_SELECTED",
    "SCENARIO_BASELINE",
    "GOLDEN_REFERENCE",
    "HISTORICAL_WINDOW",
    "KNOWN_GOOD_RUN",
)
ZERO_BASELINE_RULES = ("RELATIVE_UNAVAILABLE",)
COMPATIBILITY_STATES = ("COMPATIBLE", "INCOMPATIBLE", "UNKNOWN")
COMPARISON_STATES = (
    "COMPARABLE",
    "MISSING_BASELINE",
    "MISSING_LIVE",
    "INCOMPATIBLE",
    "ZERO_BASELINE_RELATIVE_UNAVAILABLE",
    "UNQUALIFIED",
)
MEASUREMENT_STATES = ("MEASURED", "PARTIAL", "NOT_MEASURED")

_PROFILE_ID_RE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")

# Bounded timestamp fallbacks when the profile declares no timestampSource.
_TIMESTAMP_KEYS = ("ts", "timestamp", "observedAt", "observed_at", "time", "datetime")


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Control9Error(ValueError):
    """Raised for malformed metric profiles, baselines, or measurement inputs."""


# Monitoring/response source records — explicit alert-layer facts only.
# A ``MONITORING_ALERT`` record declares the alert identity, the window it
# fired on, the named owner/recipient, and the required response. A
# ``MONITORING_RESPONSE`` record (or inline response fields on the alert)
# records the observed response or a recorded silence — never inferred.
_MONITORING_ALERT_TYPE = "MONITORING_ALERT"
_MONITORING_RESPONSE_TYPE = "MONITORING_RESPONSE"
_MONITORING_RESPONSE_STATES = frozenset(
    {"RESPONDED", "NO_RESPONSE_RECORDED", "SILENCE_RECORDED", "NOT_REQUIRED"}
)


def project_monitoring_evidence(
    *,
    run_resolution: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project the run's monitoring/alert evidence into a deterministic block.

    Only explicit source records bound to this run are read. Every field is
    carried verbatim; absent records produce ``None`` (never fabricated).
    """
    qualified = {str(r) for r in run_resolution.get("qualifiedEventRefs") or ()}
    alerts: list[dict[str, Any]] = []
    responses: dict[str, list[dict[str, Any]]] = {}
    for event in canonical_events:
        attributes = event.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            continue
        record_type = _text(attributes.get("event_type") or attributes.get("recordType"))
        if record_type not in {_MONITORING_ALERT_TYPE, _MONITORING_RESPONSE_TYPE}:
            continue
        ref = str(event.get("eventId") or "")
        if ref not in qualified:
            continue
        if record_type == _MONITORING_ALERT_TYPE:
            alerts.append({"ref": ref, "attributes": attributes})
        else:
            alert_id = _text(attributes.get("alertId"))
            responses.setdefault(alert_id or "", []).append(
                {"ref": ref, "attributes": attributes}
            )

    if not alerts:
        return {"monitoring": None, "monitoringEvidenceRefs": [], "limitations": []}

    # Deterministic alert selection — earliest triggeredAt, then alertId —
    # never "latest wins". Additional alerts stay visible as a limitation.
    alerts.sort(
        key=lambda row: (
            _text(row["attributes"].get("triggeredAt"))
            or _text(row["attributes"].get("ts"))
            or "",
            _text(row["attributes"].get("alertId")) or "",
        )
    )
    alert = alerts[0]
    attributes = alert["attributes"]
    limitations: list[str] = []
    if len(alerts) > 1:
        limitations.append(f"MULTIPLE_MONITORING_ALERTS:{len(alerts)}")

    alert_id = _text(attributes.get("alertId"))
    response_rows = list(responses.get(alert_id or "", ()))
    response = None
    # Inline response fields on the alert record are explicit facts too.
    inline_state = _text(attributes.get("responseState"))
    if response_rows:
        response_rows.sort(
            key=lambda row: (
                _text(row["attributes"].get("responseObservedAt"))
                or _text(row["attributes"].get("observedAt"))
                or _text(row["attributes"].get("ts"))
                or "",
                row["ref"],
            )
        )
        if len(response_rows) > 1:
            limitations.append(f"MULTIPLE_MONITORING_RESPONSES:{len(response_rows)}")
        rattr = response_rows[0]["attributes"]
        state = _text(rattr.get("state") or rattr.get("responseState"))
        response = {
            "state": state if state in _MONITORING_RESPONSE_STATES else None,
            "observedAt": _text(
                rattr.get("responseObservedAt") or rattr.get("observedAt")
            )
            or _text(rattr.get("ts")),
            "responderRef": _text(rattr.get("responderRef")),
            "evidenceRef": _text(rattr.get("responseEvidenceRef") or rattr.get("evidenceRef")),
            "detail": _text(rattr.get("detail")),
        }
        if state is not None and response["state"] is None:
            limitations.append("MONITORING_RESPONSE_STATE_UNRECOGNIZED")
    elif inline_state is not None:
        response = {
            "state": (
                inline_state if inline_state in _MONITORING_RESPONSE_STATES else None
            ),
            "observedAt": _text(attributes.get("responseObservedAt")),
            "responderRef": _text(attributes.get("responderRef")),
            "evidenceRef": _text(
                attributes.get("responseEvidenceRef") or attributes.get("evidenceRef")
            ),
            "detail": _text(attributes.get("detail")),
        }
        if response["state"] is None:
            limitations.append("MONITORING_RESPONSE_STATE_UNRECOGNIZED")

    monitoring = {
        "alertId": alert_id,
        "triggeredWindowKey": _text(attributes.get("triggeredWindowKey")),
        "triggeredAt": _text(attributes.get("triggeredAt")) or _text(attributes.get("ts")),
        "driftValuePercent": _finite_number(attributes.get("driftValuePercent")),
        "thresholdVersionRef": _text(attributes.get("thresholdVersionRef")),
        "owner": _text(attributes.get("owner")),
        "recipient": _text(attributes.get("recipient")),
        "requiredResponse": _text(attributes.get("requiredResponse")),
        "response": response,
        "evidenceRefs": sorted(
            {alert["ref"]}
            | {row["ref"] for row in response_rows}
        ),
    }
    return {
        "monitoring": monitoring,
        "monitoringEvidenceRefs": monitoring["evidenceRefs"],
        "limitations": limitations,
    }


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _finite_number(value: Any) -> float | None:
    """Strict KPI value normalization: real finite numbers only. No coercion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _int_field(value: Any, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise Control9Error(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise Control9Error(f"{label} must be an integer") from None
    if result < minimum:
        raise Control9Error(f"{label} must be >= {minimum}")
    return result


def _parse_time_ms(value: Any) -> int | None:
    """ISO-8601 timestamp to epoch milliseconds, or None when unparsable."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        dt = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_iso(ms: int) -> str:
    return (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# KpiMetricProfile — versioned, immutable metric semantics
# ---------------------------------------------------------------------------


def profile_ref(profile_id: str, version: int) -> str:
    return f"metric-profile:{profile_id}@v{version}"


def normalize_metric_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one ``kpi-metric-profile/0.1`` document.

    The profile is immutable once persisted — any semantic change (unit,
    direction, aggregation, windowing, scope, value mapping) requires a new
    ``profileVersion`` and yields a new ``profileDigest``. No HAIEC drift
    threshold field is accepted — LogSense never owns the verdict policy.
    """
    if not isinstance(payload, Mapping):
        raise Control9Error("metric profile must be an object")
    profile_id = str(payload.get("profileId") or "").strip()
    if not profile_id or any(ch.isspace() for ch in profile_id):
        raise Control9Error("profileId must be a non-empty identifier without whitespace")
    if not set(profile_id) <= _PROFILE_ID_RE_CHARS:
        raise Control9Error("profileId may use letters, digits, '.', '_' and '-' only")
    version = _int_field(payload.get("profileVersion"), "profileVersion")

    metric_id = str(payload.get("metricId") or "").strip()
    if not metric_id:
        raise Control9Error("metricId is required")
    unit = str(payload.get("unit") or "").strip()
    if not unit:
        raise Control9Error("unit is required — values are never unitless by default")
    direction = str(payload.get("direction") or "").strip()
    if direction not in DIRECTIONS:
        raise Control9Error(
            "direction is required and must be explicit data — "
            "HIGHER_IS_BETTER or LOWER_IS_BETTER (never inferred from the metric name)"
        )
    aggregation = str(payload.get("aggregation") or "").strip()
    if aggregation not in AGGREGATIONS:
        raise Control9Error(f"aggregation must be one of {', '.join(AGGREGATIONS)}")

    zero_rule = str(payload.get("zeroBaselineRule") or "RELATIVE_UNAVAILABLE").strip()
    if zero_rule not in ZERO_BASELINE_RULES:
        raise Control9Error(
            "zeroBaselineRule must be RELATIVE_UNAVAILABLE — the generic engine "
            "fails closed on a zero baseline (no epsilon, no clamp)"
        )

    value_source = payload.get("valueSource")
    if not isinstance(value_source, Mapping) or not str(value_source.get("field") or "").strip():
        raise Control9Error(
            "valueSource.field is required — the canonical attribute carrying the KPI value"
        )

    window = payload.get("windowDefinition")
    if not isinstance(window, Mapping):
        raise Control9Error("windowDefinition is required")
    mode = str(window.get("mode") or "").strip()
    if mode not in WINDOW_MODES:
        raise Control9Error(f"windowDefinition.mode must be one of {', '.join(WINDOW_MODES)}")
    normalized_window: dict[str, Any] = {"mode": mode}
    if mode == "SOURCE_WINDOWED":
        key_field = str(window.get("windowKeyField") or "").strip()
        if not key_field:
            raise Control9Error(
                "SOURCE_WINDOWED mode requires windowKeyField — the attribute "
                "carrying the producer's own window identity"
            )
        normalized_window["windowKeyField"] = key_field
        for opt in ("windowStartField", "windowEndField"):
            if str(window.get(opt) or "").strip():
                normalized_window[opt] = str(window[opt]).strip()
    else:
        duration = _int_field(window.get("durationMs"), "windowDefinition.durationMs")
        anchor = _text(window.get("anchorTime"))
        if anchor is None or _parse_time_ms(anchor) is None:
            raise Control9Error(
                "FIXED_DURATION mode requires anchorTime — a parseable ISO-8601 "
                "alignment anchor so bucketing is deterministic"
            )
        normalized_window["durationMs"] = duration
        normalized_window["anchorTime"] = anchor

    expected_keys = window.get("expectedWindowKeys")
    if expected_keys is not None:
        if not isinstance(expected_keys, Sequence) or isinstance(expected_keys, (str, bytes)):
            raise Control9Error("expectedWindowKeys must be an array of window keys")
        normalized_window["expectedWindowKeys"] = sorted(
            {str(k).strip() for k in expected_keys if str(k).strip()}
        )
    expected_count = window.get("expectedWindowCount")
    if expected_count is not None:
        normalized_window["expectedWindowCount"] = _int_field(
            expected_count, "expectedWindowCount", minimum=0
        )

    scope = payload.get("governedScope")
    normalized_scope = None
    if scope is not None:
        if not isinstance(scope, Mapping):
            raise Control9Error("governedScope must be an object")
        normalized_scope = {
            "type": _text(scope.get("type")),
            "id": _text(scope.get("id")),
            "attributes": dict(scope.get("attributes") or {}) or None,
        }

    created_at = _text(payload.get("createdAt")) or "1970-01-01T00:00:00Z"
    if _parse_time_ms(created_at) is None:
        raise Control9Error("createdAt must be an ISO-8601 timestamp")

    body = {
        "profileSchemaVersion": METRIC_PROFILE_SCHEMA,
        "profileId": profile_id,
        "profileVersion": version,
        "profileRef": profile_ref(profile_id, version),
        "metricId": metric_id,
        "displayName": _text(payload.get("displayName")) or metric_id,
        "unit": unit,
        "direction": direction,
        "aggregation": aggregation,
        "governedScope": normalized_scope,
        "valueSource": {
            "field": str(value_source["field"]).strip(),
            "metricNameField": _text(value_source.get("metricNameField")),
            "unitField": _text(value_source.get("unitField")),
            "scopeTypeField": _text(value_source.get("scopeTypeField")),
            "scopeIdField": _text(value_source.get("scopeIdField")),
        },
        "timestampSource": _text(payload.get("timestampSource")),
        "windowDefinition": normalized_window,
        "mappingProfileRefs": sorted(
            {str(r) for r in payload.get("mappingProfileRefs") or () if str(r)}
        ),
        "producerRefs": sorted({str(r) for r in payload.get("producerRefs") or () if str(r)}),
        "zeroBaselineRule": zero_rule,
        "createdAt": created_at,
        "sourceBasis": _text(payload.get("sourceBasis")),
        "limitations": sorted({str(x) for x in payload.get("limitations") or () if str(x)}),
    }
    return {**body, "profileDigest": "sha256:" + _digest(body)}


# ---------------------------------------------------------------------------
# Built-in illustrative profiles — replace before assessed use.
# ---------------------------------------------------------------------------


def _example_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    limitations = [
        "ILLUSTRATIVE_EXAMPLE_REPLACE_BEFORE_ASSESSED_USE",
        *(str(x) for x in payload.get("limitations") or ()),
    ]
    return normalize_metric_profile({**payload, "limitations": limitations})


def builtin_metric_profiles() -> tuple[dict[str, Any], ...]:
    """Bounded built-in templates an operator can adopt or clone.

    These are examples only — they carry the ILLUSTRATIVE limitation and no
    drift threshold. The real event KPI is bound by cloning a profile and
    approving the real field mapping, never by editing the engine.
    """
    return (
        _example_profile(
            {
                "profileId": "example-performance-score",
                "profileVersion": 1,
                "metricId": "example.performance_score",
                "displayName": "Example Performance Score",
                "unit": "ratio",
                "direction": "HIGHER_IS_BETTER",
                "aggregation": "SOURCE_VALUE",
                "governedScope": {"type": "LOGICAL_ENTITY", "id": "scope-1"},
                "valueSource": {
                    "field": "kpiValue",
                    "metricNameField": "kpiName",
                    "unitField": "unit",
                    "scopeIdField": "scopeId",
                },
                "timestampSource": "ts",
                "windowDefinition": {
                    "mode": "SOURCE_WINDOWED",
                    "windowKeyField": "windowId",
                    "expectedWindowKeys": [
                        "W01", "W02", "W03", "W04", "W05",
                        "W06", "W07", "W08", "W09", "W10",
                    ],
                },
                "createdAt": "2026-10-01T00:00:00Z",
                "sourceBasis": "ORGANIZER_ILLUSTRATIVE_SHAPE",
            }
        ),
        _example_profile(
            {
                "profileId": "example-p95-latency",
                "profileVersion": 1,
                "metricId": "example.latency",
                "displayName": "Example P95 Latency",
                "unit": "ms",
                "direction": "LOWER_IS_BETTER",
                "aggregation": "P95",
                "governedScope": {"type": "LOGICAL_ENTITY", "id": "scope-1"},
                "valueSource": {
                    "field": "kpiValue",
                    "metricNameField": "kpiName",
                    "unitField": "unit",
                    "scopeIdField": "scopeId",
                },
                "timestampSource": "ts",
                "windowDefinition": {
                    "mode": "SOURCE_WINDOWED",
                    "windowKeyField": "windowId",
                },
                "createdAt": "2026-10-01T00:00:00Z",
                "sourceBasis": "ILLUSTRATIVE_LOWER_IS_BETTER",
            }
        ),
    )


# ---------------------------------------------------------------------------
# Control 9 baseline — immutable, evidence-bound descriptive reference
# ---------------------------------------------------------------------------


def baseline_ref(baseline_id: str, version: int) -> str:
    return f"c9-baseline:{baseline_id}@v{version}"


def normalize_control9_baseline(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one ``control9-baseline/0.1`` document.

    The baseline reuses the ``BaselineDefinition`` identity vocabulary
    (``baselineId``, ``basis``, ``mappingProfileDigests``, ``artifactDigests``,
    ``sourceEvidenceSetId``, ``frozen``) and extends it with the measurement
    payload: the metric semantics it was captured under, and either a fixed
    reference value or per-window values. It is an immutable descriptive
    reference — the HAIEC governing baseline version is a separate,
    later adoption and is never written here.
    """
    if not isinstance(payload, Mapping):
        raise Control9Error("baseline must be an object")
    baseline_id = str(payload.get("baselineId") or "").strip()
    if not baseline_id:
        raise Control9Error("baselineId is required")
    version = _int_field(payload.get("baselineVersion"), "baselineVersion")
    basis = str(payload.get("basis") or "").strip()
    if basis not in BASELINE_BASES:
        raise Control9Error(f"basis must be one of {', '.join(BASELINE_BASES)}")
    mode = str(payload.get("baselineMode") or "").strip()
    if mode not in BASELINE_MODES:
        raise Control9Error(f"baselineMode must be one of {', '.join(BASELINE_MODES)}")

    # The baseline freezes the metric semantics it was captured under so
    # compatibility preflight can compare them against the live profile.
    semantics: dict[str, Any] = {}
    for key in ("metricId", "unit", "direction", "aggregation"):
        value = _text(payload.get(key))
        if value is None:
            raise Control9Error(f"baseline requires explicit {key}")
        semantics[key] = value
    if semantics["direction"] not in DIRECTIONS:
        raise Control9Error("baseline direction must be explicit")
    scope = payload.get("governedScope")
    window = payload.get("windowDefinition")

    fixed_value = _finite_number(payload.get("value"))
    windows: list[dict[str, Any]] | None = None
    if mode == "FIXED_REFERENCE_VALUE":
        if fixed_value is None:
            raise Control9Error("FIXED_REFERENCE_VALUE baseline requires a finite value")
    else:
        raw_windows = payload.get("windows")
        if not isinstance(raw_windows, Sequence) or isinstance(raw_windows, (str, bytes)):
            raise Control9Error("MATCHED_WINDOWS baseline requires a windows array")
        windows = []
        seen: set[str] = set()
        for row in raw_windows:
            if not isinstance(row, Mapping):
                raise Control9Error("baseline windows must be objects")
            key = str(row.get("windowKey") or "").strip()
            window_value = _finite_number(row.get("value"))
            if not key or window_value is None:
                raise Control9Error("each baseline window needs windowKey and a finite value")
            if key in seen:
                raise Control9Error(f"duplicate baseline window key: {key}")
            seen.add(key)
            windows.append(
                {
                    "windowKey": key,
                    "value": window_value,
                    "windowStart": _text(row.get("windowStart")),
                    "windowEnd": _text(row.get("windowEnd")),
                    "evidenceRefs": sorted(
                        {str(r) for r in row.get("evidenceRefs") or () if str(r)}
                    ),
                }
            )
        if not windows:
            raise Control9Error("MATCHED_WINDOWS baseline requires at least one window")
        windows.sort(key=lambda w: str(w["windowKey"]))

    created_at = _text(payload.get("createdAt")) or "1970-01-01T00:00:00Z"
    if _parse_time_ms(created_at) is None:
        raise Control9Error("createdAt must be an ISO-8601 timestamp")

    body = {
        "schemaVersion": BASELINE_SCHEMA,
        "baselineId": baseline_id,
        "baselineVersion": version,
        "baselineRef": baseline_ref(baseline_id, version),
        "caseId": _text(payload.get("caseId")),
        "label": _text(payload.get("label")) or baseline_id,
        "createdAt": created_at,
        "basis": basis,
        "baselineMode": mode,
        "metricId": semantics["metricId"],
        "unit": semantics["unit"],
        "direction": semantics["direction"],
        "aggregation": semantics["aggregation"],
        "governedScope": dict(scope) if isinstance(scope, Mapping) else None,
        "windowDefinition": dict(window) if isinstance(window, Mapping) else None,
        "metricProfileRef": _text(payload.get("metricProfileRef")),
        "metricProfileDigest": _text(payload.get("metricProfileDigest")),
        "value": fixed_value if mode == "FIXED_REFERENCE_VALUE" else None,
        "windows": windows,
        "valueBasis": _text(payload.get("valueBasis")) or "EXPLICIT_DECLARED",
        "sourceRunId": _text(payload.get("sourceRunId")),
        "sourceAnalysisRunId": _text(payload.get("sourceAnalysisRunId")),
        "sourceSnapshotRef": _text(payload.get("sourceSnapshotRef")),
        "sourceEvidenceSetId": _text(payload.get("sourceEvidenceSetId")),
        "evidenceRefs": sorted({str(r) for r in payload.get("evidenceRefs") or () if str(r)}),
        "mappingProfileDigests": sorted(
            {str(r) for r in payload.get("mappingProfileDigests") or () if str(r)}
        ),
        "artifactDigests": sorted(
            {str(r) for r in payload.get("artifactDigests") or () if str(r)}
        ),
        "sourceBasis": _text(payload.get("sourceBasis")),
        "frozen": True,
        "limitations": sorted({str(x) for x in payload.get("limitations") or () if str(x)}),
    }
    return {**body, "baselineDigest": "sha256:" + _digest(body)}


# ---------------------------------------------------------------------------
# KpiObservation projection
# ---------------------------------------------------------------------------


def _observed_at(profile: Mapping[str, Any], attributes: Mapping[str, Any]) -> str | None:
    declared = _text(profile.get("timestampSource"))
    if declared and attributes.get(declared) not in (None, ""):
        return str(attributes[declared])
    for key in _TIMESTAMP_KEYS:
        if attributes.get(key) not in (None, ""):
            return str(attributes[key])
    return None


def _window_for_observation(
    profile: Mapping[str, Any], attributes: Mapping[str, Any], observed_at: str | None
) -> tuple[str | None, str | None, str | None, list[str]]:
    """Resolve ``(windowKey, windowStart, windowEnd, limitations)`` for one
    observation — either the source's own window identity or deterministic
    fixed-duration bucketing from the declared anchor."""
    window = profile["windowDefinition"]
    if window["mode"] == "SOURCE_WINDOWED":
        key = _text(attributes.get(window["windowKeyField"]))
        start_field = _text(window.get("windowStartField"))
        end_field = _text(window.get("windowEndField"))
        start = _text(attributes.get(start_field)) if start_field else None
        end = _text(attributes.get(end_field)) if end_field else None
        limitations = [] if key else ["WINDOW_KEY_ABSENT"]
        return key, start, end, limitations
    duration = int(window["durationMs"])
    anchor_ms = _parse_time_ms(window["anchorTime"])
    obs_ms = _parse_time_ms(observed_at)
    if obs_ms is None or anchor_ms is None:
        return None, None, None, ["OBSERVATION_TIME_UNRESOLVED_FOR_FIXED_WINDOW"]
    index = (obs_ms - anchor_ms) // duration  # floor semantics, both directions
    key = f"W{index:04d}"
    return key, _ms_to_iso(anchor_ms + index * duration), _ms_to_iso(
        anchor_ms + (index + 1) * duration
    ), []


def project_kpi_observations(
    *,
    metric_profile: Mapping[str, Any],
    run_resolution: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project qualified KPI observations for one resolved run.

    An event is a C9 candidate only when it is mapped, carries the profile's
    declared value field, and — when the profile declares a
    ``metricNameField`` — names this metric explicitly. Ambiguous run
    evidence is never observed; unresolved candidates stay visible.
    """
    profile = metric_profile
    value_field = str(profile["valueSource"]["field"])
    metric_name_field = _text(profile["valueSource"].get("metricNameField"))
    unit_field = _text(profile["valueSource"].get("unitField"))
    scope_type_field = _text(profile["valueSource"].get("scopeTypeField"))
    scope_id_field = _text(profile["valueSource"].get("scopeIdField"))
    mapping_refs = {str(r) for r in profile.get("mappingProfileRefs") or ()}
    metric_id = str(profile["metricId"])
    governed_scope = profile.get("governedScope") or {}
    governed_scope_id = _text(governed_scope.get("id"))

    qualified = {str(r) for r in run_resolution.get("qualifiedEventRefs") or ()}
    ambiguous = {str(r) for r in run_resolution.get("ambiguousEvidenceRefs") or ()}

    observations: list[dict[str, Any]] = []
    ambiguous_refs: list[str] = []
    unresolved_refs: list[str] = []
    for event in canonical_events:
        ref = str(event.get("eventId") or "")
        if not ref:
            continue
        attributes = event.get("attributes") or {}
        if not isinstance(attributes, Mapping):
            continue
        # Candidate gate — the record must carry this metric's declared value
        # field or name; generic events are never KPI candidates.
        has_value_field = attributes.get(value_field) not in (None, "")
        named_metric = (
            metric_name_field is not None
            and str(attributes.get(metric_name_field) or "") == metric_id
        )
        if not has_value_field and not named_metric:
            continue
        if metric_name_field is not None and not named_metric:
            # A value-bearing record for a different metric is not a
            # candidate for this profile — it is simply not this KPI.
            continue
        if ref in ambiguous:
            ambiguous_refs.append(ref)
            continue
        if ref not in qualified:
            unresolved_refs.append(ref)
            continue

        event_mapped = (
            event.get("eventClassAssignment") == "MAPPED" and event.get("mappingProfileRef")
        )
        mapping_allowed = not mapping_refs or str(
            event.get("mappingProfileRef") or ""
        ) in mapping_refs
        value = _finite_number(attributes.get(value_field))
        observed_at = _observed_at(profile, attributes)
        window_key, window_start, window_end, window_lims = _window_for_observation(
            profile, attributes, observed_at
        )

        limitations: list[str] = list(window_lims)
        mapping_qual = "QUALIFIED" if event_mapped and mapping_allowed else "UNKNOWN"
        if not event_mapped:
            limitations.append("EVENT_MAPPING_NOT_QUALIFIED")
        elif not mapping_allowed:
            limitations.append("MAPPING_PROFILE_NOT_IN_PROFILE_REFS")

        metric_qual = "QUALIFIED"
        if value is None:
            metric_qual = "UNQUALIFIED"
            limitations.append("KPI_VALUE_NOT_FINITE_NUMERIC")
        declared_unit = _text(attributes.get(unit_field)) if unit_field else None
        if declared_unit and declared_unit != str(profile["unit"]):
            metric_qual = "UNQUALIFIED"
            limitations.append(f"KPI_UNIT_MISMATCH:{declared_unit}")
        if governed_scope_id and scope_id_field:
            obs_scope = _text(attributes.get(scope_id_field))
            if obs_scope and obs_scope != governed_scope_id:
                metric_qual = "UNQUALIFIED"
                limitations.append(f"KPI_SCOPE_MISMATCH:{obs_scope}")
        if metric_qual == "QUALIFIED" and mapping_qual != "QUALIFIED":
            metric_qual = "UNQUALIFIED"
        if window_key is None and metric_qual == "QUALIFIED":
            limitations.append("WINDOW_UNRESOLVED")

        artifact_id = None
        for row in event.get("rawRecordRefs") or ():
            if isinstance(row, Mapping) and row.get("artifactId"):
                artifact_id = str(row["artifactId"])
                break

        observations.append(
            {
                "observationSchemaVersion": OBSERVATION_SCHEMA,
                "metricProfileRef": profile["profileRef"],
                "metricId": metric_id,
                "value": value,
                "unit": str(profile["unit"]),
                "observedAt": observed_at,
                "windowKey": window_key,
                "windowStart": window_start,
                "windowEnd": window_end,
                "scopeType": _text(attributes.get(scope_type_field)) if scope_type_field else None,
                "scopeId": _text(attributes.get(scope_id_field)) if scope_id_field else None,
                "aggregation": str(profile["aggregation"]),
                "producer": _text(attributes.get("producer"))
                or _text(attributes.get("emitter")),
                "producerVersion": _text(attributes.get("producerVersion")),
                "sourceArtifactId": artifact_id,
                "sourceEventRef": ref,
                "mappingProfileRef": _text(event.get("mappingProfileRef")),
                "mappingQualification": mapping_qual,
                "metricQualification": metric_qual,
                "limitations": limitations,
            }
        )

    observations.sort(key=lambda o: (str(o["windowKey"]), str(o["sourceEventRef"])))
    return {
        "observations": observations,
        "ambiguousCandidateRefs": sorted(ambiguous_refs),
        "unresolvedCandidateRefs": sorted(unresolved_refs),
    }


# ---------------------------------------------------------------------------
# Window aggregation
# ---------------------------------------------------------------------------


def _aggregate(values: list[float], aggregation: str) -> float | None:
    """Deterministic bounded aggregation. P50/P95 use nearest-rank."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if aggregation == "MEAN":
        return math.fsum(ordered) / n
    if aggregation == "MIN":
        return ordered[0]
    if aggregation == "MAX":
        return ordered[-1]
    if aggregation == "SUM":
        return math.fsum(ordered)
    if aggregation in ("P50", "P95"):
        percentile = 50 if aggregation == "P50" else 95
        rank = max(1, math.ceil(percentile / 100 * n))
        return ordered[rank - 1]
    return ordered[-1]  # SOURCE_VALUE/LAST single-value path handled by caller


# ---------------------------------------------------------------------------
# Compatibility preflight
# ---------------------------------------------------------------------------

_COMPAT_DIMENSIONS = (
    "METRIC_ID",
    "UNIT",
    "DIRECTION",
    "AGGREGATION",
    "GOVERNED_SCOPE",
    "WINDOW_SEMANTICS",
    "METRIC_PROFILE",
    "MAPPING_PROFILE",
    "SOURCE_BASIS",
)


def compatibility_gate(
    *,
    metric_profile: Mapping[str, Any],
    baseline: Mapping[str, Any],
    live_mapping_profile_refs: Sequence[str] = (),
    live_source_basis: str | None = None,
) -> dict[str, Any]:
    """Compare baseline semantics against the live metric profile per
    dimension. INCOMPATIBLE evidence never produces authoritative drift —
    a semantic profile change is a comparability failure, not system drift.
    """
    profile = metric_profile
    dimensions: list[dict[str, Any]] = []

    def _dim(dimension: str, baseline_value: Any, live_value: Any, detail: str) -> None:
        if baseline_value in (None, "") or live_value in (None, ""):
            state = "UNKNOWN"
        elif baseline_value == live_value:
            state = "COMPATIBLE"
        else:
            state = "INCOMPATIBLE"
        dimensions.append(
            {
                "dimension": dimension,
                "baseline": baseline_value,
                "live": live_value,
                "state": state,
                "detail": detail,
            }
        )

    _dim("METRIC_ID", baseline.get("metricId"), profile.get("metricId"), "metric identity")
    _dim("UNIT", baseline.get("unit"), profile.get("unit"), "measurement unit")
    _dim("DIRECTION", baseline.get("direction"), profile.get("direction"), "metric direction")
    _dim(
        "AGGREGATION",
        baseline.get("aggregation"),
        profile.get("aggregation"),
        "window aggregation",
    )
    base_scope = baseline.get("governedScope") or {}
    live_scope = profile.get("governedScope") or {}
    scope_pair = (
        {"type": _text(base_scope.get("type")), "id": _text(base_scope.get("id"))},
        {"type": _text(live_scope.get("type")), "id": _text(live_scope.get("id"))},
    )
    _EMPTY_SCOPE = {"type": None, "id": None}
    if scope_pair[0] == _EMPTY_SCOPE and scope_pair[1] == _EMPTY_SCOPE:
        scope_state = "COMPATIBLE"  # no governed scope declared on either side
    elif scope_pair[0] == _EMPTY_SCOPE or scope_pair[1] == _EMPTY_SCOPE:
        scope_state = "UNKNOWN"  # one-sided scope cannot be proven compatible
    else:
        scope_state = "COMPATIBLE" if scope_pair[0] == scope_pair[1] else "INCOMPATIBLE"
    dimensions.append(
        {
            "dimension": "GOVERNED_SCOPE",
            "baseline": scope_pair[0],
            "live": scope_pair[1],
            "state": scope_state,
            "detail": "governed entity scope",
        }
    )

    base_window = baseline.get("windowDefinition") or {}
    live_window = profile.get("windowDefinition") or {}
    window_baseline = {
        k: base_window.get(k)
        for k in ("mode", "durationMs", "anchorTime", "windowKeyField")
        if base_window.get(k) is not None
    }
    window_live = {
        k: live_window.get(k)
        for k in ("mode", "durationMs", "anchorTime", "windowKeyField")
        if live_window.get(k) is not None
    }
    _dim(
        "WINDOW_SEMANTICS",
        window_baseline or None,
        window_live or None,
        "window mode / duration / alignment",
    )

    base_profile_ref = _text(baseline.get("metricProfileRef"))
    base_profile_digest = _text(baseline.get("metricProfileDigest"))
    if base_profile_digest is None or base_profile_ref is None:
        profile_state = "UNKNOWN"
        profile_detail = "baseline did not record its source profile identity"
    elif base_profile_ref != profile.get("profileRef"):
        profile_state = "INCOMPATIBLE"
        profile_detail = (
            "baseline was captured under a different metric profile — a "
            "semantic profile change is not system drift; requalify"
        )
    elif base_profile_digest != profile.get("profileDigest"):
        profile_state = "INCOMPATIBLE"
        profile_detail = (
            "same profile ref but different digest — the profile content "
            "changed; requalify the baseline"
        )
    else:
        profile_state = "COMPATIBLE"
        profile_detail = "baseline captured under this exact profile version"
    dimensions.append(
        {
            "dimension": "METRIC_PROFILE",
            "baseline": base_profile_ref,
            "live": profile.get("profileRef"),
            "state": profile_state,
            "detail": profile_detail,
        }
    )

    base_digests = sorted({str(d) for d in baseline.get("mappingProfileDigests") or ()})
    live_digests = sorted({str(d) for d in live_mapping_profile_refs})
    if not base_digests or not live_digests:
        map_state = "UNKNOWN"
    else:
        map_state = "COMPATIBLE" if base_digests == live_digests else "INCOMPATIBLE"
    dimensions.append(
        {
            "dimension": "MAPPING_PROFILE",
            "baseline": base_digests or None,
            "live": live_digests or None,
            "state": map_state,
            "detail": "approved mapping identity/digests",
        }
    )
    _dim(
        "SOURCE_BASIS",
        _text(baseline.get("sourceBasis")),
        _text(live_source_basis),
        "source semantic basis",
    )

    states = {d["state"] for d in dimensions}
    if "INCOMPATIBLE" in states:
        overall = "INCOMPATIBLE"
    elif "UNKNOWN" in states:
        overall = "UNKNOWN"
    else:
        overall = "COMPATIBLE"
    return {
        "overallState": overall,
        "dimensions": dimensions,
        "blockers": [d["dimension"] for d in dimensions if d["state"] == "INCOMPATIBLE"],
        "unknowns": [d["dimension"] for d in dimensions if d["state"] == "UNKNOWN"],
    }


# ---------------------------------------------------------------------------
# Drift measurement
# ---------------------------------------------------------------------------


def _relative_degradation(direction: str, baseline: float, live: float) -> float | None:
    """Exact machine math — no rounding, no epsilon, no clamping.

    A zero baseline makes the relative term undefined: returns None and the
    caller marks the window ZERO_BASELINE_RELATIVE_UNAVAILABLE. A negative
    result means the runtime improved versus baseline — preserved, never
    clamped to zero.
    """
    if baseline == 0:
        return None
    if direction == "HIGHER_IS_BETTER":
        return (baseline - live) / abs(baseline)
    return (live - baseline) / abs(baseline)


def aggregate_live_windows(
    *,
    metric_profile: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate qualified observations into per-window live values.

    Returns ``live_by_key`` (qualified members per window), ``values`` (the
    aggregated window value), ``unqualified_obs``, ``unqualified_keys``, and
    per-window ``limitations``. Used by both measurement and baseline
    derivation so the two paths can never diverge.
    """
    profile = metric_profile
    qualified_obs: list[dict[str, Any]] = [
        dict(o)
        for o in observations
        if o["metricQualification"] == "QUALIFIED"
        and o["mappingQualification"] == "QUALIFIED"
        and o["windowKey"]
    ]
    unqualified_obs = [o for o in observations if o not in qualified_obs]

    live_by_key: dict[str, list[dict[str, Any]]] = {}
    for obs in qualified_obs:
        live_by_key.setdefault(str(obs["windowKey"]), []).append(obs)

    values: dict[str, float] = {}
    window_limitations: dict[str, list[str]] = {}
    unqualified_keys: list[str] = []
    for key, members in sorted(live_by_key.items()):
        member_values = [float(o["value"]) for o in members]
        aggregation = str(profile["aggregation"])
        if aggregation == "SOURCE_VALUE" and len(members) > 1:
            window_limitations.setdefault(key, []).append(
                "MULTIPLE_OBSERVATIONS_IN_SOURCE_VALUE_WINDOW"
            )
            unqualified_keys.append(key)
            continue
        if aggregation == "LAST":
            ordered = sorted(
                members, key=lambda o: (str(o["observedAt"]), str(o["sourceEventRef"]))
            )
            values[key] = float(ordered[-1]["value"])
        else:
            aggregated = _aggregate(member_values, aggregation)
            if aggregated is None:
                unqualified_keys.append(key)
                continue
            values[key] = aggregated
    return {
        "qualifiedObservations": qualified_obs,
        "unqualifiedObservations": unqualified_obs,
        "liveByKey": live_by_key,
        "values": values,
        "limitations": window_limitations,
        "unqualifiedKeys": unqualified_keys,
    }


def measure_drift(
    *,
    run_resolution: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
    metric_profile: Mapping[str, Any],
    baseline: Mapping[str, Any],
    live_mapping_profile_refs: Sequence[str] = (),
    live_source_basis: str | None = None,
) -> dict[str, Any]:
    """Measure KPI drift for one resolved run — pure deterministic function.

    Inputs are the run resolution, the analysis snapshot's canonical events,
    a normalized ``kpi-metric-profile/0.1``, and a normalized
    ``control9-baseline/0.1``. No clock, no AI, no verdict.
    """
    profile = metric_profile
    projection = project_kpi_observations(
        metric_profile=profile,
        run_resolution=run_resolution,
        canonical_events=canonical_events,
    )
    observations = projection["observations"]
    ambiguous_refs: list[str] = projection["ambiguousCandidateRefs"]
    unresolved_refs: list[str] = projection["unresolvedCandidateRefs"]

    compatibility = compatibility_gate(
        metric_profile=profile,
        baseline=baseline,
        live_mapping_profile_refs=live_mapping_profile_refs,
        live_source_basis=live_source_basis,
    )
    compatible_overall = compatibility["overallState"] != "INCOMPATIBLE"

    # ---- live windows -----------------------------------------------------
    window_def = profile["windowDefinition"]
    expected_keys: list[str] = list(window_def.get("expectedWindowKeys") or ())
    expected_count = window_def.get("expectedWindowCount")
    expected_windows: int | None
    if expected_keys:
        expected_windows = len(expected_keys)
    elif expected_count is not None:
        expected_windows = int(expected_count)
    else:
        expected_windows = None

    aggregated = aggregate_live_windows(metric_profile=profile, observations=observations)
    qualified_obs: list[dict[str, Any]] = aggregated["qualifiedObservations"]
    unqualified_obs: list[dict[str, Any]] = aggregated["unqualifiedObservations"]
    live_by_key: dict[str, list[dict[str, Any]]] = aggregated["liveByKey"]
    live_window_values: dict[str, float] = aggregated["values"]
    window_limitations: dict[str, list[str]] = aggregated["limitations"]
    unqualified_window_keys: list[str] = aggregated["unqualifiedKeys"]

    # ---- baseline windows -------------------------------------------------
    baseline_mode = str(baseline["baselineMode"])
    baseline_fixed = baseline.get("value") if baseline_mode == "FIXED_REFERENCE_VALUE" else None
    baseline_windows: dict[str, dict[str, Any]] = {}
    if baseline_mode == "MATCHED_WINDOWS":
        for row in baseline.get("windows") or ():
            baseline_windows[str(row["windowKey"])] = dict(row)

    # The comparison perimeter: every window either side declares, plus the
    # expected set. Missing windows stay explicit — never dropped, never
    # silently zero.
    observed_window_keys = {
        str(o["windowKey"]) for o in observations if o["windowKey"]
    }
    all_keys = sorted(
        set(expected_keys) | set(live_window_values) | set(baseline_windows)
        | set(unqualified_window_keys)
        | observed_window_keys
    )
    if expected_count is not None and not expected_keys:
        # Deterministic expected ordinal keys W000..W{n-1} when only a count
        # was declared under FIXED_DURATION; SOURCE_WINDOWED without explicit
        # keys cannot fabricate expected identities.
        if window_def["mode"] == "FIXED_DURATION":
            declared = {f"W{i:04d}" for i in range(int(expected_count))}
            all_keys = sorted(set(all_keys) | declared)
        else:
            window_limitations.setdefault("__measurement__", []).append(
                "EXPECTED_WINDOW_COUNT_WITHOUT_KEYS"
            )

    windows: list[dict[str, Any]] = []
    missing_live: list[str] = []
    missing_baseline: list[str] = []
    for key in all_keys:
        live_value = live_window_values.get(key)
        live_members = live_by_key.get(key, [])
        window_lims = list(window_limitations.get(key, ()))
        if baseline_mode == "FIXED_REFERENCE_VALUE":
            baseline_value = baseline_fixed
            baseline_refs = list(baseline.get("evidenceRefs") or ())
        else:
            base_row = baseline_windows.get(key)
            baseline_value = base_row["value"] if base_row else None
            baseline_refs = list((base_row or {}).get("evidenceRefs") or ())

        state: str
        absolute_delta = relative = relative_pct = None
        if not compatible_overall:
            state = "INCOMPATIBLE"
        elif key in unqualified_window_keys:
            state = "UNQUALIFIED"
        elif live_value is None and key not in observed_window_keys:
            state = "MISSING_LIVE"  # no observation at all — never zero drift
        elif live_value is None:
            state = "UNQUALIFIED"  # observation existed but failed qualification
        elif baseline_value is None:
            state = "MISSING_BASELINE"
        elif baseline_value == 0:
            state = "ZERO_BASELINE_RELATIVE_UNAVAILABLE"
            absolute_delta = live_value - baseline_value
        else:
            absolute_delta = live_value - baseline_value
            relative = _relative_degradation(str(profile["direction"]), baseline_value, live_value)
            relative_pct = relative * 100 if relative is not None else None
            state = "COMPARABLE"

        live_refs = sorted({str(o["sourceEventRef"]) for o in live_members})
        if state == "MISSING_LIVE":
            missing_live.append(key)
        if state == "MISSING_BASELINE":
            missing_baseline.append(key)
        windows.append(
            {
                "windowKey": key,
                "windowStart": live_members[0]["windowStart"] if live_members else None,
                "windowEnd": live_members[0]["windowEnd"] if live_members else None,
                "baselineValue": baseline_value,
                "liveValue": live_value,
                "unit": str(profile["unit"]),
                "direction": str(profile["direction"]),
                "absoluteDelta": absolute_delta,
                "relativeDegradation": relative,
                "relativeDegradationPercent": relative_pct,
                "comparisonState": state,
                "baselineEvidenceRefs": baseline_refs,
                "liveEvidenceRefs": live_refs,
                "liveObservationCount": len(live_members),
                "limitations": window_lims,
            }
        )

    # Unqualified observations that carry a window key are reported inside
    # their window; observations without any window stay measurement-level.
    for obs in unqualified_obs:
        obs_key = _text(obs.get("windowKey"))
        if obs_key is None:
            continue
        for row in windows:
            if row["windowKey"] == obs_key and row["comparisonState"] != "COMPARABLE":
                row["limitations"] = sorted(
                    set(row["limitations"]) | set(obs.get("limitations") or ())
                )

    comparable = [w for w in windows if w["comparisonState"] == "COMPARABLE"]
    incompatible_windows = [w["windowKey"] for w in windows if w["comparisonState"] == "INCOMPATIBLE"]
    unqualified_windows = [
        w["windowKey"] for w in windows if w["comparisonState"] == "UNQUALIFIED"
    ]
    zero_baseline_windows = [
        w["windowKey"]
        for w in windows
        if w["comparisonState"] == "ZERO_BASELINE_RELATIVE_UNAVAILABLE"
    ]
    observed_qualified = len(live_window_values)
    coverage_pct = (
        observed_qualified / expected_windows * 100
        if expected_windows is not None and expected_windows > 0
        else None
    )

    # ---- measurement state -------------------------------------------------
    limitations: list[str] = []
    if expected_windows is None:
        limitations.append("EXPECTED_WINDOW_DENOMINATOR_NOT_ESTABLISHED")
    if compatibility["overallState"] == "UNKNOWN":
        limitations.append(
            "COMPATIBILITY_DIMENSIONS_UNKNOWN:" + ",".join(compatibility["unknowns"])
        )
    if ambiguous_refs:
        limitations.append(f"AMBIGUOUS_RUN_MEMBERSHIP_OBSERVATIONS:{len(ambiguous_refs)}")
    if unresolved_refs:
        limitations.append(f"UNRESOLVED_RUN_MEMBERSHIP_OBSERVATIONS:{len(unresolved_refs)}")
    limitations.extend(window_limitations.get("__measurement__", ()))

    resolution_state = str(run_resolution.get("resolutionState") or "")
    if resolution_state in ("NOT_RESOLVED", "AMBIGUOUS"):
        limitations.append(f"RUN_RESOLUTION_{resolution_state}")

    if not compatible_overall:
        state = "NOT_MEASURED"
        limitations.append(
            "BASELINE_LIVE_INCOMPATIBLE:" + ",".join(compatibility["blockers"])
        )
    elif resolution_state == "NOT_RESOLVED":
        state = "NOT_MEASURED"
    elif not qualified_obs:
        state = "NOT_MEASURED"
        limitations.append("NO_QUALIFIED_KPI_OBSERVATIONS")
    elif not comparable:
        state = "NOT_MEASURED"
        limitations.append("NO_COMPARABLE_WINDOWS")
    elif (
        missing_live
        or missing_baseline
        or unqualified_windows
        or incompatible_windows
        or zero_baseline_windows
        or ambiguous_refs
        or unresolved_refs
        or unqualified_obs
        or resolution_state in ("PARTIAL", "AMBIGUOUS")
        or compatibility["overallState"] == "UNKNOWN"
        or (coverage_pct is not None and coverage_pct < 100)
    ):
        state = "PARTIAL"
    else:
        state = "MEASURED"

    worst = max(
        comparable,
        key=lambda w: float(w["relativeDegradation"]),
        default=None,
    )
    most_improved = min(
        comparable,
        key=lambda w: float(w["relativeDegradation"]),
        default=None,
    )

    # Monitoring/alert evidence — the organizer-required alert layer,
    # projected strictly apart from the drift arithmetic. Only explicit
    # MONITORING_ALERT / MONITORING_RESPONSE source records bound to this
    # run are read; none recorded → null, never fabricated.
    monitoring_projection = project_monitoring_evidence(
        run_resolution=run_resolution,
        canonical_events=canonical_events,
    )
    limitations.extend(monitoring_projection["limitations"])

    return {
        "schemaVersion": CONTROL9_MEASUREMENT_SCHEMA,
        "controlCode": CONTROL9_CODE,
        "measurementType": CONTROL9_CODE,
        "runId": str(run_resolution.get("runId") or ""),
        "measurementState": state,
        "metricProfileRef": profile["profileRef"],
        "metricProfileDigest": profile["profileDigest"],
        "metricId": str(profile["metricId"]),
        "unit": str(profile["unit"]),
        "direction": str(profile["direction"]),
        "aggregation": str(profile["aggregation"]),
        "baselineRef": baseline.get("baselineRef"),
        "baselineDigest": baseline.get("baselineDigest"),
        "baselineMode": baseline_mode,
        "baselineBasis": baseline.get("basis"),
        "compatibility": compatibility,
        "expectedWindows": expected_windows,
        "observedQualifiedWindows": observed_qualified,
        "comparableMeasuredWindows": len(comparable),
        "missingWindows": {"missingLive": missing_live, "missingBaseline": missing_baseline},
        "incompatibleWindows": incompatible_windows,
        "unqualifiedWindows": unqualified_windows,
        "zeroBaselineWindows": zero_baseline_windows,
        "coveragePercent": coverage_pct,
        "windows": windows,
        "kpiObservations": observations,
        "worstRelativeDegradation": (
            {
                "windowKey": worst["windowKey"],
                "relativeDegradation": worst["relativeDegradation"],
                "relativeDegradationPercent": worst["relativeDegradationPercent"],
            }
            if worst
            else None
        ),
        "mostImprovedWindow": (
            {
                "windowKey": most_improved["windowKey"],
                "relativeDegradation": most_improved["relativeDegradation"],
                "relativeDegradationPercent": most_improved["relativeDegradationPercent"],
            }
            if most_improved and most_improved["relativeDegradation"] < 0
            else None
        ),
        "qualifiedObservationCount": len(qualified_obs),
        "unqualifiedObservationCount": len(unqualified_obs),
        "monitoring": monitoring_projection["monitoring"],
        "evidenceRefs": sorted(
            {str(o["sourceEventRef"]) for o in observations}
            | {str(r) for r in baseline.get("evidenceRefs") or ()}
            | set(monitoring_projection["monitoringEvidenceRefs"])
        ),
        "excludedEvidence": {
            "ambiguousRunRefs": ambiguous_refs,
            "unresolvedRunRefs": unresolved_refs,
            "unqualifiedObservationRefs": sorted(
                {str(o["sourceEventRef"]) for o in unqualified_obs}
            ),
        },
        "limitations": sorted(set(limitations)),
        "verdict": None,
        "verdictOwner": "HAIEC",
    }
