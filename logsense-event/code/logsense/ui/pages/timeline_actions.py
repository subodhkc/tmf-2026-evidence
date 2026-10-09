"""Timeline & Actions — canonical ordering and reconstructed action groups."""

from __future__ import annotations

import streamlit as st

from logsense.ui import shared, workbench_views

st.title("Timeline & Actions")
st.caption(
    "Ordering comes from canonical timeline records; actions are reconstructed "
    "deterministically. Sequence here does not imply causality."
)

shared.render_case_sidebar()
_case_id, analysis, _report = shared.ensure_results()

tab_timeline, tab_actions, tab_explore = st.tabs(["Timeline", "Actions", "Explore / Mapping"])
with tab_timeline:
    workbench_views.render_timeline(analysis)
    workbench_views.render_forensic_window(analysis)
with tab_actions:
    workbench_views.render_actions(analysis)
with tab_explore:
    workbench_views.render_explore(analysis)
