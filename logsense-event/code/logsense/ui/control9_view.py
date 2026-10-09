"""Control 9 / AIA-ARC-006 — drift & performance measurement panel.

Operator-facing projection of the deterministic measurement. LogSense
measures how the selected KPI changed against an evidence-bound baseline;
HAIEC owns the governing baseline version, the drift threshold, the
violating-window allowance, and the final Control Test verdict.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from logsense.competition.control9 import (
    AGGREGATIONS,
    BASELINE_BASES,
    CONTROL9_CODE,
    DIRECTIONS,
    WINDOW_MODES,
)
from logsense.competition.fixture_packs import fixture_names, list_fixtures
from logsense.competition.guidance import HAIEC_EVENT_FOOTNOTE
from logsense.competition.run import CompetitionRunError
from logsense.integrations.service import IntegrationRequestError
from logsense.ui import shared
from logsense.workspace.cases import CaseWorkspaceError

_C9_FIXTURES = {m["fixtureId"]: m for m in list_fixtures() if m.get("control") == CONTROL9_CODE}

_C9_ERRORS = (IntegrationRequestError, CaseWorkspaceError, CompetitionRunError, ValueError)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fmt_value(value: Any) -> str:
    return f"{float(value):g}" if isinstance(value, (int, float)) else "—"


def _fmt_pct(value: Any) -> str:
    # Display-only rounding — machine payloads keep exact values.
    return f"{float(value):.2f}%" if isinstance(value, (int, float)) else "—"


def _help() -> None:
    with st.expander("What is Control 9 asking?", expanded=False):
        st.caption(
            "**What is this?** A drift measurement — how the selected runtime KPI "
            "changed from an evidence-bound baseline across comparable windows. "
            "**Why does it matter?** The competition asks whether observed "
            "performance drifted; LogSense produces the measured change and its "
            "evidence, not a pass/fail. **What remains unknown?** Whether the "
            "drift breaches the governing threshold — HAIEC owns that Control "
            "Test. **Next:** pick a metric profile, map the real KPI fields, "
            "select a baseline, run Compatibility Preflight, then Measure Drift."
        )
    with st.expander("What does KPI direction mean?", expanded=False):
        st.caption(
            "`HIGHER_IS_BETTER` — a higher value is healthier (e.g. a success "
            "rate); degradation is `(baseline − live) / baseline`. "
            "`LOWER_IS_BETTER` — a lower value is healthier (e.g. latency); "
            "degradation is `(live − baseline) / baseline`. Direction is "
            "explicit profile data — it is never inferred from the metric name."
        )
    with st.expander("What is a comparable window?", expanded=False):
        st.caption(
            "A window where the baseline and the live run share the same "
            "metric identity, unit, direction, aggregation, scope, and window "
            "semantics — verified by the Compatibility Preflight. Values that "
            "differ in semantics are never drifted against each other; a "
            "semantic profile change is not system drift."
        )
    with st.expander("Why do I need a baseline?", expanded=False):
        st.caption(
            "Drift is *change relative to a declared evidence basis*. Without "
            "an immutable, evidence-bound baseline there is nothing honest to "
            "compare against. The LogSense baseline is descriptive — HAIEC "
            "later adopts a governing baseline version for its Control Test."
        )
    with st.expander("What if the baseline is zero? What if a window is missing?", expanded=False):
        st.caption(
            "A zero baseline makes relative degradation undefined — LogSense "
            "keeps the absolute delta and reports "
            "`ZERO_BASELINE_RELATIVE_UNAVAILABLE` instead of inventing a "
            "denominator. A missing expected window reduces coverage and is "
            "reported explicitly — a missing window is never zero drift."
        )
    with st.expander("Who decides whether the control passed?", expanded=False):
        st.caption(
            "HAIEC — it applies the frozen governing baseline, drift threshold "
            "and permitted violating-window allowance. LogSense outputs always "
            "carry `verdict: null`, `verdictOwner: HAIEC`."
        )


def _profile_form(prefix: str, seed: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Visual metric-profile editor — clone/clone-from-example or create.

    No JSON required for normal operation. Direction and unit are explicit
    operator choices; nothing is inferred.
    """
    seed = seed or {}
    value_source = dict(seed.get("valueSource") or {})
    window = dict(seed.get("windowDefinition") or {})
    scope = dict(seed.get("governedScope") or {})
    c1, c2 = st.columns(2)
    profile_id = c1.text_input(
        "Profile ID",
        value=str(seed.get("profileId") or ""),
        key=f"{prefix}_pid",
        help="Immutable identity — clone the example profile into your real KPI id.",
    )
    seed_version = seed.get("profileVersion")
    version = c2.number_input(
        "Profile version",
        min_value=1,
        value=seed_version if isinstance(seed_version, int) else 1,
        key=f"{prefix}_ver",
        help="Never edit a version in place — bump the version for any semantic change.",
    )
    c1, c2 = st.columns(2)
    metric_id = c1.text_input(
        "Metric ID", value=str(seed.get("metricId") or ""), key=f"{prefix}_metric"
    )
    display = c2.text_input(
        "Display name", value=str(seed.get("displayName") or ""), key=f"{prefix}_name"
    )
    c1, c2, c3 = st.columns(3)
    unit = c1.text_input("Unit", value=str(seed.get("unit") or ""), key=f"{prefix}_unit")
    direction = c2.selectbox(
        "Direction",
        DIRECTIONS,
        index=DIRECTIONS.index(str(seed.get("direction")))
        if str(seed.get("direction")) in DIRECTIONS
        else 0,
        key=f"{prefix}_dir",
        help="HIGHER_IS_BETTER: score/availability. LOWER_IS_BETTER: latency/error rate.",
    )
    aggregation = c3.selectbox(
        "Window aggregation",
        AGGREGATIONS,
        index=AGGREGATIONS.index(str(seed.get("aggregation")))
        if str(seed.get("aggregation")) in AGGREGATIONS
        else 0,
        key=f"{prefix}_agg",
    )
    c1, c2 = st.columns(2)
    scope_type = c1.text_input(
        "Governed scope type (optional)",
        value=str(scope.get("type") or ""),
        key=f"{prefix}_stype",
    )
    scope_id = c2.text_input(
        "Governed scope ID (optional)",
        value=str(scope.get("id") or ""),
        key=f"{prefix}_sid",
    )
    st.caption("**Real KPI field bindings** — the source attributes that carry each fact.")
    c1, c2 = st.columns(2)
    value_field = c1.text_input(
        "KPI value field *",
        value=str(value_source.get("field") or ""),
        key=f"{prefix}_vfield",
    )
    metric_name_field = c2.text_input(
        "Metric-name field (recommended)",
        value=str(value_source.get("metricNameField") or ""),
        key=f"{prefix}_mfield",
    )
    c1, c2 = st.columns(2)
    unit_field = c1.text_input(
        "Unit field (optional)",
        value=str(value_source.get("unitField") or ""),
        key=f"{prefix}_ufield",
    )
    scope_field = c2.text_input(
        "Scope/entity field (optional)",
        value=str(value_source.get("scopeIdField") or ""),
        key=f"{prefix}_sfield",
    )
    ts_field = st.text_input(
        "Timestamp field (optional — bounded defaults used when empty)",
        value=str(seed.get("timestampSource") or ""),
        key=f"{prefix}_ts",
    )
    mode = st.selectbox(
        "Window mode",
        WINDOW_MODES,
        index=WINDOW_MODES.index(str(window.get("mode")))
        if str(window.get("mode")) in WINDOW_MODES
        else 0,
        key=f"{prefix}_wmode",
        help="SOURCE_WINDOWED: the producer already emits window identity. "
        "FIXED_DURATION: bucket raw observations deterministically.",
    )
    window_key_field = duration_ms = anchor = None
    if mode == "SOURCE_WINDOWED":
        window_key_field = st.text_input(
            "Window-key field *",
            value=str(window.get("windowKeyField") or ""),
            key=f"{prefix}_wkf",
        )
    else:
        c1, c2 = st.columns(2)
        seed_duration = window.get("durationMs")
        duration_ms = c1.number_input(
            "Window duration (ms) *",
            min_value=1,
            value=seed_duration if isinstance(seed_duration, int) else 60000,
            key=f"{prefix}_wdur",
        )
        anchor = c2.text_input(
            "Alignment anchor (ISO-8601) *",
            value=str(window.get("anchorTime") or ""),
            key=f"{prefix}_wanchor",
        )
    expected_keys_raw = st.text_input(
        "Expected window keys (comma-separated, optional)",
        value=", ".join(window.get("expectedWindowKeys") or ()),
        key=f"{prefix}_wkeys",
        help="The expected-window denominator — without it coverage is reported "
        "as unknown, never fabricated as 100%.",
    )
    expected_count_raw = st.text_input(
        "Expected window count (optional, when keys are not named)",
        value=str(window.get("expectedWindowCount") or ""),
        key=f"{prefix}_wcount",
    )
    if not (profile_id and metric_id and unit and value_field):
        st.caption("Profile ID, Metric ID, Unit and KPI value field are required.")
        return None
    window_def: dict[str, Any] = {"mode": mode}
    if mode == "SOURCE_WINDOWED":
        if not window_key_field:
            st.caption("SOURCE_WINDOWED needs the window-key field name.")
            return None
        window_def["windowKeyField"] = window_key_field
    else:
        if not anchor:
            st.caption("FIXED_DURATION needs an alignment anchor.")
            return None
        window_def["durationMs"] = duration_ms
        window_def["anchorTime"] = anchor
    expected_keys = [k.strip() for k in expected_keys_raw.split(",") if k.strip()]
    if expected_keys:
        window_def["expectedWindowKeys"] = expected_keys
    elif expected_count_raw.strip():
        try:
            window_def["expectedWindowCount"] = int(expected_count_raw.strip())
        except ValueError:
            st.caption("Expected window count must be an integer.")
            return None
    return {
        "profileSchemaVersion": "kpi-metric-profile/0.1",
        "profileId": profile_id.strip(),
        "profileVersion": int(version),
        "metricId": metric_id.strip(),
        "displayName": display.strip() or metric_id.strip(),
        "unit": unit.strip(),
        "direction": direction,
        "aggregation": aggregation,
        "governedScope": (
            {"type": scope_type.strip() or None, "id": scope_id.strip() or None}
            if (scope_type.strip() or scope_id.strip())
            else None
        ),
        "valueSource": {
            "field": value_field.strip(),
            "metricNameField": metric_name_field.strip() or None,
            "unitField": unit_field.strip() or None,
            "scopeIdField": scope_field.strip() or None,
        },
        "timestampSource": ts_field.strip() or None,
        "windowDefinition": window_def,
        "zeroBaselineRule": "RELATIVE_UNAVAILABLE",
        "createdAt": seed.get("createdAt") or _utc_now(),
        "sourceBasis": str(seed.get("sourceBasis") or "USER_DECLARED"),
        "limitations": list(seed.get("limitations") or ()),
    }


