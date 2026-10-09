"""Event operator projections — capability ladder, human-loop readiness,
C16 runtime posture, evidence-identity integrity, plane readiness, and
source→deployment continuity.

Pure functions over existing service outputs (first-hour dashboard,
measurements, run resolution, discovery workspace, action five-plane
coverage). No new evidence store, no inference logic — statuses are
evidence-backed only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "event-operator/0.1"

_FIVE_PLANES = (
    "requested",
    "policyAuthorized",
    "effectivelyGranted",
    "codeCapable",
    "observed",
)


def _measured(measurement: Mapping[str, Any] | None) -> bool:
    if not measurement:
        return False
    return str(measurement.get("measurementState")) in {"MEASURED", "PARTIAL"}


def haiec_control_result(measurement: Mapping[str, Any] | None) -> str | None:
    """An authoritative HAIEC Control Test result bound to a measurement,
    when one was explicitly supplied through the external references map.

    Only an explicit result value counts — a reference key existing, a
    timestamp, or a measurement merely existing is never live-event proof.
    """
    refs = (measurement or {}).get("references") or {}
    for key, value in refs.items():
        k = str(key).lower()
        if any(token in k for token in ("controltest", "control_test", "result", "verdict")):
            v = str(value).upper()
            if v in {"SATISFIED", "NOT_SATISFIED", "NOT_EVALUATED"}:
                return v
    return None


def _live_event_proven(*measurements: Mapping[str, Any] | None) -> bool:
    """DEMONSTRATED requires explicit authoritative live-event provenance —
    today the only field that can carry it is a bound HAIEC Control Test
    result on the persisted measurement. REHEARSAL / SYNTHETIC evidence is
    never promoted; absent the marker, fail conservative."""
    return any(haiec_control_result(m) for m in measurements)


def capability_ladder(
    *,
    c7: Mapping[str, Any] | None,
    c9: Mapping[str, Any] | None,
    c16: Mapping[str, Any] | None,
    bundles_present: int,
    ep_points: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    action_rows: Sequence[Mapping[str, Any]],
    analysis_present: bool,
    human_loop_recorded: int,
) -> list[dict[str, Any]]:
    """The eight-layer competition capability ladder.

    Every status is derived from existing evidence-backed state; a layer is
    never promoted on a plausible architecture. ``DEMONSTRATED`` requires a
    persisted measurement/coverage record — rehearsal and fixture evidence
    demonstrates the technical path, which the basis text states honestly.
    """
    measurements: tuple[Mapping[str, Any] | None, ...] = (c7, c9, c16)
    measured_count = sum(1 for m in measurements if _measured(m))
    fully_measured = sum(
        1
        for m in measurements
        if m is not None and m.get("measurementState") == "MEASURED"
    )
    live_proven = _live_event_proven(*measurements)

    # Layer 3 — five-plane coverage already projected per action group.
    covered_actions = sum(
        1
        for row in action_rows
        if _all_planes_present(row.get("fivePlaneCoverage"))
    )
    plane_rows = sum(1 for row in action_rows if row.get("fivePlaneCoverage"))

    observed_eps = [p for p in ep_points if p.get("state") == "OBSERVED"]
    denied_refs = int((c16 or {}).get("deniedBeforeExecutionCalls") or 0)

    adversarial = any(
        str(run.get("scenarioLabel") or "").upper() not in {"", "NONE"}
        and str(run.get("runRole") or "") in {"ASSESSED_BREACH", "OTHER", "RETEST"}
        for run in runs
    )

    layers: list[dict[str, Any]] = []

    layers.append(
        _layer(
            1,
            "One scored control completely end-to-end",
            (
                "DEMONSTRATED"
                if live_proven and fully_measured >= 1 and bundles_present >= 1
                else (
                    "TECHNICALLY_PROVEN"
                    if fully_measured >= 1 and bundles_present >= 1
                    else "NOT_YET"
                )
            ),
            basis=(
                "Technical path proven with persisted evidence. Event "
                "assessment not yet established."
                if fully_measured >= 1 and bundles_present >= 1 and not live_proven
                else f"{fully_measured}/3 controls measured with a persisted "
                "Competition Evidence Bundle."
            ),
        )
    )
    layers.append(
        _layer(
            2,
            "C7 + C9 + C16 complete",
            (
                "DEMONSTRATED"
                if live_proven and fully_measured == 3
                else (
                    "TECHNICALLY_PROVEN"
                    if fully_measured == 3
                    else ("READY_FOR_ONSITE" if measured_count else "NOT_YET")
                )
            ),
            basis=(
                f"{fully_measured}/3 controls MEASURED; {measured_count}/3 "
                "with any measurement. Rehearsal/fixture evidence is not an "
                "event assessment."
            ),
        )
    )
    layers.append(
        _layer(
            3,
            "Five-plane proof",
            (
                "DEMONSTRATED"
                if live_proven and covered_actions >= 1
                else (
                    "TECHNICALLY_PROVEN"
                    if covered_actions >= 1
                    else ("READY_FOR_ONSITE" if plane_rows else "NOT_YET")
                )
            ),
            basis=(
                f"{covered_actions} action(s) with all five planes PRESENT; "
                f"{plane_rows} action(s) carry five-plane coverage."
            ),
        )
    )
    layers.append(
        _layer(
            4,
            "ServiceNow human-governance proof",
            "READY_FOR_ONSITE" if human_loop_recorded else "NOT_YET",
            basis=(
                f"{human_loop_recorded} human-loop fact(s) recorded with "
                "evidence refs via the gap register."
                if human_loop_recorded
                else "No human-loop evidence recorded — verify onsite."
            ),
        )
    )
    layers.append(
        _layer(
            5,
            "Real-time C16",
            "ONSITE_VERIFY" if denied_refs else "NOT_YET",
            basis=(
                f"{denied_refs} denied-before-execution record(s) observed — "
                "verify onsite that a real enforcement point issued the deny "
                "before claiming prevention."
                if denied_refs
                else "No denied-before-execution evidence; no live "
                "enforcement hook proven."
            ),
        )
    )
    layers.append(
        _layer(
            6,
            "Second real enforcement point",
            "ONSITE_VERIFY" if len(observed_eps) >= 2 else "NOT_YET",
            basis=(
                f"{len(observed_eps)} observed enforcement-point "
                "candidate(s) — a second point counts only across a "
                "genuinely different operational boundary."
                if observed_eps
                else "No observed enforcement-point candidates yet."
            ),
        )
    )
    layers.append(
        _layer(
            7,
            "Adversarial scenario",
            "ONSITE_VERIFY" if adversarial else "NOT_YET",
            basis=(
                "A declared breach/adversarial-labelled run exists."
                if adversarial
                else "No adversarial scenario run declared."
            ),
        )
    )
    layers.append(
        _layer(
            8,
            "Forensic time-window exploration + HAIEC deterministic Control Test",
            "AVAILABLE" if analysis_present else "NOT_YET",
            basis=(
                "Timeline/forensic window available; HAIEC Control Test "
                "technically available — event assessed NOT YET."
                if analysis_present
                else "Run deterministic analysis first."
            ),
        )
    )
    return layers


def _layer(number: int, name: str, state: str, *, basis: str) -> dict[str, Any]:
    return {"layer": number, "name": name, "state": state, "basis": basis}


def _all_planes_present(coverage: Any) -> bool:
    if not isinstance(coverage, Mapping):
        return False
    for plane in _FIVE_PLANES:
        cell = coverage.get(plane)
        if not isinstance(cell, Mapping) or cell.get("state") != "PRESENT":
            return False
    return True


def plane_readiness_rows(
    action_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """DECLARED / AUTHORIZED vs OBSERVED — aggregate five-plane coverage
    states over the existing action projection. Unknown stays unknown."""
    counts: dict[str, dict[str, int]] = {
        plane: {"PRESENT": 0, "PARTIAL": 0, "UNKNOWN": 0, "ABSENT": 0}
        for plane in _FIVE_PLANES
    }
    assessed = 0
    for row in action_rows:
        coverage = row.get("fivePlaneCoverage")
        if not isinstance(coverage, Mapping):
            continue
        assessed += 1
        for plane in _FIVE_PLANES:
            cell = coverage.get(plane) or {}
            state = str(cell.get("state") or "UNKNOWN")
            bucket = counts[plane]
            bucket[state if state in bucket else "UNKNOWN"] += 1
    return {
        "schemaVersion": SCHEMA,
        "actionsAssessed": assessed,
        "planes": [
            {"plane": plane, "counts": counts[plane]} for plane in _FIVE_PLANES
        ],
    }


def human_loop_rows(
    *,
    c9: Mapping[str, Any] | None,
    operator_gap_entries: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """C9 ServiceNow human-loop checklist.

    Each row is backed by existing data only: the C9 measurement for the
    breach-observed row, or operator gap entries (control AIA-ARC-006,
    category ENFORCEMENT) whose text matches the item's terms. A row with
    evidence refs is EVIDENCE_RECORDED; without refs DECLARED; otherwise
    NOT ESTABLISHED. Silence is never upgraded.
    """
    entries = [
        e
        for e in operator_gap_entries
        if e.get("control") in (None, "", "AIA-ARC-006")
    ]
    rows: list[dict[str, Any]] = []
    for spec in items:
        key = str(spec.get("key"))
        if key == "c9Measurement":
            # C9 MEASUREMENT EXISTS != C9 BREACH OBSERVED — LogSense reports
            # the measurement state and evidence, never a breach call.
            state = str((c9 or {}).get("measurementState") or "NOT_MEASURED")
            rows.append(
                {
                    "item": spec["item"],
                    "state": state,
                    "evidenceRefs": (
                        list((c9 or {}).get("evidenceRefs") or ())[:8] if c9 else []
                    ),
                    "basis": (
                        "LogSense establishes the drift measurement — not "
                        "the breach."
                        if c9
                        else "no C9 measurement yet"
                    ),
                }
            )
            continue
        if key == "haiecResult":
            result = haiec_control_result(c9)
            rows.append(
                {
                    "item": spec["item"],
                    "state": result or "NOT ESTABLISHED — AWAITING HAIEC CONTROL TEST",
                    "evidenceRefs": [],
                    "basis": (
                        "HAIEC owns threshold D / violating-window B9 and the "
                        "final breach determination — LogSense never compares "
                        "drift against guessed or organizer-example thresholds."
                    ),
                }
            )
            continue
        if key == "evidenceRef":
            refd = sum(
                1 for e in entries if e.get("evidenceRefs")
            )
            rows.append(
                {
                    "item": spec["item"],
                    "state": "EVIDENCE_RECORDED" if refd else "NOT ESTABLISHED",
                    "evidenceRefs": [
                        r
                        for e in entries
                        for r in list(e.get("evidenceRefs") or ())
                    ][:8],
                    "basis": f"{refd} operator gap entr(y/ies) carry evidence refs",
                }
            )
            continue
        terms = tuple(str(t).lower() for t in spec.get("terms") or ())
        matched = [
            e
            for e in entries
            if terms
            and any(
                term
                in " ".join(
                    str(e.get(field) or "")
                    for field in ("gap", "nextAction", "whatRemainsSupportable", "consequence")
                ).lower()
                for term in terms
            )
        ]
        refs = [
            r
            for e in matched
            for r in list(e.get("evidenceRefs") or ())
        ]
        rows.append(
            {
                "item": spec["item"],
                "state": (
                    "EVIDENCE_RECORDED" if refs else ("DECLARED" if matched else "NOT ESTABLISHED")
                ),
                "evidenceRefs": refs[:8],
                "basis": (
                    f"{len(matched)} operator gap entr(y/ies) match"
                    if matched
                    else "record via the gap register when observed"
                ),
            }
        )
    return rows


def c16_runtime_posture(
    c16: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The three distinct C16 outcomes over the existing measurement —
    prevention evidence is never merged with executed usage."""
    if not c16:
        return {
            "schemaVersion": SCHEMA,
            "measured": False,
            "withinCap": None,
            "preventedAttempts": 0,
            "preventedRefs": [],
            "executedCalls": 0,
            "actualTokens": None,
        }
    return {
        "schemaVersion": SCHEMA,
        "measured": True,
        "measurementState": c16.get("measurementState"),
        "withinCap": None,  # cap comparison is HAIEC's frozen policy — never ours
        "preventedAttempts": int(c16.get("deniedBeforeExecutionCalls") or 0),
        "preventedRefs": list(
            (c16.get("excludedEvidence") or {}).get("deniedBeforeExecutionRefs") or ()
        )[:10],
        "executedCalls": int(c16.get("providerExecutedCalls") or 0),
        "actualTokens": c16.get("actualRunTokens"),
    }


