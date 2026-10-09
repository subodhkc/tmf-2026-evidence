"""TM Forum Competition — the guided event workflow.

A visible stepper walks the operator through the full event arc: understand →
discover → ingest → map → reconstruct → choose control → calibrate → freeze
in HAIEC → capture assessed runs → measure → hand off → investigate/retest →
package → rehearse. Every step explains what to do, what LogSense produced,
and what remains missing.
"""

from __future__ import annotations

import streamlit as st

from logsense.competition.controls import control_cards
from logsense.competition.guidance import RUN_ROLE_COPY, capability_truth
from logsense.pipeline.intake import preview_evidence
from logsense.presentation.workbench import manifest_rows
from logsense.ui import (
    control7_view,
    control9_view,
    control16_view,
    event_view,
    shared,
    source_view,
    workbench_views,
)
from logsense.user_config import resolve_ai_provider
from logsense.workspace.cases import evidence_inventory, load_case

STEPS = [
    "Setup",
    "Case",
    "Discover",
    "Evidence",
    "Source Setup",
    "Analyze",
    "Runs",
    "Investigation Summary",
    "Ask LogSense",
    "Competition Controls",
    "Gaps / Verification",
    "Export",
]

RUN_ROLES = ("CALIBRATION", "ASSESSED_PASS", "ASSESSED_BREACH", "RETEST", "OTHER")
RUN_ROLE_HELP = (
    "CALIBRATION — warm-up or tooling check, never scored. "
    "ASSESSED_PASS / ASSESSED_BREACH — the team's named intended PASS / BREACH "
    "demonstration run (not a verdict). RETEST — re-run after a fix. "
    "OTHER — anything else. Roles describe the workflow slot; HAIEC owns the "
    "control result."
)

R5_REMAINING = (
    "HAIEC Event Freeze / assessed-run binding (event side — real event evidence only).",
)

st.title("TM Forum Competition")
st.caption(
    "The lab supplies the AI system; your team builds controls around it and "
    "proves — independently — whether they held. LogSense preserves evidence, "
    "reconstructs runs and measures; HAIEC owns the verdict."
)
st.caption(
    "UNDERSTAND → DISCOVER → INGEST → MAP → RECONSTRUCT → CHOOSE CONTROL → "
    "CALIBRATE → FREEZE IN HAIEC → CAPTURE ASSESSED RUNS → MEASURE → "
    "HAND OFF → INVESTIGATE/RETEST → PACKAGE → REHEARSE"
)

shared.render_case_sidebar()

step = max(0, min(int(st.session_state.get("competition_step", 0)), len(STEPS) - 1))
if current_case := shared.active_case_id():
    shared.note_competition_state(current_case, step)

st.progress(
    (step + 1) / len(STEPS),
    text=f"Step {step + 1} of {len(STEPS)} — {STEPS[step]}",
)

workspace_root = shared.workspace_root()
current_case = shared.active_case_id()
case = load_case(workspace_root, current_case) if current_case else None
artifact_count = len(evidence_inventory(workspace_root, case.case_id)) if case else 0
results = shared.case_results(case.case_id) if case else None

# ---- Event Command Center ---------------------------------------------------
# Deterministic projection of real application state — never an LLM judgment.
command_center = None
if case:
    try:
        command_center = shared.service().command_center_state(case.case_id)
    except Exception:  # noqa: BLE001 — degrade to the plain header, never crash
        command_center = None

