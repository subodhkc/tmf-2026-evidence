"""Adapter Qualification — active-case view.

Reads the active case's current deterministic analysis — no manual JSON
upload. Adapter qualification describes whether the parser/adapter handled
the artifact as expected; it never grants evidence qualification or claim
authority.
"""

from __future__ import annotations

import streamlit as st

from logsense.adapters.qualification_records import project_adapter_qualification_records
from logsense.ui import shared

st.set_page_config(page_title="LogSense — Adapter Qualification", layout="wide")
st.title("Adapter Qualification")
st.caption(
    "Read-only adapter qualification boundary. Qualified syntax routing does not "
    "grant forensic semantic authority or canonical promotion."
)

shared.render_case_sidebar()
case_id = shared.ensure_case()

results = shared.case_results(case_id)
analysis = (results or {}).get("analysis") or {}
if not analysis:
    st.info(
        "No analysis for this case yet — run deterministic analysis to produce "
        "adapter qualification records."
    )
    if st.button("Run deterministic analysis", key="adq_run"):
        with st.spinner("Analyzing committed evidence…"):
            try:
                output = shared.run_case_analysis(case_id)
            except Exception as exc:  # noqa: BLE001
                st.error(shared.intake_error_text(exc))
                st.stop()
            analysis = output["analysis"]
    else:
        st.stop()

st.caption(
    f"Analysis `{analysis.get('analysisRunId')}` · case `{case_id}` — derived from "
    "the current deterministic analysis, not an uploaded file."
)

rows = project_adapter_qualification_records(analysis)
if not rows:
    st.info("No artifact adapter selections are present in this analysis.")
    st.stop()

for row in rows:
    label = str(row.get("path") or row.get("artifactId") or "Artifact")
    with st.expander(label):
        left, right = st.columns(2)
        with left:
            st.write("Adapter:", row.get("adapterId"))
            st.write("Version:", row.get("adapterVersion"))
            st.write("Format:", row.get("formatFamily"))
            st.write("Qualification state:", row.get("qualificationState"))
            st.write("Qualification basis:", row.get("qualificationBasis"))
            st.write("Schema profiles:", row.get("schemaProfiles"))
            st.write("Semantic profiles:", row.get("semanticProfiles"))
        with right:
            st.write("Supported fields:", row.get("supportedFields"))
            st.write("Unsupported fields:", row.get("unsupportedFields"))
            st.write("Canonical promotion allowed:", row.get("canonicalPromotionAllowed"))
            st.write("May emit relation candidates:", row.get("mayEmitRelationCandidates"))
            st.write("Deterministic mapping:", row.get("deterministicMapping"))
            st.write("Validated contract:", row.get("lastValidatedAgainstContractVersion"))
        if row.get("knownLimitations"):
            st.write("Known limitations:", row["knownLimitations"])
        st.caption("Adapter qualification != evidence qualification != claim authority.")
