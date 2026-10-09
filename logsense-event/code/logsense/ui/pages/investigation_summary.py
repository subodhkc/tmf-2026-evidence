"""Investigation Summary — the first page after analysis completes.

Plain-language deterministic answers only: what happened, what is and is not
established, evidence health, and what to do next. Every statement here comes
from the canonical analysis/report projections.
"""

from __future__ import annotations

import streamlit as st

from logsense.ui import shared, workbench_views

st.title("Investigation Summary")
st.caption(
    "Everything on this page is produced by the deterministic LogSense engine — "
    "no AI involved. Use Ask LogSense afterwards if you want it explained."
)

shared.render_case_sidebar()
case_id, analysis, report = shared.ensure_results()
report = report or {}
st.caption(f"Case `{case_id}`")

workbench_views.render_investigation_summary(analysis, report)

frontiers = list(report.get("evidenceFrontier") or analysis.get("evidenceFrontier") or ())
ask_col, verify_col = st.columns(2)
with ask_col:
    st.page_link(
        "pages/ask_logsense.py",
        label="Ask AI about this investigation",
        help="AI investigates and explains these deterministic results; it cannot change them.",
    )
with verify_col:
    if frontiers:
        st.page_link("pages/verify.py", label="Open the verification loop")