with st.expander("Event Command Center", expanded=True):
    active_run = (command_center or {}).get("activeRun") or {}
    snapshot_info = (command_center or {}).get("snapshot") or {}
    health_info = (command_center or {}).get("collectionHealth") or {}
    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric("Competition Case", (case.title or case.case_id) if case else "none")
    if active_run.get("runId"):
        role = active_run.get("runRole") or "—"
        cc2.metric("Active Run", f"{active_run['runId']} — {role}")
    else:
        cc2.metric("Active Run", "Not selected")
    cc3.metric("AI", shared.ai_status_line())
    cc4.metric("Sources", artifact_count)
    if case and command_center:
        c5, c6, c7c, c8 = st.columns(4)
        readiness_label = {
            "READY": "Ready",
            "READY_WITH_LIMITATIONS": "Ready with limitations",
            "REVIEW_RECOMMENDED": "Review recommended",
            "NO_EVIDENCE": "No evidence",
        }.get(str(command_center["readinessState"]), "—")
        c5.metric("Source readiness", readiness_label)
        analysis_label = {
            "CURRENT": "Current",
            "STALE": "May be stale",
            "NOT_RUN": "Needs run",
        }.get(str(command_center["analysis"]["state"]), "—")
        c6.metric("Analysis", analysis_label)
        c7c.metric(
            "Control 7",
            {
                "MEASURED": "Measured",
                "NO_MEASUREMENT_YET": "Not measured",
                "NO_RUN_SELECTED": "No run selected",
            }.get(str(command_center["control7"]["state"]), "—"),
        )
        c16_info = command_center.get("control16") or {}
        c7c.caption(
            "C16: "
            + {
                "MEASURED": "Measured",
                "PARTIAL": "Partial",
                "NOT_MEASURED": "Not measured",
            }.get(str(c16_info.get("state")), "Not ready")
        )
        gaps = command_center["openGaps"]
        c8.metric("Open evidence gaps", gaps if gaps is not None else "—")
        d1, d2, d3 = st.columns(3)
        d1.metric(
            "Collection Health",
            {
                "REPORTED": "Reported",
                "ANALYSIS_REQUIRED": "Needs analysis",
                "NO_EVIDENCE": "No evidence",
            }.get(str(health_info.get("state")), "—"),
        )
        d2.metric(
            "Analysis Snapshot",
            (snapshot_info.get("label") or "None")
            + (" (stale)" if str(snapshot_info.get("state", "")).startswith("STALE") else ""),
        )
        d3.metric(
            "Coverage",
            str(health_info.get("coverageState") or "—").replace("_", " ").title(),
        )
        c9_info = command_center.get("control9") or {}
        st.caption(
            "C9: "
            + {
                "MEASURED": "Measured",
                "PARTIAL": "Partial",
                "NOT_MEASURED": "Not measured",
                "READY_TO_MEASURE": "Ready to measure",
            }.get(str(c9_info.get("state")), "Not ready")
        )
        feasibility = command_center.get("controlFeasibility") or {}
        if feasibility:
            short_code = {
                "AIA-LOG-001": "C7",
                "AIA-ARC-006": "C9",
                "ACN-COST-001": "C16",
            }
            st.caption(
                "Feasibility — "
                + " · ".join(
                    f"{short_code.get(code, code)}: "
                    f"{str(row.get('state')).replace('_', ' ')}"
                    for code, row in feasibility.items()
                )
            )
        st.info(f"**Next action:** {command_center['nextAction']['message']}")
    elif case:
        st.caption("Command-center projection unavailable — continuing with basic status.")

with st.expander("Capability truth — LogSense vs HAIEC", expanded=False):
    event_view.render_capability_truth(command_center)

event_view.render_event_orientation()

with st.expander("HAIEC companion — who owns what", expanded=False):
    st.caption(
        "LogSense reconstructs and measures the evidence. HAIEC owns: live "
        "telemetry readiness where configured, governing thresholds/baselines, "
        "frozen control versions, the final Control Test verdict, and optional "
        "runtime enforcement."
    )
    if command_center and command_center["control7"]["state"] == "MEASURED":
        st.caption(
            "**Next step in HAIEC** — take the Competition Evidence Bundle, the "
            "run ID, the Control 7 measurement (evidence refs + "
            "measurementState), then run the frozen Control 7 Control Test in "
            "HAIEC."
        )

st.divider()


