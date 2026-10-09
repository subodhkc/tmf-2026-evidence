"""LogSense workbench entrypoint — ``logsense`` launches this.

Navigation is event-first: a competition operator should reach a working
investigation without touching the expert views. Specialized surfaces live
under Advanced for troubleshooting.
"""

from __future__ import annotations

import streamlit as st

from logsense.user_config import load_secrets_into_environ

st.set_page_config(page_title="LogSense Forensic Workbench", layout="wide")

load_secrets_into_environ()

pg = st.navigation(
    {
        "LogSense": [
            st.Page("pages/start_here.py", title="Start Here", default=True),
            st.Page("pages/competition.py", title="Competition"),
            st.Page("pages/case_evidence.py", title="Case & Evidence"),
            st.Page("pages/source_mapping.py", title="Source Setup & Mapping"),
            st.Page("pages/investigation_summary.py", title="Investigation Summary"),
            st.Page("pages/timeline_actions.py", title="Timeline & Actions"),
            st.Page("pages/ask_logsense.py", title="Ask LogSense"),
            st.Page("pages/verify.py", title="Verify"),
            st.Page("pages/export.py", title="Export"),
        ],
        "Advanced": [
            st.Page("pages/advanced_forensics.py", title="Forensic Deep Dive"),
            st.Page("pages/advanced_action_relation_state.py", title="Action / Relation / State"),
            st.Page("pages/advanced_evidence_traceability.py", title="Claims / Evidence Cards"),
            st.Page("pages/advanced_adapter_qualification.py", title="Adapter Qualification"),
            st.Page("pages/advanced_local_path_intake.py", title="Local Path Intake"),
            st.Page("pages/advanced_perimeter_causes.py", title="Perimeter / Causes"),
        ],
    }
)
pg.run()
