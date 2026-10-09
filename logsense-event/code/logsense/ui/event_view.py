"""Event-teammate UI renderers for Competition Mode.

Orientation, discovery workspace, feasibility, readiness, gaps, judge pack
and AI guide panels — all reading deterministic service projections or the
structured guidance owner (``competition.guidance``). Nothing here issues a
verdict; HAIEC owns the Control Test.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import streamlit as st

from logsense.competition import event_operator
from logsense.competition.guidance import (
    ADAPTER_DECISION_GATE,
    AI_GUIDE_BANNER,
    C16_RUNTIME_BONUS,
    CALIBRATION_GUIDANCE,
    CAPABILITY_LADDER,
    CONCEPT_VOCABULARY,
    ENFORCEMENT_POINT_NOTE,
    EVENT_MISSION,
    EVIDENCE_HUNTING,
    EVIDENCE_IDENTITY,
    FILE_FORMAT_GUIDANCE,
    FIRST_HOUR_ARTIFACTS,
    FIRST_HOUR_SEQUENCE,
    FREEZE_GATE,
    HUMAN_LOOP,
    JUDGE_FLOW,
    JUDGE_REHEARSAL,
    JUDGING_AXES,
    LAB_SHAPE,
    OPERATOR_FALLBACK,
    ORGANIZER_ARCHITECTURE,
    ORGANIZER_SIX_STEPS,
    PLANE_READINESS,
    QUERY_ROUTING,
    QUICK_ACTIONS,
    RUN_ROLE_COPY,
    SAME_POLICY_COPY,
    SKEPTICAL_STRANGER_CHECK,
    SOURCE_CONTINUITY,
    SOURCE_INTEL,
    TELEMETRY_READINESS,
    THREE_LAYERS,
    THRESHOLD_DOC_GUIDANCE,
    capability_truth,
)
from logsense.presentation.workbench import action_rows
from logsense.ui import shared
from logsense.user_config import provider_key_source, resolve_ai_provider

_STATE_LABELS = {
    "READY": "READY",
    "READY_WITH_LIMITATIONS": "READY WITH LIMITATIONS",
    "NOT_READY": "NOT READY",
    "MEASURED": "MEASURED",
    "PARTIAL": "PARTIAL",
    "NOT_MEASURED": "NOT MEASURED",
    "SUPPLIED_EXTERNALLY": "SUPPLIED (external)",
    "TEMPLATE_AVAILABLE": "TEMPLATE AVAILABLE",
    "UNKNOWN": "UNKNOWN",
}


def _state_text(state: Any) -> str:
    return _STATE_LABELS.get(str(state), str(state or "—"))


def _yes_no(entry: Mapping[str, Any] | None, key: str) -> str:
    if not entry or key not in entry:
        return "—"
    return "yes" if entry.get(key) else "no"


# --------------------------------------------------------------------------
# Capability truth + orientation
# --------------------------------------------------------------------------


def render_capability_truth(command_center: Mapping[str, Any] | None) -> None:
    """C7/C9/C16 capability line — LogSense measurement vs HAIEC Control Test
    vs event-assessed status. The three columns are never merged."""
    truth = (command_center or {}).get("capabilityTruth") or capability_truth()
    rows = []
    for spec in truth["controls"]:
        event = spec.get("eventAssessed") or "NOT_YET"
        rows.append(
            {
                "Control": f"C{spec['controlNumber']} — {spec['controlCode']}",
                "LogSense measurement": spec["logsenseMeasurement"],
                "HAIEC Control Test": spec["haiecControlTest"],
                "Event assessed": event + ("*" if event == "NOT_YET" else ""),
            }
        )
    st.table(rows)
    st.caption(truth["footnote"])
    st.caption(truth["hardBoundary"])
    with st.expander("Concept vocabulary — what the columns mean", expanded=False):
        for key in ("technicalCapability", "eventStatus", "governingRule", "runtimeVsScored"):
            st.write(f"• {CONCEPT_VOCABULARY[key]}")


def render_event_orientation() -> None:
    """Mission, expected lab shape, three-layer model, organizer flow, axes."""
    with st.expander("Event orientation — what this competition is", expanded=False):
        st.markdown(f"**{EVENT_MISSION['headline']}**")
        st.write(EVENT_MISSION["mission"])
        st.markdown("**Expected lab shape**")
        for zone in LAB_SHAPE["zones"]:
            st.write(f"• {zone['zone']}" + (": " + ", ".join(zone["components"]) if zone["components"] else ""))
        st.write("• " + LAB_SHAPE["shared"])
        st.caption("Supporting: " + ", ".join(LAB_SHAPE["supporting"]))
        st.caption("*" + LAB_SHAPE["caveat"] + "*")
        st.markdown("**Three layers**")
        for layer in THREE_LAYERS:
            st.write(f"• **{layer['layer']}** — {', '.join(layer['contains'])}. *{layer['question']}*")
        st.markdown("**Organizer architecture principle**")
        st.code(ORGANIZER_ARCHITECTURE["flow"], language=None)
        st.caption(
            "Transports: "
            + "; ".join(f"`{t['name']}` {t['meaning']}" for t in ORGANIZER_ARCHITECTURE["transports"])
        )
        for habit in ORGANIZER_ARCHITECTURE["habits"]:
            st.write(f"- {habit}")
    with st.expander("Judging — the three axes", expanded=False):
        a1 = JUDGING_AXES["axis1"]
        st.markdown(f"**Axis 1 — {a1['name']}**")
        st.caption(a1["point"])
        with st.expander("What 'complete' requires"):
            for item in a1["completionChecklist"]:
                st.write(f"- {item}")
        a2 = JUDGING_AXES["axis2"]
        st.markdown(f"**Axis 2 — {a2['name']}**")
        for dim in a2["dimensions"]:
            st.write(f"- **{dim['name']}** — {dim['point']}")
        st.caption(a2["note"])
        a3 = JUDGING_AXES["axis3"]
        st.markdown(f"**Axis 3 — {a3['name']}**")
        st.caption("→ ".join(a3["paths"]))
        st.caption("Guardrail: " + a3["guardrail"])
    with st.expander("Organizer six-step mission", expanded=False):
        for step in ORGANIZER_SIX_STEPS:
            st.write(f"{step['step']}. {step['stepText']} — *{step['owner']}*")


# --------------------------------------------------------------------------
# Discovery workspace
# --------------------------------------------------------------------------


def render_first_hour(case_id: str) -> None:
    """Compact first-hour dashboard — source acquisition status at a glance.

    Everything is derived deterministically from committed evidence and
    declared runs; nothing is generated by an LLM and nothing is promoted
    past its evidence state.
    """
    svc = shared.service()
    try:
        dashboard = svc.first_hour_dashboard(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return

    sources = dashboard["sources"]
    run_id_state = dashboard["runIdentity"]["state"]
    run_start = dashboard["runStart"]
    controls = dashboard["controls"]
    eps = dashboard["enforcementPoints"]
    clock = dashboard.get("clockIntegrity") or {}

    with st.expander("First-hour sequence — CONNECT → RUN IDENTITY → CONTROL FACTS → QUALIFY", expanded=False):
        for block in FIRST_HOUR_SEQUENCE:
            st.markdown(f"**{block['window']} — {block['phase']}**")
            for item in block.get("identify") or ():
                st.write(f"- {item}")
            for code, fields in (block.get("perControl") or {}).items():
                st.write(f"- {code}: {', '.join(fields)}")
            st.caption(block["capture"])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sources", f"{sources['receivingData']}/{sources['total']} receiving")
    c2.metric("Run identity", run_id_state)
    c3.metric("Run start", run_start["state"].replace("_", " "))
    c4.metric("Enforcement points", f"{eps['observed']} observed / {eps['declared']} declared")
    c5.metric(
        "Controls",
        " / ".join(
            f"{name} {(controls.get(name) or {}).get('state', 'BLOCKED')}"
            for name in ("C7", "C9", "C16")
        ),
    )

    if run_start["state"] != "ESTABLISHED":
        st.warning(
            "Run start is "
            + run_start["state"].replace("_", " ").lower()
            + " — HAIEC cannot prove a frozen policy preceded the assessed run "
            "until an explicit run-start signal is qualified."
            + (
                " Candidate sources: "
                + ", ".join(run_start["candidateSources"])
                if run_start.get("candidateSources")
                else ""
            )
        )
    if clock.get("state") == "NOT_ESTABLISHED":
        st.warning(
            "TIME / CLOCK INTEGRITY not established — cross-system timing "
            "comparisons are not authoritative merely because timestamps "
            "parse. Record per source: " + "; ".join(clock.get("capturePerSource") or ())
            + ". Check across: " + ", ".join(clock.get("systemsToCheck") or ())
        )
    for action in dashboard["nextActions"]:
        st.write(f"**{action['priority']}** — {action['action']}")

    registry = dashboard.get("sourceRegistry") or {}
    matrix = dashboard.get("capabilityMatrix") or {}
    with st.expander(
        f"Source Intake Registry — {sources['ready']} ready / "
        f"{sources['limited']} limited / {sources['blocked']} blocked",
        expanded=False,
    ):
        rows = list(registry.get("sources") or ())
        if rows:
            st.dataframe(
                [
                    {
                        "source": r["displayName"],
                        "status": r["status"],
                        "records": r["recordsObserved"],
                        "qualified": r["qualifiedRecords"],
                        "unmapped": r["unmappedRecords"],
                        "runStart": r["runStartCapability"],
                        "controls": ", ".join(r["controlsSupported"]) or "—",
                        "next": r["nextAction"],
                    }
                    for r in rows
                ],
                use_container_width=True,
            )
        else:
            st.info("No committed sources yet — capture one sample per source first.")
        if matrix.get("rows"):
            st.caption(
                "Capability matrix — OBSERVED < MAPPED < QUALIFIED. A promising "
                "field name earns ONSITE_VERIFY at most; only run-bound "
                "qualified evidence earns QUALIFIED."
            )
            st.dataframe(matrix["rows"], use_container_width=True)

    ep_discovery = dashboard.get("enforcementPointDiscovery") or {}
    ep_points = list(ep_discovery.get("points") or ())
    if ep_points:
        try:
            declared_eps = {
                str(ep.get("point")): ep
                for ep in (svc.discovery_workspace(case_id).get("enforcementPoints") or ())
            }
        except Exception:  # noqa: BLE001 — declared attributes are optional detail
            declared_eps = {}
        with st.expander(f"Enforcement-point readiness — {len(ep_points)} candidate(s)", expanded=False):
            st.warning(ENFORCEMENT_POINT_NOTE)
            st.dataframe(
                [
                    {
                        "point": p["enforcementPointRef"],
                        "observed/declared": p["state"],
                        "zones seen": ", ".join(p.get("zonesSeen") or ()) or "—",
                        "passes through": (declared_eps.get(p["enforcementPointRef"]) or {}).get("passesThrough") or "—",
                        "can observe": _yes_no(declared_eps.get(p["enforcementPointRef"]), "canObserve"),
                        "can refuse": _yes_no(declared_eps.get(p["enforcementPointRef"]), "canRefuse"),
                        "candidate controls": ", ".join(p.get("controlsPotentiallySupported") or ()) or "—",
                        "telemetry": (declared_eps.get(p["enforcementPointRef"]) or {}).get("telemetryEmitted") or "—",
                        "decisions seen": ", ".join(p.get("decisionValuesSeen") or ()) or "—",
                        "evidence basis": ", ".join(p.get("evidenceRefs") or ()) or p.get("basis") or "—",
                    }
                    for p in ep_points
                ],
                use_container_width=True,
            )
            st.caption(
                (ep_discovery.get("note") or "")
                + " Nothing reaches QUALIFIED from this projection — verify "
                "each point against the real lab."
            )

    feasibility = dashboard.get("acquisitionFeasibility") or {}
    missing_rows = [
        {"control": name, "missing": ", ".join((ctrl or {}).get("missingFacts") or ())}
        for name, ctrl in (feasibility.get("controls") or {}).items()
        if (ctrl or {}).get("missingFacts")
    ]
    if missing_rows:
        st.caption("Missing facts: " + " | ".join(
            f"{r['control']}: {r['missing']}" for r in missing_rows
        ))


def render_discovery(case_id: str) -> None:
    """The five first-hour discovery artifacts."""
    render_first_hour(case_id)
    svc = shared.service()
    try:
        workspace = svc.discovery_workspace(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return

    st.caption(
        "Five artifacts an experienced teammate builds in the first hour. "
        "LogSense fills what it can deterministically; the rest is yours."
    )

    # A — Source Inventory (auto)
    spec = FIRST_HOUR_ARTIFACTS["sourceInventory"]
    with st.expander(f"A. {spec['name']} — {len(workspace['sourceInventory'])} source(s)", expanded=True):
        if workspace["sourceInventory"]:
            st.dataframe(
                workspace["sourceInventory"],
                use_container_width=True,
                column_config={
                    "sourceName": "Source",
                    "sha256": None,
                    "knownGaps": None,
                },
            )
        else:
            st.info("No committed sources yet — capture one representative sample per source first.")
        st.caption("Fields to keep per source: " + ", ".join(spec["fields"]))

    # B — Run-ID Map (auto once analysis exists)
    with st.expander("B. Run-ID Map — observed identifier kinds", expanded=False):
        idmap = workspace["runIdMap"]
        if idmap["kinds"]:
            st.dataframe(idmap["kinds"], use_container_width=True)
        else:
            st.info("Run deterministic analysis to populate — or record IDs you observe in the lab below.")
        st.caption("Track: " + ", ".join(FIRST_HOUR_ARTIFACTS["runIdMap"]["fields"]))

    # C — Enforcement-Point Map (operator-entered)
    eps = list(workspace["enforcementPoints"])
    with st.expander(f"C. Enforcement-Point Map — {len(eps)} point(s)", expanded=False):
        st.caption("Fields: " + ", ".join(FIRST_HOUR_ARTIFACTS["enforcementPointMap"]["fields"]))
        for ep in eps:
            st.write(
                f"• **{ep['point']}** — observes: {'yes' if ep['canObserve'] else 'no'}, "
                f"refuses: {'yes' if ep['canRefuse'] else 'no'}"
                + (f" · passes: {ep['passesThrough']}" if ep.get("passesThrough") else "")
                + (f" · controls: {', '.join(ep['candidateControls'])}" if ep.get("candidateControls") else "")
            )
        st.markdown("**Add a point**")
        ep_name = st.text_input("Point", placeholder="Gateway A / Shared Model Gateway / …", key="ep_name")
        ep_passes = st.text_input("What passes through it", key="ep_passes")
        ep_controls = st.multiselect(
            "Candidate controls",
            ["AIA-LOG-001", "AIA-ARC-006", "ACN-COST-001"],
            key="ep_controls",
        )
        epc1, epc2 = st.columns(2)
        ep_observe = epc1.checkbox("Can observe", key="ep_observe")
        ep_refuse = epc2.checkbox("Can refuse", key="ep_refuse")
        ep_telemetry = st.text_input("Telemetry emitted", key="ep_telemetry")
        if st.button("Save enforcement point", key="ep_save"):
            try:
                svc.update_discovery_workspace(
                    case_id=case_id,
                    enforcement_points=[
                        *eps,
                        {
                            "point": ep_name,
                            "passesThrough": ep_passes,
                            "candidateControls": ep_controls,
                            "canObserve": ep_observe,
                            "canRefuse": ep_refuse,
                            "telemetryEmitted": ep_telemetry,
                        },
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                st.error(shared.intake_error_text(exc))
            else:
                st.rerun()

    # D — Metric Inventory
    with st.expander("D. Metric Inventory — what each control needs", expanded=False):
        for code, fields in FIRST_HOUR_ARTIFACTS["metricInventory"]["perControl"].items():
            hints = workspace["metricInventoryHints"].get(code) or []
            st.markdown(f"**{code}** — needed: {', '.join(fields)}")
            if hints:
                st.caption("Sources with matching evidence hints: " + ", ".join(str(h.get("path")) for h in hints))

    # E — Scenario / Run Map
    with st.expander("E. Scenario / Run Map — reuse the Run Manager", expanded=False):
        rows = workspace["scenarioRunMap"]
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No confirmed runs yet — runs appear on the Runs step after analysis.")
        st.caption(
            FIRST_HOUR_ARTIFACTS["scenarioRunMap"]["note"]
            + " Track: "
            + ", ".join(FIRST_HOUR_ARTIFACTS["scenarioRunMap"]["fields"])
        )

    notes = st.text_area(
        "Discovery notes (operator)",
        value=workspace.get("notes") or "",
        key="discovery_notes",
        height=80,
    )
    if st.button("Save notes", key="discovery_notes_save"):
        svc.update_discovery_workspace(case_id=case_id, notes=notes)
        st.success("Notes saved.")


# --------------------------------------------------------------------------
# Evidence guidance + source intelligence
# --------------------------------------------------------------------------


def render_evidence_guidance() -> None:
    """Evidence hunting list, file formats, adapter decision gate."""
    with st.expander("Evidence hunting guide — what to actively request", expanded=False):
        for category, items in EVIDENCE_HUNTING.items():
            st.write(f"**{category}:** " + ", ".join(items))
    with st.expander("File formats — what works best", expanded=False):
        st.caption("Supported: " + ", ".join(FILE_FORMAT_GUIDANCE["supported"]))
        for kind, pref in FILE_FORMAT_GUIDANCE["preferred"].items():
            st.write(f"- **{kind}:** {pref}")
        st.info(FILE_FORMAT_GUIDANCE["workflow"])
    with st.expander(ADAPTER_DECISION_GATE["title"], expanded=False):
        for i, step in enumerate(ADAPTER_DECISION_GATE["steps"], start=1):
            st.write(f"{i}. {step}")
        st.caption(
            "Possible event-triggered adapters (not built speculatively): "
            + ", ".join(ADAPTER_DECISION_GATE["possibleFutureAdapters"])
        )
        st.caption(ADAPTER_DECISION_GATE["rule"])
    with st.expander(TELEMETRY_READINESS["title"], expanded=False):
        st.dataframe(
            [
                {"Source": r[0], "Intake capability": r[1], "Live binding": r[2]}
                for r in TELEMETRY_READINESS["rows"]
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(TELEMETRY_READINESS["note"])


def render_source_intel() -> None:
    """Per-source 'what can it prove' guidance for Source Setup."""
    with st.expander("Source intelligence — what can each source prove?", expanded=False):
        st.caption(SOURCE_INTEL["intro"])
        for row in SOURCE_INTEL["examples"]:
            st.write(
                f"• **{row['source']}** — useful for: {row['usefulFor']}. "
                f"Not enough alone for: {row['notEnoughFor']}."
            )
        st.caption("Timestamp proximity never establishes run membership.")


# --------------------------------------------------------------------------
# Feasibility chooser + freeze gate + calibration
# --------------------------------------------------------------------------


def render_handoff_preview(case_id: str) -> None:
    """Per-control HAIEC handoff preview — what a Competition Evidence Bundle
    carries right now and the deterministic next step."""
    svc = shared.service()
    try:
        preview = svc.handoff_preview(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return
    with st.expander("HAIEC handoff preview — Competition Evidence Bundle", expanded=False):
        st.caption(
            f"Run: {preview.get('runId') or '—'} · run start: "
            f"{(preview.get('runActivityState') or 'NOT_ESTABLISHED')} · "
            f"runStartedAt: {preview.get('runStartedAt') or '—'}"
        )
        st.caption(preview.get("note") or "")
        for name, row in (preview.get("controls") or {}).items():
            p = row.get("preview") or {}
            st.markdown(
                f"**{name} — {row['controlCode']}** · acquisition: "
                f"{row['acquisitionState']} · measurement: {p.get('measurementState')}"
            )
            st.write(
                f"bundleId: `{p.get('bundleId') or '—'}` · "
                f"evidenceSet: `{p.get('evidenceSetRef') or '—'}` · "
                f"evidenceRefs: {p.get('evidenceRefs')}"
            )
            if p.get("limitations"):
                st.caption("Limitations: " + ", ".join(p["limitations"]))
            st.info(row.get("action") or "")
        st.caption(
            "Judge path: Reusable Control → Frozen Event Governing Instance "
            "→ Run → Measurement → HAIEC Control Test → Result → Evidence → "
            "Gap / Retest."
        )
    with st.expander(SKEPTICAL_STRANGER_CHECK["title"], expanded=False):
        st.write(SKEPTICAL_STRANGER_CHECK["intro"])
        for item in SKEPTICAL_STRANGER_CHECK["items"]:
            st.write(f"◻ {item}")
        st.caption(SKEPTICAL_STRANGER_CHECK["note"])
    st.caption(OPERATOR_FALLBACK)


def render_query_routing() -> None:
    """ASK TWO DIFFERENT QUESTIONS — forensic exploration vs HAIEC verdict."""
    q = QUERY_ROUTING
    with st.expander(q["title"], expanded=True):
        left, right = st.columns(2)
        wh = q["whatHappened"]
        left.markdown(f"**{wh['question']}**")
        left.caption(f"Use: `{wh['use']}`")
        left.write("Returns:")
        for item in wh["returns"]:
            left.write(f"- {item}")
        left.error(wh["verdict"])
        dh = q["didItHold"]
        right.markdown(f"**{dh['question']}**")
        right.caption(f"Use: `{dh['use']}`")
        right.write("Returns:")
        for item in dh["returns"]:
            right.write(f"- {item}")
        right.caption("via the HAIEC handoff preview / Competition Evidence Bundle")
        st.page_link("pages/timeline_actions.py", label="Open Timeline / Forensic Window")


def render_event_capabilities(case_id: str) -> None:
    """Capability ladder + bonus-readiness projections over existing data.

    Every status is evidence-backed; rehearsal measurements demonstrate the
    technical path, never an event assessment or a HAIEC verdict."""
    svc = shared.service()
    try:
        dashboard = svc.first_hour_dashboard(case_id)
        active = svc.active_run(case_id)
        run_id = str(active.get("runId") or "") or None
        c7 = svc.load_control7_measurement(case_id, run_id) if run_id else None
        c9 = svc.load_control9_measurement(case_id, run_id) if run_id else None
        c16 = svc.load_control16_measurement(case_id, run_id) if run_id else None
        resolution = svc.resolve_case_run(case_id=case_id, run_id=run_id) if run_id else None
        workspace = svc.discovery_workspace(case_id)
        runs = svc.list_competition_runs(case_id)
        handoff = svc.handoff_preview(case_id)
        results = svc.load_case_results(case_id) or {}
        overview = svc.source_overview(case_id) if results else {}
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return

    analysis = results.get("analysis") or {}
    a_rows = action_rows(analysis) if analysis else []
    ep_points = list((dashboard.get("enforcementPointDiscovery") or {}).get("points") or ())
    gap_entries = list(workspace.get("operatorGapEntries") or ())
    human_rows = event_operator.human_loop_rows(
        c9=c9,
        operator_gap_entries=gap_entries,
        items=HUMAN_LOOP["items"],
    )
    human_recorded = sum(1 for r in human_rows if r["state"] == "EVIDENCE_RECORDED")
    bundles_present = sum(
        1
        for row in (handoff.get("controls") or {}).values()
        if (row.get("preview") or {}).get("bundleId")
        and str((row.get("preview") or {}).get("measurementState")) == "MEASURED"
    )

    layers = event_operator.capability_ladder(
        c7=c7,
        c9=c9,
        c16=c16,
        bundles_present=bundles_present,
        ep_points=ep_points,
        runs=runs,
        action_rows=a_rows,
        analysis_present=bool(analysis),
        human_loop_recorded=human_recorded,
    )

    with st.expander(CAPABILITY_LADDER["title"], expanded=False):
        st.caption(CAPABILITY_LADDER["note"])
        st.dataframe(
            [
                {"layer": layer["layer"], "capability": layer["name"], "status": layer["state"], "basis": layer["basis"]}
                for layer in layers
            ],
            use_container_width=True,
        )

    with st.expander(PLANE_READINESS["title"], expanded=False):
        st.caption(PLANE_READINESS["note"])
        plane_rows = event_operator.plane_readiness_rows(a_rows)
        st.caption(f"{plane_rows['actionsAssessed']} action(s) carry five-plane coverage.")
        st.dataframe(
            [
                {
                    "plane": spec["plane"],
                    "potential evidence": ", ".join(spec["potentialEvidence"]),
                    "PRESENT": counts["counts"]["PRESENT"],
                    "PARTIAL": counts["counts"]["PARTIAL"],
                    "UNKNOWN": counts["counts"]["UNKNOWN"] + counts["counts"]["ABSENT"],
                }
                for spec, counts in zip(PLANE_READINESS["planes"], plane_rows["planes"], strict=True)
            ],
            use_container_width=True,
        )

    with st.expander(HUMAN_LOOP["title"], expanded=False):
        st.dataframe(
            [
                {"check": r["item"], "status": r["state"], "evidence": ", ".join(r["evidenceRefs"]) or "—", "basis": r["basis"]}
                for r in human_rows
            ],
            use_container_width=True,
        )
        st.warning(f"{HUMAN_LOOP['silenceRule']} — {HUMAN_LOOP['note']}")

    with st.expander(C16_RUNTIME_BONUS["title"], expanded=False):
        posture = event_operator.c16_runtime_posture(c16)
        for case_spec in C16_RUNTIME_BONUS["cases"]:
            st.markdown(f"**{case_spec['name']}**")
            st.caption(case_spec["meaning"])
        if posture["measured"]:
            st.caption(
                f"This run: {posture['executedCalls']} provider-executed call(s), "
                f"{posture['preventedAttempts']} denied-before-execution record(s), "
                f"actual tokens: {posture['actualTokens'] if posture['actualTokens'] is not None else '—'}"
            )
            if posture["preventedRefs"]:
                st.caption("Prevented-attempt evidence: " + ", ".join(posture["preventedRefs"]))
        else:
            st.caption("No C16 measurement for the active run yet.")
        st.warning(C16_RUNTIME_BONUS["neverClaim"])

    with st.expander(EVIDENCE_IDENTITY["title"], expanded=False):
        st.caption(EVIDENCE_IDENTITY["mirroring"])
        st.caption(EVIDENCE_IDENTITY["retryRule"])
        rows = event_operator.evidence_identity_rows(
            resolution=resolution,
            run_activity=(dashboard.get("runStart") or {}),
            clock=dashboard.get("clockIntegrity"),
            c16=c16,
            source_rows=list((dashboard.get("sourceRegistry") or {}).get("sources") or ()),
        )
        st.dataframe(
            [
                {
                    "check": r["item"],
                    "status": r["state"],
                    "value": "—" if r["value"] in (None, "") else ", ".join(str(v) for v in (r["value"] if isinstance(r["value"], list) else [r["value"]])),
                    "basis": "—" if r["basis"] in (None, "") else ", ".join(str(v) for v in (r["basis"] if isinstance(r["basis"], list) else [r["basis"]])),
                }
                for r in rows
            ],
            use_container_width=True,
        )
        st.caption(EVIDENCE_IDENTITY["note"])

    with st.expander(SOURCE_CONTINUITY["title"], expanded=False):
        continuity = event_operator.deployment_continuity_rows(
            list(overview.get("sources") or ())
        )
        st.write(f"**{SOURCE_CONTINUITY['githubPath']}**")
        st.write(f"**{SOURCE_CONTINUITY['localPath']}**")
        if continuity["codeCapable"] == "NOT ESTABLISHED":
            st.warning(
                f"{SOURCE_CONTINUITY['noSource']} — {SOURCE_CONTINUITY['fallback']}"
            )
        else:
            st.caption(
                f"{continuity['sourceLikeArtifacts']} source-like artifact(s) "
                "present — binding to deployed identity still requires evidence."
            )
        st.caption(SOURCE_CONTINUITY["neverImply"])


def render_feasibility(case_id: str) -> None:
    """Deterministic READY / READY_WITH_LIMITATIONS / NOT_READY per control."""
    try:
        feasibility = shared.service().control_feasibility_state(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return
    st.markdown("#### Control feasibility — deterministic")
    st.caption(
        "Computed from real case state — not AI judgment. "
        "READY_WITH_LIMITATIONS means measurable with visible constraints; "
        "NOT_READY lists what is missing."
    )
    rows = [
        {
            "Control": code,
            "Feasibility": _state_text(row["state"]),
            "Missing": ", ".join(row["missing"]) or "—",
            "Detail": row["detail"],
        }
        for code, row in feasibility["controls"].items()
    ]
    st.dataframe(rows, use_container_width=True)


def render_freeze_gate(external_refs: Mapping[str, Any] | None) -> None:
    """HAIEC freeze checklist — the last item stays UNKNOWN unless supplied."""
    with st.expander(FREEZE_GATE["title"], expanded=False):
        st.info(FREEZE_GATE["copy"])
        for item in FREEZE_GATE["checklist"][:-1]:
            st.write(f"◻ {item}")
        supplied = bool(external_refs and any(external_refs.values()))
        st.write(
            "◻ HAIEC governing policy frozen — "
            + ("SUPPLIED (external ref attached)" if supplied else "UNKNOWN — external")
        )
        st.caption(FREEZE_GATE["externalItem"])


def render_calibration_guidance() -> None:
    with st.expander("Calibration — learn, don't lock", expanded=False):
        st.markdown(f"**{CALIBRATION_GUIDANCE['headline']}**")
        for code, uses in CALIBRATION_GUIDANCE["uses"].items():
            st.write(f"• **{code}:** {', '.join(uses)}")
        st.caption(CALIBRATION_GUIDANCE["rule"])
        st.caption(RUN_ROLE_COPY)
        st.caption(SAME_POLICY_COPY)


# --------------------------------------------------------------------------
# Gaps decision surface
# --------------------------------------------------------------------------


def render_gap_register(case_id: str) -> None:
    """Operator decision surface over the deterministic gap register."""
    try:
        register = shared.service().competition_gap_register(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return
    gaps = register["gaps"]
    st.markdown(f"#### Gap Register — {len(gaps)} open item(s)")
    st.caption(
        "What is blocking us, which control it affects, what it prevents us "
        "from claiming, and what to do next. Underlying forensic state is "
        "never hidden."
    )
    if gaps:
        st.dataframe(
            [
                {
                    "Gap": g["gapId"],
                    "Category": g["category"],
                    "Control": g.get("control") or "—",
                    "Blocking": g["gap"],
                    "Why it matters": g["whyItMatters"],
                    "Consequence": g["consequence"],
                    "Still supportable": g["whatRemainsSupportable"],
                    "Next action": g["nextAction"],
                }
                for g in gaps
            ],
            use_container_width=True,
        )
    else:
        st.success("No open gaps recorded for this case.")
    st.download_button(
        "Download Gap Register (JSON)",
        data=json.dumps(register, indent=2, sort_keys=True).encode("utf-8"),
        file_name=f"{case_id}-gap-register.json",
        mime="application/json",
    )


# --------------------------------------------------------------------------
# Judgment-Day readiness + pack
# --------------------------------------------------------------------------


def render_judgment_day(case_id: str) -> None:
    """Six-artifact readiness, run register, and the one-click pack."""
    svc = shared.service()
    try:
        readiness = svc.judgment_day_state(case_id)
        register = svc.competition_run_register(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
        return

    st.markdown("#### Six Judgment-Day artifacts")
    if readiness["allArtifactsPresent"]:
        st.success(readiness["statement"])
    else:
        st.warning(readiness["statement"])
    st.dataframe(
        [
            {
                "Artifact": a["name"],
                "Owner": a["owner"],
                "State": _state_text(a["state"]),
                "Detail": a["detail"],
            }
            for a in readiness["sixArtifacts"]
        ],
        use_container_width=True,
    )
    with st.expander("Axis 1 — controls complete (requires HAIEC too)", expanded=False):
        st.caption(JUDGING_AXES["axis1"]["point"])
        st.dataframe(
            [
                {
                    "Control": row["controlCode"],
                    "LogSense measurement": row["logSenseMeasurement"],
                    "Measured": row["measurementState"] or "—",
                    "HAIEC Control Test": row["haiecControlTest"],
                    "Policy frozen": row["policyFrozen"],
                    "Named PASS run": "yes" if row["namedPassRun"] else "no",
                    "Named breach run": "yes" if row["namedBreachRun"] else "no",
                }
                for row in readiness["axis1Controls"]
            ],
            use_container_width=True,
        )
        st.caption(capability_truth()["footnote"])

    activity = readiness.get("runActivity") or {}
    proof = readiness.get("preRunTemporalProof") or {}
    start_state = str(activity.get("startState") or "NOT_ESTABLISHED")
    st.markdown("#### Run activity")
    st.caption(
        "Qualified run-activity provenance — whether explicit evidence "
        "established when the actual assessed run began. Earliest observed "
        "activity is not automatically the assessed run start."
    )
    cols = st.columns(4)
    cols[0].metric("Run start", start_state.replace("_", " "))
    cols[1].metric("Run started", activity.get("runStartedAt") or "—")
    cols[2].metric(
        "Earliest observed", activity.get("earliestObservedActivityAt") or "—"
    )
    cols[3].metric("Pre-run proof", _state_text(proof.get("state") or "NOT_PROVEN"))
    if start_state == "ESTABLISHED":
        st.success(proof.get("actionable") or "Ready for pre-run temporal-policy proof.")
    else:
        st.warning(
            proof.get("actionable")
            or "Find and qualify the lab's actual run-start signal before "
            "assessed runs."
        )
    if activity.get("startBasis") or activity.get("startEvidenceRefs"):
        st.caption(
            "Basis: "
            + ", ".join(activity.get("startBasis") or ())
            + " · Evidence: "
            + ", ".join(activity.get("startEvidenceRefs") or ())
        )
    if activity.get("excludedStartCandidateRefs"):
        st.caption(
            "Excluded start candidates (not qualified/bound): "
            + ", ".join(activity["excludedStartCandidateRefs"])
        )
    st.caption(
        "HAIEC decides whether the frozen governing policy preceded the "
        "assessed run — LogSense only describes qualified provenance."
    )

    with st.expander("Run register", expanded=False):
        st.caption(register["note"])
        if register["runs"]:
            st.dataframe(register["runs"], use_container_width=True)
        st.download_button(
            "Download Run Register (JSON)",
            data=json.dumps(register, indent=2, sort_keys=True).encode("utf-8"),
            file_name=f"{case_id}-run-register.json",
            mime="application/json",
        )

    st.markdown("#### Judge rehearsal")
    st.caption(f"Target: {JUDGE_REHEARSAL['target']}")
    st.caption(" → ".join(f"{t} {what}" for t, what in JUDGE_REHEARSAL["segments"]))
    st.caption("Acceptance: " + "; ".join(JUDGE_REHEARSAL["acceptance"]))
    st.caption(JUDGE_FLOW)

    st.markdown("#### Portable evidence pack")
    st.caption(
        "Opens on a machine where LogSense is not installed — readable HTML "
        "plus canonical JSON, run/gap registers, limitations and any "
        "externally supplied HAIEC references."
    )
    try:
        pack, _manifest = svc.judge_evidence_pack(case_id)
    except Exception as exc:  # noqa: BLE001
        st.error(shared.intake_error_text(exc))
    else:
        st.download_button(
            "Download TMF-JUDGE-EVIDENCE-PACK.zip",
            data=pack,
            file_name="TMF-JUDGE-EVIDENCE-PACK.zip",
            mime="application/zip",
            type="primary",
        )


def render_threshold_doc_guidance() -> None:
    with st.expander(THRESHOLD_DOC_GUIDANCE["title"], expanded=False):
        st.caption("Per control: " + ", ".join(THRESHOLD_DOC_GUIDANCE["perControl"]))
        for code, fields in THRESHOLD_DOC_GUIDANCE["controlSpecific"].items():
            st.write(f"• **{code}:** {', '.join(fields)}")
        st.caption(THRESHOLD_DOC_GUIDANCE["note"])


# --------------------------------------------------------------------------
# AI competition guide
# --------------------------------------------------------------------------


def render_ai_guide(case_id: str) -> None:
    """Competition Guide mode — quick actions + provider-off fallback.

    Without an AI provider the same questions are answered deterministically
    from the guidance owner + readiness projection — the mode never fails.
    """
    st.caption(f"**{AI_GUIDE_BANNER}** — advisory only; deterministic outputs own truth.")
    labels = {key: row["label"] for key, row in QUICK_ACTIONS.items()}
    pick = st.selectbox(
        "Quick action",
        list(labels),
        format_func=lambda k: labels[k],
        key="ai_guide_action",
    )
    topic = QUICK_ACTIONS[pick]["topic"]

    def _deterministic_answer() -> None:
        try:
            readiness = shared.service().event_readiness_state(case_id)
        except Exception as exc:  # noqa: BLE001
            st.error(shared.intake_error_text(exc))
            return
        _render_deterministic_guide(topic, readiness)

    if not provider_key_source(resolve_ai_provider()):
        st.info(
            "No AI provider configured — answering deterministically from the "
            "event guide instead."
        )
        _deterministic_answer()
        return
    if st.button("Ask the competition guide", key="ai_guide_ask"):
        _deterministic_answer()
        _, analysis, report = shared.ensure_results()
        question = (
            "[COMPETITION GUIDE MODE — advisory, not forensic evidence] "
            + labels[pick]
            + ". Use get_event_readiness / get_event_guidance plus the "
            "deterministic measurements; never claim a verdict."
        )
        try:
            with st.spinner("Consulting deterministic state…"):
                view = shared.ask_question(
                    question,
                    analysis,
                    report or {},
                    competition=shared.competition_payload(case_id),
                )
        except Exception as exc:  # noqa: BLE001
            st.error(shared.provider_unavailable_message(exc))
        else:
            st.markdown(view["answer"])
            if view.get("citations"):
                st.caption(f"Evidence citations: {len(view['citations'])}")


def _render_deterministic_guide(topic: str, readiness: Mapping[str, Any]) -> None:
    """Local answers when no AI provider exists (or before calling it)."""
    feasibility = (readiness.get("feasibility") or {}).get("controls") or {}
    if topic == "feasibility":
        st.markdown("**Control readiness (deterministic):**")
        for code, row in feasibility.items():
            st.write(f"- **{code}** — {_state_text(row['state'])}. {row['detail']}")
    elif topic == "artifacts":
        for artifact in readiness.get("readiness", {}).get("sixArtifacts") or ():
            st.write(f"- **{artifact['name']}** ({artifact['owner']}): {_state_text(artifact['state'])} — {artifact['detail']}")
    elif topic == "rehearsal":
        for t, what in JUDGE_REHEARSAL["segments"]:
            st.write(f"- **{t}** {what}")
        st.caption("Acceptance: " + "; ".join(JUDGE_REHEARSAL["acceptance"]))
    elif topic == "bonus":
        st.write("Bonus order: " + " → ".join(JUDGING_AXES["axis3"]["paths"]))
        st.caption("Guardrail: " + JUDGING_AXES["axis3"]["guardrail"])
    elif topic == "evidence_hunting":
        for category, items in EVIDENCE_HUNTING.items():
            st.write(f"**{category}:** " + ", ".join(items))
    elif topic == "handoff":
        st.write(JUDGE_FLOW)
        st.caption(capability_truth()["footnote"])
    elif topic == "blockers":
        missing = [
            f"**{code}**: {', '.join(row['missing'])}" for code, row in feasibility.items() if row["missing"]
        ]
        if missing:
            for line in missing:
                st.write("- " + line)
        else:
            st.write("No deterministic blockers — see the Gap Register for limitations.")
    elif topic == "gaps":
        st.write("Check the Gap Register on the Gaps step — every gap lists its consequence and next action.")
    else:
        st.write(
            "Workflow: UNDERSTAND → DISCOVER → INGEST → MAP → RECONSTRUCT → "
            "CHOOSE CONTROL → CALIBRATE → FREEZE IN HAIEC → CAPTURE ASSESSED "
            "RUNS → MEASURE → HAND OFF → INVESTIGATE/RETEST → PACKAGE → REHEARSE."
        )
        st.caption(
            "Next action is always deterministic — see the Event Command Center."
        )