def _nav() -> None:
    back_col, next_col = st.columns(2)
    with back_col:
        if st.button("Back", disabled=step == 0, key="comp_back"):
            st.session_state["competition_step"] = step - 1
            st.rerun()
    with next_col:
        if st.button("Next", disabled=step == len(STEPS) - 1, key="comp_next"):
            st.session_state["competition_step"] = step + 1
            st.rerun()


if step == 0:  # Setup
    st.subheader("Setup — AI investigator and workspace")
    st.write(
        "**What to do:** confirm an AI provider is configured and note your "
        "workspace. **What LogSense does:** keeps evidence local and the "
        "deterministic engine in charge; AI investigates after analysis only."
    )
    st.info(f"Workspace: `{workspace_root}` — Local workspace — Recommended for competition")
    status = shared.ai_status_line()
    provider = resolve_ai_provider()
    if "configured" in status:
        st.success(f"AI investigator: {provider} — {status}")
    else:
        st.warning(
            "No AI provider configured. Deterministic analysis still works; "
            "OpenAI or Claude is recommended for the event to explain results."
        )
        if st.button("Configure a provider"):
            st.switch_page("pages/ask_logsense.py")
    st.caption(
        "Modal and local ML remain available under Advanced / Cloud Options — "
        "not required for the competition workflow."
    )
    st.write("**Next:** create or open your case.")
elif step == 1:  # Case
    st.subheader("Competition Case — the investigation workspace")
    st.write(
        "**What to do:** create a case for the competition workspace, or open an "
        "existing one. **Produced:** a workspace that holds committed evidence, "
        "manifests, and analysis outputs."
    )
    st.caption(
        "A case may contain evidence for calibration, assessed, breach or retest "
        "runs — you select the exact run on the Runs step when measuring a "
        "competition control."
    )
    if case:
        st.success(f"Active case: **{case.title or case.case_id}** (`{case.case_id}`)")
        st.caption(f"{artifact_count} committed artifact(s)")
    else:
        st.info("No case open.")
    if st.button("Open Case & Evidence"):
        st.switch_page("pages/case_evidence.py")
    st.write("**Missing / next:** add evidence once the case is open.")
elif step == 2:  # Discover
    st.subheader("Discover — the first-hour artifacts")
    st.write(
        "**What to do:** build the five artifacts an experienced teammate "
        "makes first — source inventory, run-ID map, enforcement-point map, "
        "metric inventory, and the scenario/run map. **What LogSense does:** "
        "fills what it can deterministically from committed evidence and "
        "confirmed runs; the rest is yours to record."
    )
    case_id = shared.ensure_case()
    event_view.render_discovery(case_id)
    st.write("**Next:** upload the evidence those sources produce.")
elif step == 3:  # Evidence
    st.subheader("Evidence — upload the run's artifacts")
    event_view.render_evidence_guidance()
    st.write(
        "**What to do:** upload the files the run produced (logs, telemetry, "
        "config, exports). **What LogSense does:** previews a manifest, then "
        "commits qualified evidence immutably into the case."
    )
    case_id = shared.ensure_case()
    uploads = st.file_uploader("Evidence files", accept_multiple_files=True, key="comp_upload")
    if uploads:
        tmp, paths = shared.temp_extracted_paths(uploads)
        try:
            manifest = preview_evidence(paths)
            st.dataframe(manifest_rows(manifest), use_container_width=True)
            st.caption("Manifest preview — committed only when you press Commit.")
            if st.button("Commit evidence to case", type="primary", key="comp_commit"):
                try:
                    payload = shared.commit_uploads_to_case(case_id, uploads)
                except Exception as exc:  # noqa: BLE001
                    st.error(shared.intake_error_text(exc))
                else:
                    st.success(f"Committed immutable evidence: `{payload['manifestId']}`")
                    st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(shared.intake_error_text(exc))
        finally:
            tmp.cleanup()
    if artifact_count:
        st.success(f"{artifact_count} artifact(s) committed to this case.")
    st.caption(
        "Want the full intake detail? Case & Evidence shows adapter, emitted "
        "records, and qualification status."
    )
    st.write("**Next:** check Source Setup before analysis.")