def _render_compatibility(preview: dict[str, Any]) -> None:
    gate = preview.get("compatibility") or {}
    overall = str(gate.get("overallState") or "UNKNOWN")
    badge = {"COMPATIBLE": "Compatible", "INCOMPATIBLE": "Incompatible", "UNKNOWN": "Unknown"}[
        overall
    ]
    if overall == "COMPATIBLE":
        st.success(f"**Overall compatibility: {badge}**")
    elif overall == "INCOMPATIBLE":
        st.error(f"**Overall compatibility: {badge}**")
    else:
        st.warning(f"**Overall compatibility: {badge}**")
    rows = [
        {
            "Dimension": str(d["dimension"]).replace("_", " ").title(),
            "Baseline": json.dumps(d.get("baseline"))
            if isinstance(d.get("baseline"), (dict, list))
            else str(d.get("baseline") or "—"),
            "Live": json.dumps(d.get("live"))
            if isinstance(d.get("live"), (dict, list))
            else str(d.get("live") or "—"),
            "Status": str(d["state"]).title(),
            "Detail": d.get("detail") or "",
        }
        for d in gate.get("dimensions") or ()
    ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    if overall == "INCOMPATIBLE":
        st.caption(
            "Blocked dimensions: "
            + ", ".join(gate.get("blockers") or ())
            + ". Resolve the semantic difference or create a compatible profile/baseline "
            "version — LogSense will not treat this difference as system drift."
        )


def _render_measurement(measurement: dict[str, Any]) -> None:
    state = str(measurement.get("measurementState") or "NOT_MEASURED")
    st.markdown(f"**Measurement: `{state}`**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Metric Profile", measurement.get("metricProfileRef") or "—")
    c2.metric("Baseline", measurement.get("baselineRef") or "—")
    expected = measurement.get("expectedWindows")
    c3.metric(
        "Expected / Observed / Comparable",
        f"{expected if expected is not None else 'unknown'} / "
        f"{measurement.get('observedQualifiedWindows', 0)} / "
        f"{measurement.get('comparableMeasuredWindows', 0)}",
    )
    c4.metric("Coverage", _fmt_pct(measurement.get("coveragePercent")))
    worst = measurement.get("worstRelativeDegradation")
    improved = measurement.get("mostImprovedWindow")
    if worst:
        st.metric(
            f"Worst relative degradation — {worst['windowKey']}",
            _fmt_pct(worst.get("relativeDegradationPercent")),
        )
    if improved:
        st.metric(
            f"Most improved window — {improved['windowKey']}",
            _fmt_pct(improved.get("relativeDegradationPercent")),
            help="Negative relative degradation = runtime improved vs baseline.",
        )

    windows = measurement.get("windows") or []
    if windows:
        st.markdown("**Window comparison**")
        st.dataframe(
            [
                {
                    "Window": w["windowKey"],
                    "Baseline": _fmt_value(w.get("baselineValue")),
                    "Live": _fmt_value(w.get("liveValue")),
                    "Abs. Delta": _fmt_value(w.get("absoluteDelta")),
                    "Rel. Degradation": _fmt_pct(w.get("relativeDegradationPercent")),
                    "State": str(w["comparisonState"]).replace("_", " "),
                    "Evidence": len(w.get("liveEvidenceRefs") or ())
                    + len(w.get("baselineEvidenceRefs") or ()),
                }
                for w in windows
            ],
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Baseline vs live — window chart", expanded=False):
            chart_rows = {
                "baseline": {
                    w["windowKey"]: w.get("baselineValue") for w in windows
                },
                "live": {w["windowKey"]: w.get("liveValue") for w in windows},
            }
            st.line_chart(chart_rows)
            st.caption("Missing windows appear as gaps — values are never fabricated.")

    # Gaps / incompatibility — separate, never lumped into "failed".
    missing = measurement.get("missingWindows") or {}
    gap_groups = {
        "Missing live windows": missing.get("missingLive") or [],
        "Missing baseline windows": missing.get("missingBaseline") or [],
        "Incompatible windows": measurement.get("incompatibleWindows") or [],
        "Unqualified windows": measurement.get("unqualifiedWindows") or [],
        "Zero-baseline windows": measurement.get("zeroBaselineWindows") or [],
    }
    if any(gap_groups.values()):
        with st.expander("Gaps / incompatibility", expanded=True):
            for label, keys in gap_groups.items():
                if keys:
                    st.write(f"- **{label}:** {', '.join(f'`{k}`' for k in keys)}")
    limitations = measurement.get("limitations") or []
    if limitations:
        with st.expander("Limitations", expanded=state != "MEASURED"):
            for item in limitations:
                st.write(f"- `{item}`")

    with st.expander("Window evidence drilldown", expanded=False):
        for w in windows:
            st.markdown(
                f"**`{w['windowKey']}`** — {str(w['comparisonState']).replace('_', ' ')}"
            )
            c1, c2 = st.columns(2)
            c1.caption(
                "Baseline evidence: "
                + (", ".join(f"`{r}`" for r in w.get("baselineEvidenceRefs") or ()) or "none")
            )
            c2.caption(
                "Live evidence: "
                + (", ".join(f"`{r}`" for r in w.get("liveEvidenceRefs") or ()) or "none")
            )
            if w.get("limitations"):
                st.caption("Limitations: " + ", ".join(f"`{x}`" for x in w["limitations"]))
        observations = measurement.get("kpiObservations") or []
        if observations:
            st.markdown("**KPI observations**")
            st.dataframe(
                [
                    {
                        "Event": o.get("sourceEventRef"),
                        "Window": o.get("windowKey") or "—",
                        "Value": _fmt_value(o.get("value")),
                        "Observed": o.get("observedAt") or "—",
                        "Mapping": o.get("mappingQualification"),
                        "Metric": o.get("metricQualification"),
                    }
                    for o in observations
                ],
                use_container_width=True,
                hide_index=True,
            )


def render_control9_panel(case_id: str) -> None:
    """Functional Control 9 operator flow: active run → metric profile → real
    KPI mapping → baseline → compatibility preflight → measure → handoff."""
    svc = shared.service()

    st.markdown("#### Control 9 — Drift & Performance")
    st.caption(
        "How did the selected runtime KPI change from its baseline across "
        "comparable measurement windows? LogSense measures the KPI and evidence "
        "quality. HAIEC owns the governing baseline/threshold and the final "
        "Control Test result."
    )
    _help()

    if _C9_FIXTURES:
        with st.expander("Optional: load a built-in Control 9 fixture", expanded=False):
            pick = st.selectbox(
                "Fixture",
                [n for n in fixture_names() if n in _C9_FIXTURES],
                format_func=lambda name: f"{name} — {_C9_FIXTURES[name]['label']}",
                key="c9_fixture_pick",
            )
            st.caption(_C9_FIXTURES[pick]["description"])
            if st.button("Load fixture into this case", key="c9_fixture_load"):
                try:
                    with st.spinner(
                        "Importing fixture evidence, resolving run, measuring…"
                    ):
                        output = svc.import_competition_fixture(
                            case_id=case_id, fixture_name=pick
                        )
                except _C9_ERRORS as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        f"Fixture loaded — run `{output['run']['runId']}` "
                        f"({output['run']['resolutionState']}), "
                        f"measurement `{output['measurement']['measurementState']}`."
                    )
                    st.rerun()

    # ---- 1. Active run ------------------------------------------------------
    st.markdown("**1 — Active run**")
    active = svc.active_run(case_id)
    run_id = str(active.get("runId") or "")
    if not run_id:
        st.info("No active run — confirm one on the Runs step first.")
        return
    st.write(
        f"`{run_id}` — {active.get('runRole') or 'no role'} · "
        f"scenario {active.get('scenarioLabel') or '—'}"
    )
    snapshot = svc.analysis_snapshot_state(case_id)
    st.caption(
        f"Analysis snapshot: `{snapshot.get('snapshotId') or '—'}` · "
        f"evidence set `{active.get('evidenceSetRef') or '—'}`"
    )

    # ---- 2. Metric profile --------------------------------------------------
    st.markdown("**2 — Metric profile**")
    builtin = svc.builtin_control9_profiles()
    saved = svc.list_control9_profiles(case_id)
    if saved:
        options = {str(p["profileRef"]): p for p in saved}
        pick = st.selectbox(
            "Saved metric profile", list(options), key="c9_profile_pick"
        )
        profile = options[pick]
        st.caption(
            f"`{profile['profileRef']}` · metric `{profile['metricId']}` · "
            f"{profile['unit']} · {str(profile['direction']).replace('_', ' ')} · "
            f"{profile['aggregation']}"
        )
    else:
        profile = None
        st.info("No metric profile saved yet — adopt an example or create one below.")
    seed: dict[str, Any] | None = None
    with st.expander("Adopt / clone / create a metric profile", expanded=not saved):
        template = st.radio(
            "Starting point",
            ["Blank", *[str(p["profileRef"]) for p in builtin]],
            horizontal=True,
            key="c9_profile_template",
        )
        for p in builtin:
            if str(p["profileRef"]) == template:
                seed = p
        if seed:
            st.caption(
                "ILLUSTRATIVE EXAMPLE — clone it into your real KPI before assessed use."
            )
        st.caption(
            "Cloning creates a new immutable profile version — never edit a "
            "profile already used for assessed evidence."
        )
        draft = _profile_form("c9_new", seed)
        if st.button("Save metric profile", key="c9_profile_save"):
            if draft is None:
                st.error("Fill the required fields first.")
            else:
                try:
                    profile = svc.save_control9_profile(case_id=case_id, profile=draft)
                except _C9_ERRORS as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Saved `{profile['profileRef']}` ({profile['profileDigest'][:19]}…)")
                    st.rerun()
    with st.expander("Using the real event KPI", expanded=False):
        st.caption(
            "The included metric profiles are examples. When the lab provides "
            "the real KPI, open Source Setup, identify and approve the source "
            "value/time/scope fields, then clone or create a Metric Profile "
            "with the correct metric ID, unit, direction, aggregation and "
            "window. Select a known-good/calibration baseline and rerun "
            "Compatibility Preflight. No engine code change is required."
        )

    # ---- 3. Real KPI mapping -------------------------------------------------
    st.markdown("**3 — Real KPI mapping**")
    if profile is None:
        st.warning("Select or save a metric profile first.")
        return
    vs = profile.get("valueSource") or {}
    st.caption(
        f"Value ← `{vs.get('field')}` · metric name ← `{vs.get('metricNameField') or '—'}` · "
        f"timestamp ← `{profile.get('timestampSource') or 'bounded defaults'}` · "
        f"scope ← `{vs.get('scopeIdField') or '—'}` · unit ← `{vs.get('unitField') or 'profile'}`"
    )
    approvals = svc.load_case_mapping_approvals(case_id)
    if approvals:
        st.caption(
            "Approved source mappings: "
            + ", ".join(
                f"`{e.mapping_profile.get('profileId')}`" for e in approvals.values()
            )
        )
        st.caption("Mapping qualification: QUALIFIED (approved runtime mapping)")
    else:
        st.warning(
            "No approved source mappings — LogSense cannot establish drift until "
            "it knows which qualified source field represents this Metric "
            "Profile's value. Open Source Setup, approve the proposal for the "
            "KPI artifact, then rerun analysis."
        )
        if st.button("Open Source Setup", key="c9_open_src"):
            st.switch_page("pages/source_mapping.py")

    # ---- 4. Baseline ---------------------------------------------------------
    st.markdown("**4 — Baseline**")
    baselines = svc.list_control9_baselines(case_id)
    baseline = None
    if baselines:
        b_options = {str(b["baselineRef"]): b for b in baselines}
        b_pick = st.selectbox("Saved baseline", list(b_options), key="c9_base_pick")
        baseline = b_options[b_pick]
        b = baseline
        st.caption(
            f"`{b['baselineRef']}` · {str(b['baselineMode']).replace('_', ' ')} · "
            f"basis {b['basis']} · "
            + (
                f"value {_fmt_value(b.get('value'))}"
                if b["baselineMode"] == "FIXED_REFERENCE_VALUE"
                else f"{len(b.get('windows') or ())} windows"
            )
            + f" · source run {b.get('sourceRunId') or '—'}"
        )
    with st.expander("Create or declare a baseline", expanded=not baselines):
        st.caption(
            "A LogSense baseline is an immutable, evidence-bound descriptive "
            "reference — it is not the HAIEC governing baseline. Calibration "
            "data may inform selection; it never silently becomes policy."
        )
        mode = st.radio(
            "Baseline source",
            [
                "Derive from a calibration / known-good run",
                "Declare a fixed reference value",
            ],
            key="c9_base_mode",
        )
        c1, c2 = st.columns(2)
        new_base_id = c1.text_input("Baseline ID", key="c9_base_id")
        basis = c2.selectbox("Basis", BASELINE_BASES, key="c9_base_basis")
        if mode == "Derive from a calibration / known-good run":
            runs = [str(r["runId"]) for r in svc.list_competition_runs(case_id)]
            src_run = st.selectbox("Source run", runs, key="c9_base_run")
            if st.button("Create baseline from run", key="c9_base_create"):
                try:
                    baseline = svc.create_control9_baseline_from_run(
                        case_id=case_id,
                        source_run_id=src_run,
                        profile_id=str(profile["profileId"]),
                        profile_version=int(profile["profileVersion"]),
                        baseline_id=new_base_id.strip(),
                        basis=basis,
                    )
                except _C9_ERRORS as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Saved `{baseline['baselineRef']}`")
                    st.rerun()
        else:
            fixed_value = st.number_input(
                "Baseline reference value", value=0.0, key="c9_base_value", format="%.6g"
            )
            if st.button("Save fixed baseline", key="c9_base_save"):
                try:
                    baseline = svc.save_control9_baseline(
                        case_id=case_id,
                        baseline={
                            "baselineId": new_base_id.strip(),
                            "baselineVersion": 1,
                            "label": new_base_id.strip(),
                            "basis": basis,
                            "baselineMode": "FIXED_REFERENCE_VALUE",
                            "metricId": profile["metricId"],
                            "unit": profile["unit"],
                            "direction": profile["direction"],
                            "aggregation": profile["aggregation"],
                            "governedScope": profile.get("governedScope"),
                            "windowDefinition": profile.get("windowDefinition"),
                            "metricProfileRef": profile["profileRef"],
                            "metricProfileDigest": profile["profileDigest"],
                            "value": float(fixed_value),
                            "valueBasis": "EXPLICIT_DECLARED",
                            "createdAt": _utc_now(),
                            "limitations": [
                                "LOGSENSE_DESCRIPTIVE_BASELINE_NE_HAIEC_GOVERNING_BASELINE"
                            ],
                        },
                    )
                except _C9_ERRORS as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Saved `{baseline['baselineRef']}`")
                    st.rerun()
    if baseline is None:
        st.info("No baseline selected — drift needs a declared evidence basis.")
        return

    # ---- 5. Compatibility preflight ------------------------------------------
    st.markdown("**5 — Compatibility preflight**")
    try:
        preview = svc.control9_compatibility_preview(
            case_id=case_id,
            run_id=run_id,
            profile_id=str(profile["profileId"]),
            profile_version=int(profile["profileVersion"]),
            baseline_id=str(baseline["baselineId"]),
            baseline_version=int(baseline["baselineVersion"]),
        )
    except _C9_ERRORS as exc:
        st.error(str(exc))
        preview = None
    if preview:
        _render_compatibility(preview)
        st.caption(
            f"Baseline `{preview['baselineRef']}` vs live profile `{preview['metricProfileRef']}`"
        )

    # ---- 6. Measure -----------------------------------------------------------
    st.markdown("**6 — Measure**")
    if st.button("Measure Drift", type="primary", key="c9_measure"):
        try:
            output = svc.run_control9_measurement(
                case_id=case_id,
                run_id=run_id,
                profile_id=str(profile["profileId"]),
                profile_version=int(profile["profileVersion"]),
                baseline_id=str(baseline["baselineId"]),
                baseline_version=int(baseline["baselineVersion"]),
            )
        except _C9_ERRORS as exc:
            st.error(str(exc))
        else:
            st.session_state["c9_last_measurement"] = output["measurement"]
            st.rerun()

    measurement = svc.load_control9_measurement(case_id, run_id)
    if measurement is None:
        st.info("No Control 9 measurement yet for this run.")
        return
    if measurement.get("activeSnapshotRef") != snapshot.get("snapshotId"):
        st.warning(
            "This measurement was produced against a prior analysis snapshot — "
            "it is preserved history, not current truth. Measure again."
        )
    _render_measurement(measurement)

    st.markdown("**HAIEC handoff**")
    st.caption(HAIEC_EVENT_FOOTNOTE)
    if measurement.get("measurementState") == "MEASURED":
        st.markdown("**MEASUREMENT READY**")
        refs = measurement.get("references") or {}
        st.caption(
            "Governance refs: "
            + ", ".join(f"{k}={v}" for k, v in refs.items())
            if refs
            else "No governance refs attached — HAIEC binds the governing "
            "baseline version, drift threshold and violating-window allowance."
        )
        st.info(
            "Export the Competition Evidence Bundle and run the AIA-ARC-006 "
            "Control Test in HAIEC. LogSense never emits the verdict."
        )
    else:
        blockers = measurement.get("limitations") or []
        st.warning(
            "Handoff not ready — measurement is "
            f"`{measurement.get('measurementState')}`. "
            + (", ".join(str(b) for b in blockers[:4]) if blockers else "")
        )
    bundle = svc.load_competition_bundle(case_id, run_id)
    if bundle and bundle.get("measurementType") == CONTROL9_CODE:
        st.download_button(
            "Download Competition Evidence Bundle",
            data=(json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            file_name=f"{case_id}-{run_id}-competition-evidence-bundle.json",
            mime="application/json",
            key="c9_dl_bundle",
        )
    st.markdown("**What this measures**")
    st.caption(
        "Each comparable window reports baseline, live, absolute delta and "
        "relative degradation under the profile's explicit direction. A missing "
        "window is never zero drift; incompatible semantics never produce an "
        "authoritative comparison; a zero baseline keeps the absolute delta "
        "but leaves the relative term undefined. LogSense measures; HAIEC "
        "evaluates the frozen policy."
    )
