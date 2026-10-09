"""Deterministic event-readiness projections for Competition Mode.

Pure functions over existing deterministic state (run declarations,
resolutions, measurements, source overview, collection health). They answer
"how ready is each control / each Judgment-Day artifact" without AI and
without ever inventing HAIEC-side state — anything external stays ``UNKNOWN``
unless an explicit supplied reference exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .guidance import CAPABILITY_TRUTH, SIX_ARTIFACTS
from .run import event_identifiers

FEASIBILITY_SCHEMA = "control-feasibility/0.1"
GAP_REGISTER_SCHEMA = "competition-gap-register/0.1"
RUN_REGISTER_SCHEMA = "competition-run-register/0.1"
READINESS_SCHEMA = "judgment-day-readiness/0.1"

CONTROL7 = "AIA-LOG-001"
CONTROL9 = "AIA-ARC-006"
CONTROL16 = "ACN-COST-001"

# --------------------------------------------------------------------------
# Control feasibility
# --------------------------------------------------------------------------


def _row(state: str, missing: list[str], detail: str) -> dict[str, Any]:
    return {"state": state, "missing": missing, "detail": detail}


def control7_feasibility(
    *,
    active_run: Mapping[str, Any] | None,
    resolution: Mapping[str, Any] | None,
    manifests: Sequence[Mapping[str, Any]],
    measurement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """READY needs a resolved run, an expected-event basis, and observed events."""
    missing: list[str] = []
    limitations: list[str] = []
    if not (active_run or {}).get("runId"):
        missing.append("ACTIVE_RUN")
    elif resolution is None or str(resolution.get("resolutionState")) == "NOT_RESOLVED":
        missing.append("RUN_RESOLUTION")
    if not manifests:
        missing.append("EXPECTED_EVENT_BASIS")
    qualified = len((resolution or {}).get("qualifiedEventRefs") or ())
    if resolution is not None and qualified == 0:
        missing.append("OBSERVED_EVENTS")
    if resolution is not None and (
        resolution.get("ambiguousEvidenceRefs") or resolution.get("unresolvedEvidenceRefs")
    ):
        limitations.append("AMBIGUOUS_OR_UNRESOLVED_EVIDENCE")
    if measurement is not None and str(measurement.get("measurementState")) == "PARTIAL":
        limitations.append("PARTIAL_MEASUREMENT")

    if missing:
        detail = (
            "No expected-event basis has been reviewed. Observed events alone "
            "cannot establish expected-event coverage."
            if "EXPECTED_EVENT_BASIS" in missing
            else "Missing: " + ", ".join(missing)
        )
        state = "NOT_READY"
    elif limitations:
        state = "READY_WITH_LIMITATIONS"
        detail = "Measurable, with open evidence limitations."
    else:
        state = "READY"
        detail = "Active run, expected-event basis and observed events are in place."
    out = _row(state, missing, detail)
    if limitations:
        out["limitations"] = limitations
    return out


def control9_feasibility(
    *,
    active_run: Mapping[str, Any] | None,
    profiles: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    compatibility: Mapping[str, Any] | None,
    measurement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """READY needs a run, a metric profile, a qualified baseline, and
    compatible baseline/live semantics."""
    missing: list[str] = []
    if not (active_run or {}).get("runId"):
        missing.append("ACTIVE_RUN")
    if not profiles:
        missing.append("METRIC_PROFILE")
    if not baselines:
        missing.append("QUALIFIED_BASELINE")

    overall = str((compatibility or {}).get("overallState") or "")
    limitations: list[str] = []
    if baselines and profiles:
        if overall == "INCOMPATIBLE":
            missing.append("COMPATIBLE_SEMANTICS")
        elif overall == "UNKNOWN":
            limitations.append("COMPATIBILITY_DIMENSIONS_UNKNOWN")
        elif not overall and compatibility is None:
            limitations.append("COMPATIBILITY_NOT_PREFLIGHTED")
    if measurement is not None:
        mstate = str(measurement.get("measurementState"))
        if mstate == "PARTIAL":
            limitations.append("PARTIAL_MEASUREMENT")
        elif mstate == "NOT_MEASURED":
            limitations.append("NO_QUALIFIED_KPI_EVIDENCE")

    if missing:
        return _row("NOT_READY", missing, "Missing: " + ", ".join(missing))
    if limitations:
        return _row(
            "READY_WITH_LIMITATIONS",
            [],
            "Profile and baseline exist; " + ", ".join(limitations),
        ) | {"limitations": limitations}
    return _row(
        "READY",
        [],
        "Metric profile, qualified baseline and compatible semantics are in place.",
    )


def control16_feasibility(
    *,
    active_run: Mapping[str, Any] | None,
    resolution: Mapping[str, Any] | None,
    usage_fields_present: bool,
    measurement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """READY needs a resolved run plus qualified model-call usage semantics."""
    missing: list[str] = []
    limitations: list[str] = []
    if not (active_run or {}).get("runId"):
        missing.append("ACTIVE_RUN")
    elif resolution is None or str(resolution.get("resolutionState")) == "NOT_RESOLVED":
        missing.append("RUN_RESOLUTION")
    elif not (resolution.get("qualifiedEventRefs") or ()):
        missing.append("RUN_EVENTS")
    if not usage_fields_present:
        missing.append("QUALIFIED_TOKEN_USAGE")
    if measurement is not None:
        mstate = str(measurement.get("measurementState"))
        if mstate == "PARTIAL":
            limitations.append("PARTIAL_MEASUREMENT")
        elif mstate == "NOT_MEASURED":
            limitations.append("NO_QUALIFIED_USAGE_EVIDENCE")

    if missing:
        detail = (
            "Missing usage is not zero tokens, duplicate telemetry is not a "
            "retry, and a genuine provider retry counts again. Qualify "
            "model-call + token fields in Source Setup first."
        )
        return _row("NOT_READY", missing, detail + " Missing: " + ", ".join(missing))
    if limitations:
        return _row(
            "READY_WITH_LIMITATIONS",
            [],
            "Usage semantics qualified; " + ", ".join(limitations),
        ) | {"limitations": limitations}
    return _row("READY", [], "Model-call identity and token usage fields are qualified.")


def control_feasibility(
    *,
    active_run: Mapping[str, Any] | None,
    resolution: Mapping[str, Any] | None,
    manifests: Sequence[Mapping[str, Any]],
    c7_measurement: Mapping[str, Any] | None,
    c9_profiles: Sequence[Mapping[str, Any]],
    c9_baselines: Sequence[Mapping[str, Any]],
    c9_compatibility: Mapping[str, Any] | None,
    c9_measurement: Mapping[str, Any] | None,
    c16_usage_fields_present: bool,
    c16_measurement: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Per-control READY / READY_WITH_LIMITATIONS / NOT_READY — deterministic."""
    return {
        "schemaVersion": FEASIBILITY_SCHEMA,
        "controls": {
            CONTROL7: control7_feasibility(
                active_run=active_run,
                resolution=resolution,
                manifests=manifests,
                measurement=c7_measurement,
            ),
            CONTROL9: control9_feasibility(
                active_run=active_run,
                profiles=c9_profiles,
                baselines=c9_baselines,
                compatibility=c9_compatibility,
                measurement=c9_measurement,
            ),
            CONTROL16: control16_feasibility(
                active_run=active_run,
                resolution=resolution,
                usage_fields_present=c16_usage_fields_present,
                measurement=c16_measurement,
            ),
        },
    }