elif step == 4:  # Source Setup
    st.subheader("Source Setup — make every source count")
    event_view.render_source_intel()
    st.write(
        "**What to do:** check that each committed source parsed and mapped "
        "cleanly. **What LogSense does:** profiles each source's schema and "
        "proposes deterministic mappings for unfamiliar formats — nothing is "
        "promoted until you approve it."
    )
    case_id = shared.ensure_case()
    if not artifact_count:
        st.warning("Commit at least one evidence artifact first.")
    else:
        source_view.render_source_setup(case_id, compact=True)
        st.divider()
        source_view.render_collection_health(case_id, compact=True)
        st.caption(
            "You can analyze now with current coverage, or approve proposed "
            "mappings to broaden deterministic coverage."
        )
        if st.button("Open Source Setup & Mapping", key="comp_srcmap_page"):
            st.switch_page("pages/source_mapping.py")
    st.write("**Next:** run deterministic analysis.")
elif step == 5:  # Analyze
    st.subheader("Analyze — deterministic truth")
    st.write(
        "**What to do:** run the canonical LogSense engine over the committed "
        "evidence. **Produced:** an immutable analysis snapshot — re-running "
        "after new evidence or mapping changes creates a new snapshot; the "
        "previous one stays preserved."
    )
    case_id = shared.ensure_case()
    if not artifact_count:
        st.warning("Commit at least one evidence artifact first.")
    else:
        snapshot_state = (command_center or {}).get("snapshot") or {}
        if results:
            st.success(
                "Active analysis snapshot — "
                f"`{(snapshot_state.get('label') or results['analysis'].get('analysisRunId'))}`."
            )
            if str(snapshot_state.get("state", "")).startswith("STALE"):
                st.warning(
                    "Your evidence or mapping changed after this analysis. Run "
                    "analysis again to create a new snapshot — the previous "
                    "snapshot remains preserved."
                )
        if st.button("Run deterministic analysis", type="primary"):
            with st.spinner("Analyzing committed evidence deterministically…"):
                try:
                    output = shared.run_case_analysis(case_id)
                except Exception as exc:  # noqa: BLE001
                    st.error(shared.intake_error_text(exc))
                else:
                    st.success(
                        "Analysis complete — a new immutable snapshot is now "
                        "active for this case."
                    )
                    st.caption(f"Run `{output['analysis'].get('analysisRunId')}`")
                    st.rerun()
        try:
            snapshots = shared.service().list_analysis_snapshots(case_id)
        except Exception:  # noqa: BLE001
            snapshots = []
        if snapshots:
            with st.expander(f"Analysis history ({len(snapshots)} snapshot(s))", expanded=False):
                st.caption(
                    "Each snapshot is immutable proof of one analysis run. "
                    "Making a snapshot active only repoints which one is "
                    "current — it never rewrites history."
                )
                for row in snapshots:
                    cols = st.columns([2, 2, 2, 3])
                    cols[0].write(
                        f"**{row.get('snapshotLabel')}**"
                        + (" — active" if row.get("active") else " — historical")
                    )
                    cols[1].write(
                        f"{row.get('eventCount')} events · {row.get('artifactCount')} artifacts"
                    )
                    cols[2].write(str(row.get("createdAt") or "")[:19])
                    if not row.get("active") and cols[3].button(
                        "Make active", key=f"snap_activate_{row['snapshotLabel']}"
                    ):
                        try:
                            shared.service().set_active_snapshot(
                                case_id=case_id, snapshot_id=str(row["snapshotId"])
                            )
                        except Exception as exc:  # noqa: BLE001
                            st.error(shared.intake_error_text(exc))
                        else:
                            st.success(f"Snapshot {row['snapshotLabel']} is now active.")
                            st.rerun()
    st.write("**Next:** review discovered runs and confirm one on the Runs step.")