def evidence_identity_rows(
    *,
    resolution: Mapping[str, Any] | None,
    run_activity: Mapping[str, Any] | None,
    clock: Mapping[str, Any] | None,
    c16: Mapping[str, Any] | None,
    source_rows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """EVIDENCE IDENTITY INTEGRITY — each row shows what existing canonical
    identity establishes, or an explicit NOT ESTABLISHED gap."""
    rows: list[dict[str, Any]] = []

    run_id = (resolution or {}).get("runId")
    rows.append(
        _identity_row(
            "Authoritative run ID",
            str(run_id) if run_id else None,
            (resolution or {}).get("bindingBasis"),
        )
    )

    start = run_activity or {}
    start_state = (
        start.get("startState")
        or start.get("state")
        or (start.get("runStart") or {}).get("startState")
    )
    start_basis = start.get("startBasis") or start.get("basis")
    rows.append(
        _identity_row(
            "Authoritative run-start source",
            str(start_state) if start_state else None,
            start_basis,
        )
    )

    identifiers = (resolution or {}).get("identifiers") or {}
    corr: list[str] = []
    for key in ("traceIds", "requestIds", "sessionIds"):
        values = (resolution or {}).get(key) or identifiers.get(key) or []
        corr.extend(str(v) for v in values)
    rows.append(
        _identity_row(
            "Correlation / trace IDs",
            f"{len(set(corr))} observed" if corr else None,
            None,
        )
    )

    source_names = [
        str(s.get("sourceId") or s.get("displayName") or "")
        for s in source_rows
        if s.get("sourceId") or s.get("displayName")
    ]
    rows.append(
        _identity_row(
            "Source native IDs",
            f"{len(set(source_names))} source(s)" if source_names else None,
            None,
        )
    )

    clock_state = (clock or {}).get("state")
    rows.append(
        _identity_row(
            "Clock-domain / comparability",
            str(clock_state) if clock_state else None,
            None,
        )
    )

    agents = (resolution or {}).get("agentIds") or []
    rows.append(
        _identity_row(
            "Deployment / runtime identity",
            f"{len(set(agents))} agent identit(y/ies)" if agents else None,
            None,
        )
    )

    suppressed = int((c16 or {}).get("duplicateTelemetryRecordsSuppressed") or 0)
    dup_groups = (c16 or {}).get("duplicateGroups") or []
    if suppressed or dup_groups:
        mirrored = f"{suppressed} duplicate record(s) suppressed / {len(dup_groups)} group(s)"
    else:
        mirrored = None
    rows.append(
        _identity_row(
            "Mirrored-telemetry status",
            mirrored,
            None,
            missing_is_gap=False,
        )
    )
    return rows


def _identity_row(
    label: str, value: Any, basis: Any, *, missing_is_gap: bool = True
) -> dict[str, Any]:
    if value:
        state = "ESTABLISHED"
    elif missing_is_gap:
        state = "NOT ESTABLISHED"
    else:
        state = "NOT OBSERVED"
    return {"item": label, "state": state, "value": value, "basis": basis}


def deployment_continuity_rows(
    overview_sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Source → deployment continuity. No binding path is invented — absent
    bound source/config evidence the CODE_CAPABLE plane stays NOT
    ESTABLISHED and the operator relies on other planes."""
    kinds = {
        str(s.get("sourceKind") or s.get("adapterId") or "").lower()
        for s in overview_sources
    }
    has_source_like = any(
        token in " ".join(kinds)
        for token in ("git", "source", "code", "repo", "archive", "zip", "config")
    )
    return {
        "schemaVersion": SCHEMA,
        "codeCapable": "BOUND_CANDIDATE_PRESENT" if has_source_like else "NOT ESTABLISHED",
        "sourceLikeArtifacts": sum(
            1
            for s in overview_sources
            if str(s.get("sourceKind") or s.get("adapterId") or "").lower()
            in kinds
            and has_source_like
            and any(
                token in str(s.get("sourceKind") or s.get("adapterId") or "").lower()
                for token in ("git", "source", "code", "repo", "archive", "zip", "config")
            )
        ),
        "note": (
            "No binding proof that source evidence is the deployed organizer "
            "source — identity must be established by evidence, not assumed."
        ),
    }
