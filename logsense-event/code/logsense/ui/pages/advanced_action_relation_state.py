from __future__ import annotations

import json

import streamlit as st

from logsense.presentation import action_rows, relation_rows, state_transition_rows

st.set_page_config(page_title="LogSense — Action / Relation / State", layout="wide")
st.title("Action / Relation / State")
st.caption(
    "Read-only deterministic drilldown. Relation admission and state attribution are never inferred by the UI."
)

upload = st.file_uploader(
    "Deterministic analysis JSON", type=["json"], key="relation_state_analysis"
)
if upload is None:
    st.info(
        "Load deterministic analysis JSON to inspect canonical actions, relations and state transitions."
    )
    st.stop()

try:
    analysis = json.loads(upload.getvalue().decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    st.error(f"Invalid JSON: {exc}")
    st.stop()

if not isinstance(analysis, dict):
    st.error("Expected one analysis JSON object.")
    st.stop()

st.subheader("Actions")
actions = action_rows(analysis)
if actions:
    st.dataframe(actions, use_container_width=True)
else:
    st.info("No canonical ActionGroup records are present.")

st.subheader("Relation evaluations")
relations = relation_rows(analysis)
if relations:
    st.dataframe(relations, use_container_width=True)
else:
    st.info("No RelationEvaluation records are present.")
st.caption(
    "PARTIAL/UNKNOWN/REJECTED relation decisions remain exactly that; UI display does not establish a relation."
)

st.subheader("State transitions")
transitions = state_transition_rows(analysis)
if transitions:
    st.dataframe(transitions, use_container_width=True)
else:
    st.info("No StateTransition records are present.")
st.caption(
    "A state transition is not action attribution unless the canonical transition owner contains an admitted relation binding."
)