elif step == 6:  # Runs
    st.subheader("Runs — confirm the execution you are investigating")
    st.caption(RUN_ROLE_COPY)
    st.write(
        "**What to do:** LogSense groups events that share explicit run, trace "
        "or call identifiers into candidate executions — never by timestamp "
        "proximity. Confirm the run you want, assign its role, and select it "
        "as active so measurement and handoff follow it."
    )
    case_id = shared.ensure_case()
    if not results:
        st.warning("Run deterministic analysis first — run discovery works on the analysis.")
    else:
        svc = shared.service()
        active = svc.active_run(case_id)
        confirmed = svc.list_competition_runs(case_id)
        st.markdown("**Active run**")
        if active.get("runId"):
            st.success(
                f"`{active['runId']}` — {active.get('runRole') or 'no role'} · "
                f"snapshot {active.get('snapshotRef') or '—'} · "
                f"{active.get('resolutionState') or 'unresolved'}"
            )
        else:
            st.info(
                "**Active Run — Not selected.** Recommended next action: review "
                "discovered runs below and confirm the execution you want to "
                "investigate."
            )
        if confirmed:
            st.markdown("**Confirmed runs**")
            for run in confirmed:
                cols = st.columns([3, 2, 2, 2, 2])
                cols[0].write(
                    f"**`{run['runId']}`**"
                    + (f" — {run.get('label')}" if run.get("label") != run["runId"] else "")
                )
                cols[1].write(run.get("runRole") or "—")
                cols[2].write(run.get("scenarioLabel") or "—")
                cols[3].write(
                    f"{run.get('resolutionState') or '—'} · "
                    f"{len(run.get('ambiguousEvidenceRefs') or ())} ambiguous / "
                    f"{len(run.get('unresolvedEvidenceRefs') or ())} unresolved"
                )
                if active.get("runId") != run["runId"] and cols[4].button(
                    "Make active", key=f"run_active_{run['runId']}"
                ):
                    svc.set_active_run(case_id=case_id, run_id=str(run["runId"]))
                    st.rerun()
        st.markdown("**Discovered candidates**")
        try:
            discovery = svc.discover_case_run_candidates(case_id)
        except Exception as exc:  # noqa: BLE001
            st.error(shared.intake_error_text(exc))
        else:
            candidates = discovery.get("candidates") or []
            if not candidates:
                st.caption(
                    "No candidate executions found — events carry no shared "
                    "explicit identifiers. Timestamp similarity is never used "
                    "to form a run."
                )
            for candidate in candidates:
                label = candidate["suggestedRunId"]
                basis_values = "; ".join(
                    f"{row['kind']} = {', '.join(row['values'][:3])}"
                    for row in candidate.get("identifierBasis") or ()[:4]
                )
                with st.container(border=True):
                    st.markdown(
                        f"**Possible run — `{label}`** "
                        f"({str(candidate.get('basis', '')).replace('_', ' ').title()})"
                    )
                    st.caption(f"Identifier basis: {basis_values}")
                    times = candidate.get("observedTime") or {}
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Events", candidate["eventCount"])
                    c2.metric("Qualified", candidate["qualifiedCount"])
                    c3.metric(
                        "Ambiguous / unresolved",
                        f"{candidate['ambiguousCount']} / {candidate['unresolvedCount']}",
                    )
                    c4.metric(
                        "Observed",
                        (
                            f"{str(times.get('first', ''))[11:19]} → {str(times.get('last', ''))[11:19]}"
                            if times.get("first")
                            else "—"
                        ),
                    )
                    if candidate.get("alreadyDeclared"):
                        st.caption("Already confirmed as a run.")
                    else:
                        role = st.selectbox(
                            "Run role",
                            RUN_ROLES,
                            key=f"cand_role_{label}",
                            help=RUN_ROLE_HELP,
                        )
                        scenario = st.text_input(
                            "Scenario label (optional, e.g. AL1)",
                            key=f"cand_scenario_{label}",
                        )
                        if st.button("Confirm this run", key=f"cand_confirm_{label}"):
                            try:
                                svc.confirm_competition_run(
                                    case_id=case_id,
                                    declaration=candidate["declaration"],
                                    run_role=role,
                                    scenario_label=scenario or None,
                                )
                                svc.set_active_run(case_id=case_id, run_id=label)
                            except Exception as exc:  # noqa: BLE001
                                st.error(shared.intake_error_text(exc))
                            else:
                                st.success(
                                    f"Run `{label}` confirmed as {role} and selected active."
                                )
                                st.rerun()
        if confirmed:
            choices = ["(none)"] + [str(r["runId"]) for r in confirmed]
            current = active.get("runId")
            pick = st.selectbox(
                "Active run selector",
                choices,
                index=choices.index(str(current)) if current in choices else 0,
                key="active_run_select",
            )
            if st.button("Apply active run", key="active_run_apply"):
                svc.set_active_run(case_id=case_id, run_id=None if pick == "(none)" else pick)
                st.rerun()
    st.write("**Next:** read the Investigation Summary for the active run.")
