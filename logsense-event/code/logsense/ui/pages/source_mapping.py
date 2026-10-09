"""Source Setup & Mapping — first-class event page.

Guides the operator through: choose source → inspect detected schema →
review the deterministic mapping proposal → explicitly approve → re-run
analysis. Only the canonical runtime-mapping owner promotes mappings; this
page never mutates canonical truth itself.
"""

from __future__ import annotations

import streamlit as st

from logsense.ui import shared, source_view

st.title("Source Setup & Mapping")
st.caption(
    "Inspect unfamiliar logs or telemetry, profile their schema, review "
    "LogSense's deterministic mapping proposals, explicitly approve a mapping, "
    "and rerun analysis — no manual JSON editing required."
)

shared.render_case_sidebar()
case_id = shared.ensure_case()

source_view.render_source_setup(case_id)

with st.expander("Ask LogSense — advisory explanation only", expanded=False):
    st.caption(
        "AI can explain this source in plain language. Advisory explanation is "
        "never a MappingProposal and never an approved mapping — only explicit "
        "approval promotes a mapping."
    )
    question = st.text_area(
        "Question about this source",
        placeholder="What do these fields probably represent? Which fields are useful for run correlation?",
        key="srcmap_ai_question",
    )
    if st.button("Explain (advisory)", key="srcmap_ai_ask"):
        results = shared.case_results(case_id)
        try:
            view = shared.ask_question(
                question,
                (results or {}).get("analysis") or {},
                (results or {}).get("report") or {},
                competition=shared.competition_payload(case_id),
            )
        except Exception as exc:  # noqa: BLE001
            st.error(shared.provider_unavailable_message(exc))
        else:
            st.caption("*Advisory explanation — not a mapping decision.*")
            st.markdown(view["answer"])

st.divider()
cols = st.columns(3)
cols[0].page_link("pages/case_evidence.py", label="← Case & Evidence")
cols[1].page_link("pages/competition.py", label="Back to Competition")
cols[2].page_link("pages/investigation_summary.py", label="Investigation Summary →")
