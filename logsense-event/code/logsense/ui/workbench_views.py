"""Read-only render functions for canonical workbench views.

Moved verbatim from the original single-file workbench so the page-level
navigation can compose them. These views never mutate canonical state and
never infer beyond the deterministic projections they display.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from logsense.presentation.forensic_window import forensic_window_rows
from logsense.presentation.workbench import (
    action_rows,
    evidence_inventory_rows,
    proof_frontier_rows,
    report_overview,
    semantic_drilldown,
    status_view,
    timeline_rows,
)
from logsense.workspace.cases import evidence_inventory, list_manifests


def render_status(value: Any) -> None:
    view = status_view(value)
    st.caption(f"{view['label']} · {view['semanticClass']}")


def render_case(workspace_root: Path, case_id: str) -> None:
    st.subheader("Case")
    st.write("Workspace:", f"`{workspace_root}`")
    st.write("Case ID:", case_id or "Not selected")
    results = None
    if case_id:
        from logsense.ui import shared

        results = shared.case_results(case_id)
    analysis = (results or {}).get("analysis") or {}
    report = (results or {}).get("report") or {}
    st.write(
        "Analysis run:",
        report.get("analysisRunId") or analysis.get("analysisRunId") or "Not analyzed yet",
    )
    st.write(
        "Evidence set:",
        report.get("evidenceSetId") or analysis.get("evidenceSetId") or "Not analyzed yet",
    )
    if case_id:
        persisted = list_manifests(workspace_root, case_id)
        st.metric("Committed manifests", len(persisted))
        if persisted:
            st.dataframe(list(persisted), use_container_width=True)


def render_manifest(workspace_root: Path, case_id: str) -> None:
    st.subheader("Manifest")
    rows = st.session_state.get("manifest_rows", [])
    if rows:
        st.markdown("#### Current preview")
        st.write(f"Manifest: `{st.session_state.get('manifest_id', '')}`")
        st.write(f"Dataset digest: `{st.session_state.get('dataset_digest', '')}`")
        st.dataframe(rows, use_container_width=True)
    if not case_id:
        if not rows:
            st.info("Create/open a case and gather evidence first.")
        return
    persisted = list_manifests(workspace_root, case_id)
    st.markdown("#### Committed manifests")
    (
        st.dataframe(list(persisted), use_container_width=True)
        if persisted
        else st.info("No manifest has been committed to this case.")
    )


def render_evidence_inventory(
    workspace_root: Path, case_id: str, analysis: dict[str, Any] | None
) -> None:
    st.subheader("Evidence inventory")
    if case_id:
        persisted = evidence_inventory(workspace_root, case_id)
        st.markdown("#### Persisted immutable artifacts")
        (
            st.dataframe(list(persisted), use_container_width=True)
            if persisted
            else st.info("No evidence committed to this case.")
        )
    if analysis:
        rows = evidence_inventory_rows(analysis)
        st.markdown("#### Qualified source projections")
        (
            st.dataframe(rows, use_container_width=True)
            if rows
            else st.info("No source descriptors available.")
        )
    elif not case_id:
        st.info("Open a case or run deterministic analysis.")


def render_explore(analysis: dict[str, Any] | None) -> None:
    st.subheader("Explore / profile / mapping review")
    if not analysis:
        st.info("Run deterministic analysis first.")
        return
    view = semantic_drilldown(analysis)
    st.markdown("#### External producers")
    st.write(view["externalProducers"] or ["Not assessed"])
    st.markdown("#### Artifact profiles")
    (
        st.dataframe(view["artifacts"], use_container_width=True)
        if view["artifacts"]
        else st.info("No artifact profiles available.")
    )
    st.markdown("#### Mapping proposals")
    st.caption("Read-only review. Proposal != approved canonical mapping.")
    (
        st.dataframe(view["mappingProposals"], use_container_width=True)
        if view["mappingProposals"]
        else st.info("No mapping proposals emitted.")
    )
    st.markdown("#### Source qualification")
    (
        st.dataframe(view["qualifications"], use_container_width=True)
        if view["qualifications"]
        else st.info("No claim-scoped qualifications emitted.")
    )
    left, right = st.columns(2)
    with left:
        st.markdown("#### Upstream Rule")
        st.json(view["upstreamRule"])
    with right:
        st.markdown("#### Definition Delta")
        st.json(view["definitionDelta"])
    st.markdown("#### Provenance path")
    (
        st.dataframe(view["provenancePath"], use_container_width=True)
        if view["provenancePath"]
        else st.info("No provenance path available.")
    )
    if view["limitations"]:
        st.markdown("#### Limitations")
        st.write(view["limitations"])


def render_timeline(analysis: dict[str, Any] | None) -> None:
    st.subheader("Timeline")
    if not analysis:
        st.info("Run deterministic analysis first.")
        return
    rows = timeline_rows(analysis)
    st.caption(
        "Displayed order comes from canonical timeline records; the UI does not infer causality."
    )
    (
        st.dataframe(rows, use_container_width=True)
        if rows
        else st.info("No canonical timeline records available.")
    )


def render_forensic_window(analysis: dict[str, Any] | None) -> None:
    """FORENSIC TIME WINDOW — deterministic from/to filtering over canonical
    event time. Evidence exploration only; never a control verdict."""
    if not analysis:
        return
    rows = timeline_rows(analysis)
    if not rows:
        return

    with st.expander("FORENSIC TIME WINDOW — filter canonical events by event time", expanded=False):
        st.warning("TIME-WINDOW FORENSIC VIEW — NO CONTROL VERDICT")
        st.caption(
            "Displayed sequence reflects canonical timeline ordering. "
            "Sequence does not establish causality."
        )
        fc1, fc2 = st.columns(2)
        from_raw = fc1.text_input(
            "From timestamp (RFC3339, optional)",
            key="fw_from",
            placeholder="2026-10-01T14:00:00Z",
        )
        to_raw = fc2.text_input(
            "To timestamp (RFC3339, optional)",
            key="fw_to",
            placeholder="2026-10-01T15:00:00Z",
        )
        fc3, fc4 = st.columns(2)
        identity_raw = fc3.text_input(
            "Run / correlation identity contains (optional)",
            key="fw_identity",
            placeholder="run or event ref substring",
        )
        sources = sorted({s for row in rows for s in (row.get("sourceRefs") or ())})
        source_pick = fc4.selectbox(
            "Source (optional)",
            ["(all)"] + sources,
            key="fw_source",
        )
        try:
            window = forensic_window_rows(
                rows,
                from_time=from_raw or None,
                to_time=to_raw or None,
                identity=identity_raw or None,
                source=None if source_pick == "(all)" else source_pick,
            )
        except ValueError as exc:
            st.error(str(exc))
            return

        st.caption(
            f"Window: {window['from'] or '—'} → {window['to'] or '—'} · "
            f"{window['matchedCount']} matching event(s) · "
            f"{window['excludedUnknownTime']} "
            + window["copy"]["unknownTime"]
        )
        if not window["crossClockEstablished"]:
            st.error(
                "CROSS-CLOCK COMPARABILITY NOT ESTABLISHED — matched records "
                "span "
                + (", ".join(window["clockDomains"]) or "undeclared")
                + " clock domain(s). No skew correction is applied."
            )
        if not window["rows"]:
            st.info("No canonical events match this window.")
            return
        st.dataframe(
            [
                {
                    "event": r.get("semanticClass") or "—",
                    "eventTime": r.get("normalizedTime") or r.get("eventTime") or "—",
                    "source": ", ".join(r.get("sourceRefs") or ()) or "—",
                    "evidence": ", ".join(r.get("evidenceRefs") or ()) or "—",
                    "clockDomain": r.get("clockDomainRef") or "—",
                    "run/correlation": r.get("actionGroupRef") or "—",
                    "orderingBasis": r.get("orderingBasis") or "—",
                    "timeQuality": r.get("timeQuality") or "—",
                }
                for r in window["rows"]
            ],
            use_container_width=True,
        )


def render_actions(analysis: dict[str, Any] | None) -> None:
    st.subheader("Actions and assurance planes")
    if not analysis:
        st.info("Run deterministic analysis first.")
        return
    rows = action_rows(analysis)
    if not rows:
        st.info("No action groups available.")
        return
    for row in rows:
        with st.expander(row["actionGroupId"] or "Action"):
            st.write("Canonical operation:", row["canonicalOperation"] or "Unknown")
            render_status(row["identityState"]["state"])
            st.write("Event refs:", row["eventRefs"])
            st.write("Lifecycle:", row["lifecycle"] or "Not assessed")
            st.write("Five-plane coverage:", row["fivePlaneCoverage"] or "Not assessed")
            if row["limitations"]:
                st.write("Limitations:", row["limitations"])


def render_compare(report: dict[str, Any] | None) -> None:
    st.subheader("Baseline / compare")
    if not report:
        st.info("Run deterministic analysis first.")
        return
    case = report.get("forensicCase") or {}
    states = case.get("states") or []
    transitions = case.get("transitions") or []
    (
        st.dataframe(states, use_container_width=True)
        if states
        else st.info("No multi-state forensic case supplied.")
    )
    if transitions:
        st.markdown("#### Adjacent transitions")
        st.dataframe(transitions, use_container_width=True)
    first = case.get("firstQualifiedDivergence") or case.get("firstDeterministicDivergence")
    if first:
        st.markdown("#### Earliest qualified divergence")
        st.json(first)
        st.caption("First qualified divergence is not a root-cause conclusion.")


def render_findings(report: dict[str, Any] | None) -> None:
    st.subheader("Findings and bounded conclusions")
    if not report:
        st.info("Run deterministic analysis first.")
        return
    overview = report_overview(report)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Established")
        for item in overview["whatEstablished"] or ["Nothing established at this scope."]:
            st.write(f"- {item}")
    with right:
        st.markdown("#### Not established")
        for item in overview["whatNotEstablished"] or ["No explicit non-claims supplied."]:
            st.write(f"- {item}")
    st.markdown("#### Deterministic investigation stories")
    for story in report.get("investigationStories") or []:
        with st.expander(str(story.get("title") or story.get("family") or "Story")):
            st.write("Established:", story.get("whatEstablished") or [])
            st.write("Why it matters:", story.get("whyItMatters") or "")
            st.write("Evidence refs:", story.get("evidenceRefs") or [])
            st.write("Not claimed:", story.get("notClaimed") or [])
            st.write("Limitations:", story.get("limitations") or [])


def render_proof(report: dict[str, Any] | None) -> None:
    st.subheader("Evidence frontier / verify")
    if not report:
        st.info("Run deterministic analysis first.")
        return
    rows = proof_frontier_rows(report)
    if not rows:
        st.success("No open frontier items are present in this report.")
        return
    for row in rows:
        with st.expander(
            str(row.get("missingFact") or row.get("frontierId") or "Open proof boundary")
        ):
            render_status(row["state"]["state"])
            st.write("Why needed:", row.get("whyNeeded") or "")
            st.write("Verification requirement:", row.get("verificationRequirement") or "")
            st.write("Current evidence:", row.get("currentEvidenceRefs") or [])
            st.write("Proposed test:", row.get("proposedTestRef") or "Not defined")
            st.caption("Evidence frontier item != finding.")


def render_investigation_summary(analysis: dict[str, Any], report: dict[str, Any]) -> None:
    """Plain-language deterministic summary shared by the Summary page and the
    Competition stepper. Every statement is a canonical projection."""
    from logsense.ui import shared

    overview = report_overview(report)
    stories = list(report.get("investigationStories") or analysis.get("investigationStories") or ())

    a, b, c, d = st.columns(4)
    a.metric("Artifacts analyzed", len(analysis.get("artifactResults") or ()))
    b.metric("Canonical events", len(analysis.get("canonicalEvents") or ()))
    c.metric("Stories", overview["storyCount"])
    d.metric("Open proof boundaries", overview["openFrontierCount"])
    st.caption(f"Run `{overview['analysisRunId'] or 'n/a'}`")

    st.subheader("What happened?")
    if stories:
        for story in stories:
            title = str(story.get("title") or story.get("family") or "Material story")
            with st.expander(title, expanded=len(stories) == 1):
                established = story.get("whatEstablished") or []
                if established:
                    for item in established:
                        st.write(f"- {item}")
                if story.get("whyItMatters"):
                    st.caption(f"Why it matters: {story['whyItMatters']}")
                if story.get("notClaimed"):
                    st.caption(f"Not claimed: {', '.join(str(x) for x in story['notClaimed'])}")
    else:
        st.info("The deterministic engine produced no narrative stories for this evidence.")

    est_col, not_col = st.columns(2)
    with est_col:
        st.subheader("What LogSense established")
        st.caption(shared.GLOSSARY["Established"])
        for item in overview["whatEstablished"] or ["Nothing established at this scope."]:
            st.write(f"- {item}")
    with not_col:
        st.subheader("What LogSense did NOT establish")
        st.caption(shared.GLOSSARY["Not assessed"])
        for item in overview["whatNotEstablished"] or ["No explicit non-claims supplied."]:
            st.write(f"- {item}")

    st.divider()
    st.subheader("First qualified divergence")
    st.caption(shared.GLOSSARY["First divergence"])
    case_view = report.get("forensicCase") or {}
    first = case_view.get("firstQualifiedDivergence") or case_view.get(
        "firstDeterministicDivergence"
    )
    if first:
        st.json(first)
    else:
        st.info(
            "No qualified divergence projected. Divergence requires a comparable "
            "baseline/candidate pair or multi-state forensic case — see Advanced views."
        )

    st.subheader("Important actions reconstructed")
    rows = action_rows(analysis)
    if rows:
        st.dataframe(
            [
                {
                    "action": row["actionGroupId"],
                    "operation": row["canonicalOperation"],
                    "identity": row["identityState"]["label"],
                    "events": len(row["eventRefs"]),
                }
                for row in rows
            ],
            use_container_width=True,
        )
    else:
        st.info("No canonical action groups reconstructed from this evidence.")

    st.subheader("Evidence health")
    sources = list(analysis.get("sourceDescriptors") or ())
    contradictions = list(
        report.get("evidenceContradictions") or analysis.get("contradictions") or ()
    )
    frontiers = list(report.get("evidenceFrontier") or analysis.get("evidenceFrontier") or ())
    ungrouped = list(analysis.get("ungroupedEventRefs") or ())
    health = st.columns(4)
    health[0].metric("Sources ingested", len(analysis.get("artifactResults") or ()))
    health[1].metric("Qualified sources", len(sources))
    health[2].metric("Contradictions", len(contradictions))
    health[3].metric("Open gaps / frontiers", len(frontiers))
    st.caption(shared.GLOSSARY["Contradiction"])
    if ungrouped:
        st.caption(
            f"{len(ungrouped)} event ref(s) could not be joined into an action — unresolved correlation."
        )

    st.subheader("What should I do next?")
    verification_actions = list(report.get("verificationActions") or ())
    if frontiers:
        st.caption(shared.GLOSSARY["Evidence frontier"])
        for item in frontiers[:5]:
            st.write(f"- **{item.get('missingFact') or item.get('frontierId')}**")
            if item.get("whyNeeded"):
                st.caption(f"  Why: {item['whyNeeded']}")
    elif verification_actions:
        for action in verification_actions[:5]:
            st.write(f"- {action}")
    else:
        st.success("No open evidence frontiers. Review the report or export evidence.")


def render_report(report: dict[str, Any] | None) -> None:
    st.subheader("Deterministic forensic report")
    if not report:
        st.info("Run deterministic analysis first.")
        return
    overview = report_overview(report)
    a, b, c = st.columns(3)
    a.metric("Stories", overview["storyCount"])
    b.metric("Open proof boundaries", overview["openFrontierCount"])
    c.metric("Evidence contradictions", overview["contradictionCount"])
    st.write(
        "Report digest:",
        f"`{overview['reportDigest']}`" if overview["reportDigest"] else "Not available",
    )
    if overview["limitations"]:
        st.write("Limitations:", overview["limitations"])
    st.download_button(
        "Export deterministic report JSON",
        data=json.dumps(report, indent=2, sort_keys=True),
        file_name="logsense-forensic-report.json",
        mime="application/json",
    )