elif step == 7:  # Summary
    st.subheader("Investigation Summary")
    _, analysis, report = shared.ensure_results()
    workbench_views.render_investigation_summary(analysis, report or {})
    st.write("**Next:** ask AI to explain the findings.")
elif step == 8:  # Ask
    st.subheader("Ask LogSense — evidence investigator + competition guide")
    st.write(
        "**Evidence Investigator** answers questions grounded in the "
        "deterministic findings with citations. **Competition Guide** gives "
        "advisory event guidance — clearly labeled, never forensic truth. "
        "Both are optional: the product works fully without AI."
    )
    mode = st.radio(
        "Mode",
        ["Evidence Investigator", "Competition Guide"],
        horizontal=True,
        key="ask_mode",
        help="The guide advises on workflow/readiness — it is advisory and never establishes evidence.",
    )
    if mode == "Competition Guide":
        case_id = shared.active_case_id()
        if case_id:
            event_view.render_ai_guide(case_id)
        else:
            st.info("Open a case first — the guide reads deterministic case state.")
    else:
        _, analysis, report = shared.ensure_results()
        if "configured" not in shared.ai_status_line():
            st.warning("No AI provider configured.")
            if st.button("Configure provider"):
                st.switch_page("pages/ask_logsense.py")
        else:
            pick = st.selectbox("Suggested questions", shared.SUGGESTED_QUESTIONS, key="comp_suggest")
            question = st.text_area("Question", value=pick, height=68, key="comp_question")
            if st.button("Ask", type="primary", key="comp_ask"):
                try:
                    with st.spinner("Investigating deterministic findings…"):
                        view = shared.ask_question(
                            question,
                            analysis,
                            report or {},
                            competition=shared.competition_payload(),
                        )
                except Exception as exc:  # noqa: BLE001
                    st.error(shared.provider_unavailable_message(exc))
                else:
                    st.markdown(view["answer"])
                    citations = view.get("citations") or []
                    st.caption(f"Evidence citations: {len(citations)}")
            st.page_link("pages/ask_logsense.py", label="Open the full Ask LogSense")
