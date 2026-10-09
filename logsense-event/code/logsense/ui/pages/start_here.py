"""Start Here — the default landing page.

Three plain-language paths plus a one-click sample investigation. Nothing on
this page requires forensic-engine knowledge.
"""

from __future__ import annotations

import streamlit as st

from logsense.ui import shared

st.title("LogSense")
st.caption(
    "Deterministic forensic workbench. Evidence is reconstructed by the deterministic "
    "engine first; AI helps you investigate and explain the result. AI never becomes "
    "the source of forensic truth."
)

left, right = st.columns(2)
with left:
    st.subheader("AI investigator")
    st.caption(
        "AI explains deterministic findings — it cannot change them. "
        + shared.GLOSSARY["Deterministic"]
    )
    st.write("Active:", shared.ai_status_line())
with right:
    st.subheader("Workspace")
    st.caption("Cases and committed evidence live on this machine, outside the repository.")
    st.write(f"`{shared.workspace_root()}`")

with st.expander("AI setup — choose OpenAI or Claude", expanded=False):
    shared.render_ai_configuration()

resume = shared.competition_resume()
if resume is not None:
    st.success(
        f"Competition investigation in progress — case `{resume['caseId']}`."
    )
    if st.button("Resume Competition Investigation", type="primary"):
        shared.set_active_case(resume["caseId"])
        st.session_state["competition_step"] = resume["competitionStep"]
        st.switch_page("pages/competition.py")

st.divider()
st.subheader("How do you want to work?")

competition, mapping = st.columns(2)
with competition:
    st.markdown("**Competition Investigation** — *recommended for TM Forum*")
    st.write(
        "Investigate supplied evidence, reconstruct competition runs, measure "
        "Controls 7/9/16 and prepare evidence for the HAIEC Control Test."
    )
    st.page_link("pages/competition.py", label="Start Competition Investigation", icon=None)
    with st.expander("TM Forum event mission — read first"):
        st.write(
            "The lab already provides the AI system and its collaborating "
            "agents — you are not building the agents. Your job is to build "
            "controls around the supplied system and **independently prove "
            "whether those controls held**."
        )
        st.code(
            "Customer Zone      IT Zone           Network Zone\n"
            "  chat agent   →A→   triage agent   →B→   investigation agent\n"
            "  tickets            account/AWS         inventory + digital twin\n"
            "\n"
            "        Shared Model Gateway — model calls across all zones",
            language=None,
        )
        st.caption(
            "Expected architecture shape — actual field names, APIs and "
            "source semantics must be discovered from the live lab. "
            "The event workflow is built into Competition Mode: understand → "
            "discover → ingest → map → reconstruct → choose control → "
            "calibrate → freeze in HAIEC → measure → hand off → package → rehearse."
        )
with mapping:
    st.markdown("**Source Setup & Mapping** — *use when new evidence does not map cleanly*")
    st.write(
        "Use this when the event gives you a new or unfamiliar log, telemetry "
        "export or dataset — profile it, review the deterministic mapping "
        "proposal, approve it and rerun analysis."
    )
    st.page_link("pages/source_mapping.py", label="Set Up New Sources", icon=None)

general, advanced = st.columns(2)
with general:
    st.markdown("**General Investigation**")
    st.write(
        "Run the full deterministic forensic workflow outside the "
        "competition-specific control flow."
    )
    st.page_link("pages/case_evidence.py", label="Open Case & Evidence")
with advanced:
    st.markdown("**Advanced Forensics**")
    st.write(
        "Inspect detailed mappings, evidence qualification, relations, state "
        "transitions, provenance and forensic boundaries."
    )
    st.page_link("pages/advanced_forensics.py", label="Open Advanced Views")

st.divider()
st.subheader("Learn the flow with sample data")
st.write(
    "Runs the bundled synthetic Golden fixture (GFB-001) through the real "
    "deterministic pipeline: case → evidence → analysis → summary."
)
if st.button("Try Sample Investigation", type="primary"):
    with st.spinner("Creating sample case and running deterministic analysis..."):
        try:
            cid = shared.run_sample_investigation()
        except Exception as exc:
            st.error(shared.intake_error_text(exc))
        else:
            st.success(f"Sample case ready: {cid}")
            st.page_link("pages/investigation_summary.py", label="Open the Investigation Summary")