# --------------------------------------------------------------------------
# Run-ID map + source inventory (first-hour artifacts)
# --------------------------------------------------------------------------


def run_id_map(canonical_events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Observed identifier kinds across the analysis — the Run-ID Map.

    Reports which identifier kinds carry values and how many distinct values
    each holds. Timestamp proximity is never involved.
    """
    kinds: dict[str, set[str]] = {}
    for event in canonical_events:
        for kind, values in event_identifiers(event).items():
            kinds.setdefault(kind, set()).update(values)
    return {
        "schemaVersion": "run-id-map/0.1",
        "kinds": [
            {
                "kind": kind,
                "distinctValues": len(values),
                "examples": sorted(values)[:5],
            }
            for kind, values in sorted(kinds.items())
        ],
        "observedKinds": sorted(kinds),
    }


def source_inventory(overview: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Auto-populated Source Inventory rows from the deterministic overview."""
    rows: list[dict[str, Any]] = []
    for source in overview.get("sources") or ():
        rows.append(
            {
                "sourceName": source.get("path"),
                "artifactId": source.get("artifactId"),
                "sha256": source.get("sha256"),
                "format": source.get("format"),
                "sampleCaptured": True,
                "records": source.get("recordCount"),
                "parsedRecords": source.get("parsedRecordCount"),
                "canonicalEvents": source.get("canonicalEventCount"),
                "mappingState": source.get("mappingState"),
                "qualification": (source.get("evidenceQualification") or {}).get("state"),
                "adapterNeeded": source.get("mappingState") == "NO_MAPPING_AVAILABLE",
                "candidateControls": [
                    row["controlCode"] for row in (source.get("controlHints") or ())
                ],
                "knownGaps": list(source.get("limitations") or ()),
                "nextAction": source.get("nextAction"),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Gap register
# --------------------------------------------------------------------------

_GAP_COUNTER = [0]


def _gap(
    *,
    category: str,
    control: str | None,
    run: str | None,
    gap: str,
    why: str,
    consequence: str,
    supportable: str,
    next_action: str,
    refs: Sequence[str] = (),
) -> dict[str, Any]:
    _GAP_COUNTER[0] += 1
    return {
        "gapId": f"GAP-{_GAP_COUNTER[0]:04d}",
        "category": category,
        "control": control,
        "run": run,
        "gap": gap,
        "whyItMatters": why,
        "consequence": consequence,
        "whatRemainsSupportable": supportable,
        "nextAction": next_action,
        "evidenceRefs": list(refs),
    }


def _measurement_gaps(
    control: str,
    measurement: Mapping[str, Any] | None,
    *,
    run: str | None,
) -> list[dict[str, Any]]:
    if not measurement:
        return []
    rows: list[dict[str, Any]] = []
    state = str(measurement.get("measurementState") or "")
    refs = list(measurement.get("evidenceRefs") or ())[:10]
    for limitation in measurement.get("limitations") or ():
        rows.append(
            _gap(
                category="MEASUREMENT",
                control=control,
                run=str(measurement.get("runId") or run or "") or None,
                gap=str(limitation),
                why="The measurement recorded a limiting condition.",
                consequence=(
                    "The measurement does not fully cover the declared perimeter."
                    if state != "MEASURED"
                    else "Bounded qualification — measurement is usable with the stated limitation."
                ),
                supportable="The measured values that are qualified remain exact.",
                next_action="Resolve the limiting evidence or document it in the Gap List.",
                refs=refs,
            )
        )
    if control == CONTROL9 and isinstance(measurement.get("missingWindows"), Mapping):
        missing_live = measurement["missingWindows"].get("missingLive") or ()
        for window in missing_live:
            rows.append(
                _gap(
                    category="COVERAGE",
                    control=control,
                    run=str(measurement.get("runId") or run or "") or None,
                    gap=f"Expected live window missing: {window}",
                    why="A missing window is not zero drift — the denominator stays explicit.",
                    consequence="Coverage is reduced; the window contributes no comparison.",
                    supportable="Comparable windows remain exactly measured.",
                    next_action="Collect the KPI export covering this window or declare the perimeter.",
                )
            )
    if control == CONTROL7:
        for event_id in (measurement.get("missingEvents") or ())[:10]:
            rows.append(
                _gap(
                    category="EVIDENCE",
                    control=control,
                    run=str(measurement.get("runId") or run or "") or None,
                    gap=f"Expected event not observed: {event_id}",
                    why="A missing event is not proof the event did not occur.",
                    consequence="Expected-event coverage is incomplete.",
                    supportable="Matched events remain evidence-bound.",
                    next_action="Check collection scope, mapping, and the event's producer.",
                )
            )
    if control == CONTROL16 and measurement.get("missingUsageCalls"):
        rows.append(
            _gap(
                category="EVIDENCE",
                control=control,
                run=str(measurement.get("runId") or run or "") or None,
                gap=f"{measurement['missingUsageCalls']} executed call(s) lack token usage",
                why="Missing usage is not zero tokens.",
                consequence="ActualRunTokens is not fully established (PARTIAL).",
                supportable="knownQualifiedTokens remains an exact qualified subtotal.",
                next_action="Collect provider/model-gateway usage for the unqualified calls.",
            )
        )
    return rows


def gap_register(
    *,
    case_id: str,
    frontier: Sequence[Mapping[str, Any]],
    health: Mapping[str, Any],
    overview: Mapping[str, Any],
    resolution: Mapping[str, Any] | None,
    c7: Mapping[str, Any] | None,
    c9: Mapping[str, Any] | None,
    c16: Mapping[str, Any] | None,
    active_run: Mapping[str, Any] | None,
    operator_entries: Sequence[Mapping[str, Any]] = (),
    external_refs: Mapping[str, Any] | None = None,
    run_activities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Exportable Gap Register over deterministic limitations/frontiers.

    ``operator_entries`` are operator-entered POLICY/ENFORCEMENT/LAB_ACCESS
    rows; ``external_refs`` are HAIEC references explicitly supplied via
    measurement references — never inferred.
    """
    _GAP_COUNTER[0] = 0
    run_id = str((active_run or {}).get("runId") or "") or None
    rows: list[dict[str, Any]] = []

    for item in frontier or ():
        rows.append(
            _gap(
                category="EVIDENCE",
                control=None,
                run=run_id,
                gap=str(item.get("missingFact") or item.get("frontierId") or "frontier"),
                why=str(item.get("whyNeeded") or "An open evidence frontier."),
                consequence="The related claim cannot be fully established.",
                supportable="Established claims remain unchanged.",
                next_action=str(item.get("nextEvidence") or "Collect the indicated evidence."),
            )
        )

    totals = (health or {}).get("totals") or {}
    if totals.get("failedRecordCount"):
        rows.append(
            _gap(
                category="COLLECTION",
                control=None,
                run=None,
                gap=f"{totals['failedRecordCount']} record(s) failed to parse",
                why="Unparsed records cannot qualify into canonical evidence.",
                consequence="Coverage of that source is bounded.",
                supportable="Parsed records remain canonical.",
                next_action="Inspect the source in Source Setup; consider an adapter if semantics are unreachable.",
            )
        )
    for source in (overview.get("sources") or ()):
        state = str(source.get("mappingState") or "")
        if state in ("NO_MAPPING_AVAILABLE", "PROPOSAL_AVAILABLE", "APPROVAL_REJECTED_NEEDS_REVIEW"):
            rows.append(
                _gap(
                    category="MAPPING",
                    control=None,
                    run=None,
                    gap=f"{source.get('path')} — {state.replace('_', ' ').title()}",
                    why="Unmapped sources cannot produce qualified canonical evidence.",
                    consequence="That source contributes no qualified observations.",
                    supportable="The artifact remains preserved as raw evidence.",
                    next_action="Review/approve the mapping proposal, or record that no mapping exists.",
                    refs=[str(source.get("artifactId"))] if source.get("artifactId") else (),
                )
            )

    if resolution is not None:
        ambiguous = list(resolution.get("ambiguousEvidenceRefs") or ())
        unresolved = list(resolution.get("unresolvedEvidenceRefs") or ())
        if ambiguous or unresolved:
            rows.append(
                _gap(
                    category="RUN_RESOLUTION",
                    control=None,
                    run=str(resolution.get("runId") or run_id or "") or None,
                    gap=f"{len(ambiguous)} ambiguous / {len(unresolved)} unresolved evidence refs",
                    why="Ambiguous or orphaned run membership fails closed.",
                    consequence="Excluded from run-scoped measurement.",
                    supportable="Explicitly bound events remain measured.",
                    next_action="Resolve identifier conflicts or declare additional identifier sets.",
                    refs=[*ambiguous[:5], *unresolved[:5]],
                )
            )

    rows += _measurement_gaps(CONTROL7, c7, run=run_id)
    rows += _measurement_gaps(CONTROL9, c9, run=run_id)
    rows += _measurement_gaps(CONTROL16, c16, run=run_id)

    # Qualified run-activity provenance — the pre-run temporal-policy proof
    # HAIEC consumes. Missing/conflicting start is a per-run gap; measurement
    # itself is never blocked (LogSense measures descriptively either way).
    for run_id_key, run_activity in (run_activities or {}).items():
        if run_activity is None:
            continue
        activity_state = str(run_activity.get("startState") or "NOT_ESTABLISHED")
        activity_run = str(run_activity.get("runId") or run_id_key or "") or None
        if activity_state == "NOT_ESTABLISHED":
            rows.append(
                _gap(
                    category="EVIDENCE",
                    control=None,
                    run=activity_run,
                    gap="RUN_START_NOT_ESTABLISHED",
                    why=(
                        "HAIEC cannot prove the frozen governing policy "
                        "preceded the actual assessed run without an explicit "
                        "qualified run-start fact."
                    ),
                    consequence=(
                        "Pre-run temporal-policy proof is unavailable; the "
                        "Control Test may return NOT_EVALUATED."
                    ),
                    supportable=(
                        "Descriptive C7/C9/C16 measurements and the observed-"
                        "activity window remain exact."
                    ),
                    next_action=(
                        "Find and qualify the lab's actual run-start signal "
                        "(e.g. an explicit RUN_STARTED record or a mapping-"
                        "declared RUN_START field) before assessed runs."
                    ),
                    refs=list(run_activity.get("excludedStartCandidateRefs") or ())[:10],
                )
            )
        elif activity_state == "CONFLICTING":
            rows.append(
                _gap(
                    category="EVIDENCE",
                    control=None,
                    run=activity_run,
                    gap="RUN_START_EVIDENCE_CONFLICT",
                    why=(
                        "Multiple qualified facts assert different run-start "
                        "times — LogSense never picks one."
                    ),
                    consequence=(
                        "runStartedAt is null until the conflicting source "
                        "facts are reconciled."
                    ),
                    supportable="Observed-activity bounds remain exact.",
                    next_action=(
                        "Reconcile the conflicting run-start records at the "
                        "source; do not select a start time by convenience."
                    ),
                    refs=list(run_activity.get("startEvidenceRefs") or ())[:10],
                )
            )

    # HAIEC-side state is external: never inferred. An explicit supplied
    # reference upgrades the row content; otherwise it stays UNKNOWN.
    supplied = bool(external_refs and any(external_refs.values()))
    rows.append(
        _gap(
            category="POLICY",
            control=None,
            run=None,
            gap="HAIEC governing policy freeze status",
            why="Assessed runs require a frozen governing policy before evaluation.",
            consequence="No Control Test verdict can be claimed until HAIEC freezes and evaluates.",
            supportable="LogSense measurements remain exportable evidence.",
            next_action=(
                "HAIEC reference supplied — confirm it names the intended frozen version."
                if supplied
                else "UNKNOWN — freeze the governing policy in HAIEC and attach the reference."
            ),
            refs=[str(v) for v in (external_refs or {}).values() if v],
        )
    )

    # Time/clock integrity — a cross-system timing comparison is never
    # authoritative merely because two timestamps parse. When multiple
    # sources carry canonical events, clock comparability must be recorded
    # per source; until it is, the limitation stays visible.
    timed_sources = [
        str(s.get("path") or s.get("artifactId") or "?")
        for s in (overview.get("sources") or ())
        if int(s.get("canonicalEventCount") or 0) > 0
    ]
    if len(timed_sources) > 1:
        rows.append(
            _gap(
                category="LIMITATION",
                control=None,
                run=None,
                gap="CLOCK_COMPARABILITY_NOT_ESTABLISHED",
                why=(
                    "Cross-system clock skew is not verifiable from logs — a "
                    "timing comparison is not authoritative merely because "
                    "two timestamps parse."
                ),
                consequence=(
                    "Ordering/gap measurements across sources carry an "
                    "unquantified clock-skew limitation."
                ),
                supportable=(
                    "Within-source ordering and explicit-zone timestamps "
                    "remain exactly as recorded."
                ),
                next_action=(
                    "Record per-source clock basis (UTC vs local, "
                    "authoritative clock, synchronization, precision, "
                    "expected skew) in the Time/Clock Integrity check."
                ),
                refs=timed_sources[:10],
            )
        )

    for entry in operator_entries or ():
        rows.append(
            _gap(
                category=str(entry.get("category") or "POLICY"),
                control=entry.get("control"),
                run=entry.get("run"),
                gap=str(entry.get("gap") or ""),
                why=str(entry.get("whyItMatters") or ""),
                consequence=str(entry.get("consequence") or ""),
                supportable=str(entry.get("whatRemainsSupportable") or ""),
                next_action=str(entry.get("nextAction") or ""),
                refs=list(entry.get("evidenceRefs") or ()),
            )
        )

    return {
        "schemaVersion": GAP_REGISTER_SCHEMA,
        "caseId": case_id,
        "gaps": rows,
        "counts": {
            "total": len(rows),
            "byCategory": {
                category: sum(1 for row in rows if row["category"] == category)
                for category in sorted({row["category"] for row in rows})
            },
        },
        "note": (
            "Deterministic register — gaps remain visible; insufficient "
            "evidence never becomes green. HAIEC-side governance gaps appear "
            "only when explicitly supplied."
        ),
    }


# --------------------------------------------------------------------------
# Run register
# --------------------------------------------------------------------------


def run_register(
    *,
    case_id: str,
    runs: Sequence[Mapping[str, Any]],
    measurement_states: Mapping[str, Mapping[str, Any]],
    snapshot: Mapping[str, Any],
    run_activities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Exportable run register — run roles, never verdicts."""
    rows: list[dict[str, Any]] = []
    for run in runs:
        rid = str(run.get("runId"))
        states = measurement_states.get(rid) or {}
        activity = (run_activities or {}).get(rid) or {}
        rows.append(
            {
                "runId": rid,
                "label": run.get("label"),
                "runRole": run.get("runRole"),
                "scenarioLabel": run.get("scenarioLabel"),
                "resolutionState": run.get("resolutionState"),
                "evidenceSetRef": run.get("evidenceSetRef"),
                "activeSnapshotRef": snapshot.get("snapshotId"),
                # EARLIEST_OBSERVED_ACTIVITY != RUN_START — the register
                # shows both so the distinction stays visible.
                "runStartState": activity.get("startState"),
                "runStartedAt": activity.get("runStartedAt"),
                "earliestObservedActivityAt": activity.get("earliestObservedActivityAt"),
                "controlsMeasured": sorted(
                    code for code, m in states.items() if m is not None
                ),
                "measurementStates": {
                    code: (m or {}).get("measurementState")
                    for code, m in sorted(states.items())
                    if m is not None
                },
                "limitationCounts": {
                    code: len((m or {}).get("limitations") or ())
                    for code, m in sorted(states.items())
                    if m is not None
                },
                "retestOfRunId": run.get("retestOfRunId"),
            }
        )
    return {
        "schemaVersion": RUN_REGISTER_SCHEMA,
        "caseId": case_id,
        "runs": rows,
        "note": (
            "Run roles describe workflow intent only. PASS/FAIL never appears "
            "on a run — HAIEC owns the result."
        ),
    }


# --------------------------------------------------------------------------
# Judgment-Day readiness
# --------------------------------------------------------------------------


def judgment_day_readiness(
    *,
    runs: Sequence[Mapping[str, Any]],
    measurements: Mapping[str, Mapping[str, Any] | None],
    external_refs: Mapping[str, Any] | None,
    run_activity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Six-artifact + three-axis readiness. External items stay UNKNOWN."""
    measured = [code for code, m in measurements.items() if m is not None]
    roles = {str(r.get("runRole")) for r in runs}
    two_runs = "ASSESSED_PASS" in roles and "ASSESSED_BREACH" in roles
    refs = external_refs or {}
    refs_supplied = any(refs.get(k) for k in ("controlRef", "controlVersionRef", "thresholdVersionRef"))

    artifacts: dict[str, dict[str, Any]] = {
        "evidenceFile": {
            "state": "READY" if measured else "NOT_READY",
            "detail": (
                f"{len(measured)} control measurement(s) exportable."
                if measured
                else "No control measurement exists yet."
            ),
        },
        "thresholdDocument": {
            "state": "SUPPLIED_EXTERNALLY" if refs.get("thresholdVersionRef") else "UNKNOWN",
            "detail": (
                "HAIEC threshold reference attached."
                if refs.get("thresholdVersionRef")
                else "External — freeze in HAIEC; LogSense cannot infer it."
            ),
        },
        "controlTestTool": {
            "state": "PARTIAL",
            "detail": (
                "All three HAIEC Control Tests (C7/C9/C16) are technically "
                "available; event assessed: NOT YET — requires real event "
                "evidence bound through the HAIEC frozen Event Freeze."
            ),
        },
        "twoNamedRuns": {
            "state": "READY" if two_runs else "NOT_READY",
            "detail": (
                "Intended-PASS and intended-breach runs are named."
                if two_runs
                else "Name one ASSESSED_PASS and one ASSESSED_BREACH run (same frozen policy)."
            ),
        },
        "architecture": {
            "state": "TEMPLATE_AVAILABLE",
            "detail": "One-page architecture template ships in the evidence pack.",
        },
        "gapList": {
            "state": "READY",
            "detail": "Gap Register is exportable; HAIEC governance gaps only when supplied.",
        },
    }
    artifact_rows = [
        {
            **artifact,
            "name": spec["name"],
            "owner": spec["owner"],
            "help": spec["help"],
        }
        for spec, (key, artifact) in zip(SIX_ARTIFACTS, artifacts.items(), strict=True)
    ]
    all_ready = all(
        row["state"] in ("READY", "SUPPLIED_EXTERNALLY", "TEMPLATE_AVAILABLE", "PARTIAL")
        for row in artifact_rows
    )

    # Axis 1 — per-control completeness checklist. LogSense-side items are
    # deterministic; HAIEC-side items stay UNKNOWN unless refs are supplied.
    axis1_rows: list[dict[str, Any]] = []
    for spec in CAPABILITY_TRUTH["controls"]:
        code = spec["controlCode"]
        measurement = measurements.get(code)
        measured_state = (measurement or {}).get("measurementState")
        haiec_test = spec["haiecControlTest"]
        axis1_rows.append(
            {
                "controlCode": code,
                "name": spec["name"],
                "logSenseMeasurement": "AVAILABLE",
                "measured": bool(measurement),
                "measurementState": measured_state,
                "haiecControlTest": haiec_test,
                # Technical capability is not event status — this column
                # stays NOT_YET until real event evidence is bound through
                # the HAIEC frozen Event Freeze.
                "eventAssessed": spec.get("eventAssessed") or "NOT_YET",
                "policyFrozen": "SUPPLIED" if refs_supplied else "UNKNOWN",
                "namedPassRun": "ASSESSED_PASS" in roles,
                "namedBreachRun": "ASSESSED_BREACH" in roles,
            }
        )

    # Qualified run-activity provenance — the pre-run temporal-policy proof
    # surface. Descriptive measurement is never blocked by this; only the
    # HAIEC proof that the frozen policy preceded the assessed run is.
    activity = dict(run_activity or {})
    activity_state = str(activity.get("startState") or "NOT_ESTABLISHED")

    return {
        "schemaVersion": READINESS_SCHEMA,
        "sixArtifacts": artifact_rows,
        "allArtifactsPresent": all_ready,
        "axis1Controls": axis1_rows,
        "controlsMeasured": len(measured),
        # Pre-run temporal-policy proof is distinct from descriptive
        # measurement readiness. LogSense describes qualified run-activity
        # provenance; HAIEC decides whether the frozen policy preceded the
        # assessed run.
        "preRunTemporalProof": {
            "state": "PROOF_EVIDENCE_PRESENT" if activity_state == "ESTABLISHED" else "NOT_PROVEN",
            "actionable": (
                "Ready for pre-run temporal-policy proof."
                if activity_state == "ESTABLISHED"
                else (
                    "Find and qualify the lab's actual run-start signal "
                    "before assessed runs; measurement itself is not blocked."
                )
            ),
            "governanceOwner": "HAIEC",
        },
        "runActivity": activity,
        "capabilityTruth": CAPABILITY_TRUTH,
        "statement": (
            "Judgment-Day artifacts present."
            if all_ready
            else "Not all six Judgment-Day artifacts are present — see states."
        ),
    }