elif step == 9:  # Controls
    st.subheader("Competition controls — 7, 9, 16")
    st.write(
        "All three controls are real deterministic measurements: declare the "
        "run, configure expected events for C7, bind a metric profile and "
        "baseline for C9, and reconcile canonical evidence. LogSense never "
        "fabricates a verdict; HAIEC applies the frozen thresholds."
    )
    for card in control_cards():
        with st.container(border=True):
            st.markdown(
                f"**Control {card['control_number']} — {card['control_code']} " f"{card['name']}**"
            )
            st.write(card["plain_question"])
            st.caption(
                f"LogSense measurement: {card.get('logsense_status', 'AVAILABLE')} · "
                f"HAIEC Control Test: {card.get('haiec_status', '—')}"
            )
            if card["cardNote"]:
                st.caption(f"*{card['cardNote']}*")
    st.caption(capability_truth()["footnote"])
    if case:
        event_view.render_query_routing()
        event_view.render_feasibility(case.case_id)
        event_view.render_handoff_preview(case.case_id)
        event_view.render_calibration_guidance()
        try:
            _jd = shared.service().judgment_day_state(case.case_id)
            _frozen = any(
                row.get("policyFrozen") == "SUPPLIED"
                for row in _jd.get("axis1Controls") or ()
            )
        except Exception:  # noqa: BLE001
            _frozen = False
        event_view.render_freeze_gate({"policy": "supplied"} if _frozen else {})
        event_view.render_threshold_doc_guidance()
        st.divider()
        control7_view.render_control7_panel(case.case_id)
        st.divider()
        control9_view.render_control9_panel(case.case_id)
        st.divider()
        control16_view.render_control16_panel(case.case_id)
        st.divider()
        event_view.render_event_capabilities(case.case_id)
    else:
        st.info("Open a case first — the control panels need committed evidence.")
    with st.expander("What lands in later builds (R5+)"):
        for item in R5_REMAINING:
            st.write(f"- {item}")
elif step == 10:  # Gaps
    st.subheader("Gaps / verification — what is still unproven")
    if case:
        event_view.render_gap_register(case.case_id)
        st.divider()
    _, analysis, report = shared.ensure_results()
    report = report or {}
    frontiers = report.get("evidenceFrontier") or analysis.get("evidenceFrontier") or []
    contradictions = report.get("evidenceContradictions") or analysis.get("contradictions") or []
    gc1, gc2 = st.columns(2)
    gc1.metric("Open frontiers", len(frontiers))
    gc2.metric("Contradictions", len(contradictions))
    st.caption(shared.GLOSSARY["Evidence frontier"])
    if frontiers:
        for item in frontiers[:10]:
            st.write(f"- **{item.get('missingFact') or item.get('frontierId')}**")
            if item.get("whyNeeded"):
                st.caption(f"  Why: {item['whyNeeded']}")
    else:
        st.success("No open evidence frontiers for this case.")
    st.page_link("pages/verify.py", label="Open the full verification loop")
elif step == 11:  # Export
    st.subheader("Export — take the evidence with you")
    _, _analysis, _report = shared.ensure_results()
    st.write(
        "**Produced:** analysis, report, manifest, and gaps as JSON — plus a "
        "single ZIP bundle ready to attach to a competition submission."
    )
    case_id = shared.active_case_id() or "case"
    st.download_button(
        "Download Case Evidence Bundle",
        data=shared.case_export_bundle(case_id),
        file_name=f"{case_id}-evidence-bundle.zip",
        mime="application/zip",
    )
    if shared.active_case_id():
        st.download_button(
            "Export checkpoint (resume identities only)",
            data=shared.checkpoint_export(case_id),
            file_name=f"{case_id}-checkpoint.json",
            mime="application/json",
            help="Case/snapshot/run identities and status for orientation and "
            "recovery — not a copy of the evidence.",
        )
        st.divider()
        event_view.render_judgment_day(case_id)
    st.page_link("pages/export.py", label="Open Export for individual files")
    st.success(
        "LogSense evidence phase complete — deterministic evidence exported, "
        "no AI claims included. HAIEC-side artifacts (frozen policy, Control "
        "Test results) remain external until supplied."
    )
    if command_center and command_center["control7"]["state"] == "MEASURED":
        st.info(
            "**HAIEC next step:** hand the Competition Evidence Bundle, run ID, "
            "and measurement refs to HAIEC and run the frozen Control Test "
            "there — LogSense never issues the verdict. "
            + capability_truth()["footnote"]
        )

st.divider()
_nav()
