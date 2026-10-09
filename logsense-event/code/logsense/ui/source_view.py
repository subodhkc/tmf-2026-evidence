"""Source Setup & Mapping — shared renderer for the event workflow.

Used by the standalone ``source_mapping`` page and the Competition stepper's
Source Setup step. Every control reads or writes through ``IntegrationService``
— the UI never recomputes mappings and never promotes anything itself.

Boundary statements preserved throughout:

- a mapping *proposal* is never an approved mapping;
- adapter qualification != evidence qualification != claim authority;
- preview canonical counts are not part of the saved active analysis;
- AI explanation is advisory only — only the deterministic proposal/approval
  path controls canonical promotion.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from logsense.integrations.service import IntegrationRequestError
from logsense.ui import shared
from logsense.workspace.cases import CaseWorkspaceError

MAPPING_STATE_LABELS = {
    "PREMAPPED": ("Mapped", "A built-in deterministic mapping covers this source."),
    "APPROVED_USER": (
        "Approved mapping",
        "You explicitly approved a mapping bound to this artifact fingerprint.",
    ),
    "PROPOSAL_AVAILABLE": (
        "Needs mapping review",
        "A deterministic mapping proposal exists — nothing is active until you approve it.",
    ),
    "APPROVAL_REJECTED_NEEDS_REVIEW": (
        "Approval rejected — needs review",
        "A prior approval no longer matches this artifact's current schema. Review again.",
    ),
    "NO_MAPPING_AVAILABLE": (
        "No deterministic mapping available yet",
        "LogSense found no schema-compatible template. The artifact stays preserved as evidence.",
    ),
    "OPAQUE_PRESERVED": (
        "Preserved, not parsed",
        "LogSense could not parse this format; the bytes are preserved byte-for-byte as evidence.",
    ),
}

EVIDENCE_QUALIFICATION_LABELS = {
    "CAN_ESTABLISH": "Qualified — can support forensic claims",
    "CAN_SUPPORT": "Partial — supports but cannot establish claims alone",
    "CANNOT_ESTABLISH": "Not qualified for the claims evaluated",
    "NOT_ASSESSED": "Not assessed yet",
    "UNKNOWN": "Not assessed",
}

STATE_HELP = {
    "Detected format": "How LogSense parsed the file structure.",
    "Semantic profile": (
        "What kind of source LogSense believes this evidence represents based on "
        "deterministic profile rules."
    ),
    "Mapping proposal": (
        "A reusable deterministic mapping that appears structurally compatible with "
        "this source. It is not active until you approve it."
    ),
    "Approved mapping": "The mapping has been explicitly bound to this artifact fingerprint.",
    "Source qualification": "Whether this source is suitable to support a particular forensic claim.",
    "Adapter qualification": (
        "Whether the parser/adapter handled the artifact as expected. This does not "
        "automatically make the source authoritative."
    ),
}

MAPPING_STEPS = (
    "Choose source",
    "Inspect detected schema",
    "Review mapping proposal",
    "Approve or leave unapproved",
    "Re-run deterministic analysis",
)


def _analysis_stale(svc: Any, case_id: str, overview: Mapping[str, Any]) -> list[str]:
    """Reuse the command-center staleness check over the same overview."""
    try:
        state = svc.command_center_state(case_id, _overview=overview)
    except (IntegrationRequestError, CaseWorkspaceError):
        return []
    return list(state["analysis"].get("staleReasons") or ())


def render_readiness(overview: Mapping[str, Any]) -> str:
    """Compact source-readiness summary; returns the overall readiness state."""
    readiness = overview.get("readiness") or {}
    state = str(readiness.get("state") or "NO_EVIDENCE")
    label = readiness.get("stateLabel") or state
    counts = readiness
    st.markdown("**Source readiness**")
    if state == "READY":
        st.success(f"READY — {label}.")
    elif state == "READY_WITH_LIMITATIONS":
        st.info(f"READY WITH LIMITATIONS — {label}.")
    elif state == "REVIEW_RECOMMENDED":
        st.warning(f"REVIEW RECOMMENDED — {label}.")
    else:
        st.info(f"{label}.")
    cols = st.columns(4)
    cols[0].metric("Artifacts", counts.get("artifacts", 0))
    cols[1].metric("Parsed", counts.get("parsed", 0))
    cols[2].metric("Profiled", counts.get("profiled", 0))
    cols[3].metric("Mapped", counts.get("mapped", 0))
    cols2 = st.columns(4)
    cols2[0].metric("Needs mapping review", counts.get("needsMappingReview", 0))
    cols2[1].metric("No mapping yet", counts.get("noMappingAvailable", 0))
    cols2[2].metric("Opaque / preserved only", counts.get("opaquePreserved", 0))
    cols2[3].metric(
        "Preview canonical records",
        sum(int(s.get("canonicalEventCount") or 0) for s in overview.get("sources") or ()),
    )
    st.caption(
        "Preview counts reflect committed evidence plus current approvals — they "
        "become part of the active analysis only after you re-run it."
    )
    return state


def render_source_cards(overview: Mapping[str, Any]) -> str | None:
    """Render one card per source; return the operator-selected artifact id."""
    sources = overview.get("sources") or ()
    if not sources:
        st.info("No committed sources yet — add evidence on the Case & Evidence step first.")
        return None
    options = [str(s["artifactId"]) for s in sources]
    for source in sources:
        label, help_text = MAPPING_STATE_LABELS.get(
            str(source["mappingState"]), (str(source["mappingState"]), "")
        )
        eq = (source.get("evidenceQualification") or {}).get("state") or "NOT_ASSESSED"
        with st.container(border=True):
            top, right = st.columns([3, 1])
            with top:
                st.markdown(f"**{source.get('path')}** — `{label}`")
                st.caption(
                    f"Format {source.get('format')} · adapter `{source.get('syntaxAdapterId')}` · "
                    f"evidence qualification: "
                    f"{EVIDENCE_QUALIFICATION_LABELS.get(eq, eq)} · "
                    f"profiles: {', '.join(source.get('semanticProfileIds') or ()) or 'none'}"
                )
                if help_text:
                    st.caption(help_text)
                st.caption(f"**Next:** {source.get('nextAction')}")
            with right:
                st.caption(f"`{str(source.get('sha256'))[:12]}…`")
    selected = st.selectbox(
        "Choose a source to inspect",
        options,
        format_func=lambda aid: next(
            (str(s["path"]) for s in sources if s["artifactId"] == aid), aid
        ),
        key="srcmap_selected_artifact",
    )
    return selected


def _render_proposal_review(
    case_id: str,
    artifact_id: str,
    proposal_id: str,
    *,
    _analysis: Mapping[str, Any] | None = None,
) -> None:
    svc = shared.service()
    try:
        detail = svc.mapping_proposal_detail(
            case_id=case_id,
            artifact_id=artifact_id,
            proposal_id=proposal_id,
            _analysis=_analysis,
        )
    except (IntegrationRequestError, CaseWorkspaceError) as exc:
        st.error(str(exc))
        return

    proposal = detail["proposal"]
    st.warning(
        "PROPOSAL ONLY — this mapping has not been promoted into deterministic "
        "analysis. Nothing about this source changes until you explicitly approve."
    )
    st.caption(f"Template profile: `{detail['templateProfileId']}` · proposal `{proposal_id}`")
    st.caption(STATE_HELP["Mapping proposal"])

    coverage = detail["coverage"]
    st.markdown("**Mapping coverage**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Detected fields", coverage["detectedFields"])
    c2.metric("Mapped fields", coverage["mappedFields"])
    c3.metric("Unmapped fields", len(coverage["unmappedFields"]))
    c4.metric(
        "Required mapped", f"{coverage['requiredMappedFields']} / {coverage['requiredTotal']}"
    )
    st.caption(
        "Unmapped fields remain preserved as evidence. Not every source field "
        "needs canonical promotion — mapping only promotes what canonical "
        "analysis requires."
    )
    if coverage["unmappedFields"]:
        with st.expander("Unmapped fields (preserved, not promoted)"):
            st.write(", ".join(f"`{f}`" for f in coverage["unmappedFields"]))

    st.markdown("**Proposed field mapping**")
    st.dataframe(
        [
            {
                "Source field": row["sourceField"],
                "Canonical field": row["canonicalField"],
                "Transform": row.get("transform"),
                "Role": row["category"],
                "Required": "Yes" if row["required"] else "No",
            }
            for row in detail["mappingRows"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    basis = proposal.get("basis") or []
    if basis:
        st.caption("Compatibility basis: " + ", ".join(f"`{b}`" for b in basis))

    approve_col, _ = st.columns([1, 3])
    with approve_col:
        if st.button(
            "Approve mapping for this source",
            type="primary",
            key=f"srcmap_approve_{artifact_id}_{proposal_id}",
        ):
            try:
                result = svc.approve_case_mapping(
                    case_id=case_id,
                    artifact_id=artifact_id,
                    proposal_id=proposal_id,
                    approval_source="USER_UI",
                )
            except (IntegrationRequestError, CaseWorkspaceError) as exc:
                st.error(str(exc))
            else:
                st.session_state["srcmap_just_approved"] = result["approved"]["mappingProfile"].get(
                    "profileId"
                )
                st.success(
                    "Mapping ready — rerun deterministic analysis to include "
                    "this source in the active investigation."
                )
                st.rerun()


def render_source_detail(
    case_id: str,
    artifact_id: str,
    overview: Mapping[str, Any],
    *,
    _analysis: Mapping[str, Any] | None = None,
) -> None:
    """Full review surface for one artifact: schema, proposal, approval, provenance."""
    svc = shared.service()
    source = next(
        (s for s in overview.get("sources") or () if s["artifactId"] == artifact_id), None
    )
    if source is None:
        st.error("Source not found in the current analysis.")
        return

    try:
        detail = svc.source_profile_detail(case_id=case_id, artifact_id=artifact_id)
    except (IntegrationRequestError, CaseWorkspaceError) as exc:
        st.error(str(exc))
        return

    label, help_text = MAPPING_STATE_LABELS.get(
        str(source["mappingState"]), (str(source["mappingState"]), "")
    )
    st.markdown(f"#### {source.get('path')}")
    st.caption(f"**{label}** — {help_text}")
    st.write(
        f"**What this is:** {detail.get('format')} evidence containing "
        f"{detail.get('recordCount') or 0} record(s), preserved as "
        f"`{str(source.get('sha256'))[:16]}…`."
    )

    m = st.columns(4)
    m[0].metric("Format", detail.get("format"))
    m[1].metric("Records", detail.get("recordCount"))
    m[2].metric("Fields", len(detail.get("fieldPaths") or ()))
    m[3].metric("Preview canonical records", source.get("canonicalEventCount") or 0)

    st.markdown("**Qualification — separate dimensions**")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Parse / profile", source.get("profileState") or "NOT_ASSESSED")
    q2.metric("Mapping", label)
    q3.metric(
        "Adapter qualification",
        (source.get("adapterQualification") or {}).get("state") or "NOT_ASSESSED",
    )
    eq = (source.get("evidenceQualification") or {}).get("state") or "NOT_ASSESSED"
    q4.metric("Evidence qualification", EVIDENCE_QUALIFICATION_LABELS.get(eq, eq))
    st.caption(
        "Parsed ≠ mapped ≠ qualified. Adapter qualification ≠ evidence "
        "qualification ≠ claim authority — nothing here grants claim authority."
    )

    relevance = detail.get("controlRelevance") or []
    if relevance:
        st.markdown("**Potential competition relevance** *(evidence hint — not control proof)*")
        for item in relevance:
            st.caption(
                f"- {item['controlLabel']} (`{item['controlCode']}`) — matched roles: "
                + ", ".join(f"`{r}`" for r in item["matchedRoles"])
            )
        st.caption(
            "Field evidence suggests this source may be useful for these controls. "
            "Relevance does not prove measurement completeness."
        )

    schema = detail.get("schemaProfile") or {}
    field_profiles = schema.get("fieldProfiles") or []
    if field_profiles:
        with st.expander(f"Source field explorer ({len(field_profiles)} fields)", expanded=True):
            total_records = int(detail.get("recordCount") or 0)
            st.dataframe(
                [
                    {
                        "Field": f.get("path"),
                        "Observed type": ",".join(f.get("dataTypes") or ()),
                        "Presence": (
                            f"{round((1 - float(f.get('nullRate') or 0)) * 100)}%"
                            if total_records
                            else "n/a"
                        ),
                        "Example (bounded)": _bounded_sample(f.get("sampleValuesRedacted") or ()),
                        "Cardinality": f.get("cardinality"),
                    }
                    for f in field_profiles
                ],
                use_container_width=True,
                hide_index=True,
            )
    if detail.get("parseFailures"):
        with st.expander(f"Parse failures ({len(detail['parseFailures'])})"):
            st.dataframe(list(detail["parseFailures"]), use_container_width=True, hide_index=True)

    approved = svc.approved_mapping_detail(case_id=case_id, artifact_id=artifact_id)
    if approved is not None:
        st.success(
            "APPROVED BY USER — mapping bound to this exact artifact fingerprint. "
            "Materially different evidence requires review again."
        )
        st.caption(
            f"Fingerprint `{str(approved['artifactSha256'])[:16]}…` · runtime profile "
            f"`{approved['profileId']}` · approval mode `{approved['approvalMode']}` · "
            f"approved {approved['approvedAt']}"
        )

    for proposal_id in source.get("proposalIds") or ():
        _render_proposal_review(case_id, artifact_id, proposal_id, _analysis=_analysis)

    with st.expander("Provenance path"):
        try:
            prov = svc.source_provenance(
                case_id=case_id, artifact_id=artifact_id, _overview=overview
            )
        except (IntegrationRequestError, CaseWorkspaceError) as exc:
            st.caption(str(exc))
        else:
            st.caption(
                "raw artifact → syntax adapter → schema profile → semantic profile → "
                "approved MappingProfile → canonical event → finding/measurement"
            )
            st.dataframe(
                [
                    {"Step": "Raw artifact", "Value": prov["artifact"]},
                    {"Step": "Fingerprint (SHA-256)", "Value": prov["artifactSha256"]},
                    {"Step": "Syntax adapter", "Value": prov["syntaxAdapter"]},
                    {"Step": "Detected format", "Value": prov["format"]},
                    {"Step": "Schema profile", "Value": prov["schemaProfile"]},
                    {
                        "Step": "Semantic profiles",
                        "Value": ", ".join(prov["semanticProfiles"]) or "none",
                    },
                    {"Step": "Mapping profile", "Value": str(prov["mappingProfile"])},
                    {
                        "Step": "Canonical records produced",
                        "Value": str(prov["canonicalEventCount"]),
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.info(f"**Next:** {source.get('nextAction')}")


def _bounded_sample(values: Any) -> str:
    text = "; ".join(str(v) for v in list(values)[:3])
    return text[:120] + ("…" if len(text) > 120 else "")


def render_source_setup(case_id: str, *, compact: bool = False) -> None:
    """Guided source-mapping workflow — full page or competition-step variant.

    One preview analysis is computed per render and shared across every widget
    (``_analysis``/``_overview``) — no persistent caching, so evidence or
    mapping changes are always reflected on the next render.
    """
    svc = shared.service()
    try:
        # Preview once; empty evidence raises inside analyze_case, in which case
        # source_overview returns a clean NO_EVIDENCE state without a preview.
        try:
            preview: Mapping[str, Any] | None = svc.preview_case_analysis(case_id)
        except IntegrationRequestError:
            preview = None
        overview = svc.source_overview(case_id, _analysis=preview)
    except (IntegrationRequestError, CaseWorkspaceError) as exc:
        st.error(str(exc))
        return

    readiness_state = render_readiness(overview)
    st.caption(
        "Mapping workflow: " + " → ".join(MAPPING_STEPS) + ". "
        "AI can explain a source; it can never approve a mapping."
    )

    stale_reasons = _analysis_stale(svc, case_id, overview)
    if stale_reasons:
        st.warning(
            "Analysis rerun required — evidence or mapping approvals changed "
            "after the active analysis."
        )

    unsupported = [
        s for s in overview.get("sources") or () if s["mappingState"] == "NO_MAPPING_AVAILABLE"
    ]
    for source in unsupported:
        st.info(
            f"**New source detected:** `{source['path']}` ({source.get('format')}). "
            "No deterministic mapping is available yet — the artifact is still "
            "preserved as evidence. You can inspect its fields, ask AI to "
            "explain it, or continue analysis with current coverage."
        )

    if compact:
        # Competition step: summary + pointer only; full review lives on the page.
        if readiness_state == "REVIEW_RECOMMENDED":
            if st.button("Review Sources", key="comp_srcmap_open", type="primary"):
                st.switch_page("pages/source_mapping.py")
        elif readiness_state == "READY":
            st.write("You can continue to deterministic analysis.")
        return

    selected = render_source_cards(overview)
    if selected:
        st.divider()
        render_source_detail(case_id, selected, overview, _analysis=preview)

    if overview.get("sources"):
        st.divider()
        if st.button("Re-run deterministic analysis", key="srcmap_rerun", type="primary"):
            with st.spinner("Re-running canonical analysis with current approvals…"):
                try:
                    output = shared.run_case_analysis(case_id)
                except Exception as exc:  # noqa: BLE001
                    st.error(shared.intake_error_text(exc))
                else:
                    st.success(
                        f"Analysis refreshed — `{output['analysis'].get('analysisRunId')}`. "
                        "Canonical evidence now reflects approved mappings."
                    )


# ---- Collection Health (R5-03) -------------------------------------------------

_HEALTH_LABELS = {
    "PARSED": "Parsed",
    "PARTIAL": "Partially parsed",
    "FAILED": "Failed to parse",
    "OPAQUE_UNPARSED": "Preserved, not parsed",
    "NOT_ASSESSED": "Not assessed",
}


def render_collection_health(case_id: str, *, compact: bool = False) -> None:
    """Operator-readable collection health — descriptive, never a verdict.

    Answers: what arrived, how well it parsed, and what limitations bind
    coverage. Unknown dimensions stay visibly unknown.
    """
    st.markdown("#### Collection Health")
    st.caption(
        "**What is this:** the evidence actually received locally and how "
        "successfully it parsed. **Why it matters:** controls measured on "
        "broken collection inherit those limits. This is descriptive — never "
        "a pass/fail verdict."
    )
    svc = shared.service()
    try:
        health = svc.collection_health(case_id)
    except (IntegrationRequestError, CaseWorkspaceError) as exc:
        st.error(str(exc))
        return

    if health["state"] == "NO_EVIDENCE":
        st.info("No evidence committed yet — collection health has nothing to report.")
        return
    if health["state"] == "ANALYSIS_REQUIRED":
        st.info(
            f"{health['artifacts']} artifact(s) committed. Run deterministic "
            "analysis to measure parse outcomes, time coverage and continuity."
        )
        return

    totals = health.get("totals") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artifacts", health["artifacts"])
    c2.metric("Parsed sources", health["parsedSources"])
    c3.metric("Preserved only", health["preservedOnlySources"])
    failed = totals.get("failedRecordCount")
    c4.metric("Malformed records", failed if failed is not None else "Not measured")

    d1, d2, d3 = st.columns(3)
    d1.metric("Quarantined", "Not measured")
    dup = health.get("duplicateGroups")
    d2.metric("Duplicate groups", dup if isinstance(dup, int) else "Not measured")
    observed = health.get("observedTime") or {}
    if observed.get("first"):
        d3.metric(
            "Observed time range",
            f"{str(observed['first'])[11:19]} → {str(observed['last'])[11:19]}",
        )
    else:
        d3.metric("Observed time range", "Not measured")

    e1, e2, e3 = st.columns(3)
    e1.metric("Time quality", str(health.get("timeQuality") or "NOT_MEASURED").title())
    e2.metric(
        "Continuity",
        str(health.get("continuityState") or "NOT_MEASURED").replace("_", " ").title(),
    )
    e3.metric(
        "Coverage",
        str(health.get("coverageState") or "NOT_ASSESSED").replace("_", " ").title(),
    )

    limitations = [str(x) for x in health.get("limitations") or ()]
    if limitations:
        with st.expander(f"Known limitations ({len(limitations)})", expanded=not compact):
            st.caption("**What is unknown:** these bound what the evidence can establish.")
            for item in limitations[:12]:
                st.write(f"- `{item}`")
            if len(limitations) > 12:
                st.caption(f"…and {len(limitations) - 12} more")

    if not compact:
        with st.expander("Per-source detail", expanded=False):
            for source in health.get("sources") or ():
                label = str(source.get("path") or source.get("artifactId"))
                state = _HEALTH_LABELS.get(
                    str(source.get("profileState")), str(source.get("profileState"))
                )
                st.markdown(f"**{label}** — {state}")
                st.caption(
                    f"adapter `{source.get('adapterId')}` · "
                    f"records {source.get('recordCount')} · "
                    f"parsed {source.get('parsedRecordCount')} · "
                    f"malformed {source.get('failedRecordCount')} · "
                    f"events {source.get('canonicalEventCount')}"
                )
                if source.get("limitations"):
                    st.caption("limitations: " + ", ".join(source["limitations"][:6]))
