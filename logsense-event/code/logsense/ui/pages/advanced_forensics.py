"""Forensic Deep Dive — the full expert workbench on the active case.

Everything the original single-page workbench showed, bound to the active
case's deterministic outputs. Competition operators should not need this;
it exists for reviewers and troubleshooting.
"""

from __future__ import annotations

import streamlit as st

from logsense.ui import shared, workbench_views

st.title("Forensic Deep Dive")
st.caption(
    "Advanced deterministic views — semantic mapping, timeline, actions, "
    "compare, findings, proof frontier, and raw report. Read-only."
)

shared.render_case_sidebar()
case_id, analysis, report = shared.ensure_results()

workbench_views.render_case(shared.workspace_root(), case_id)
workbench_views.render_manifest(shared.workspace_root(), case_id)
workbench_views.render_evidence_inventory(shared.workspace_root(), case_id, analysis)
workbench_views.render_explore(analysis)
workbench_views.render_timeline(analysis)
workbench_views.render_actions(analysis)
workbench_views.render_compare(report)
workbench_views.render_findings(report)
workbench_views.render_proof(report)
workbench_views.render_report(report)
