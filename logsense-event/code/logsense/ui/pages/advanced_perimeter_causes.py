from __future__ import annotations

import json

import streamlit as st

from logsense.presentation import analysis_perimeter_view, cause_evaluation_rows

st.set_page_config(page_title="LogSense — Perimeter / Causes", layout="wide")
st.title("Analysis Perimeter / Cause Evaluations")
st.caption(
    "Read-only deterministic boundary. Comparison compatibility and cause state are displayed exactly as supplied; the UI never promotes root cause."
)

upload = st.file_uploader(
    "Deterministic forensic report JSON", type=["json"], key="perimeter_cause_report"
)
if upload is None:
    st.info("Load deterministic report JSON.")
    st.stop()

try:
    report = json.loads(upload.getvalue().decode("utf-8"))
except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    st.error(f"Invalid JSON: {exc}")
    st.stop()

if not isinstance(report, dict):
    st.error("Expected one report JSON object.")
    st.stop()

st.subheader("Analysis perimeter")
perimeter = analysis_perimeter_view(report)
st.write("State:", perimeter["state"])
if perimeter["identity"] is not None:
    st.json(perimeter["identity"])
else:
    st.info("AnalysisPerimeterIdentity was not emitted for this report.")
if perimeter["caseStatePerimeterRefs"]:
    st.write("Case-state perimeter refs:", perimeter["caseStatePerimeterRefs"])
if perimeter["limitations"]:
    st.write("Limitations:", perimeter["limitations"])
st.caption(
    "Changed or missing analysis perimeter can make comparisons partial or incomparable; it is not system drift by itself."
)

st.subheader("Cause evaluations")
rows = cause_evaluation_rows(report)
if not rows:
    st.info("No CauseEvaluation records are present.")
else:
    for row in rows:
        label = str(row.get("evaluationId") or row.get("ruleId") or "Cause evaluation")
        with st.expander(label):
            st.write("Rule:", row.get("ruleId"))
            st.write("State:", row["state"]["label"])
            st.write("Subject refs:", row["subjectRefs"])
            st.write("Evidence refs:", row["evidenceRefs"])
            st.write("Independent lineage families:", row["independentLineageFamilies"])
            st.write("Gap refs:", row["gapRefs"])
            st.write("Limitations:", row["limitations"])
            st.write("Root cause claimed by this UI:", False)
            st.caption(
                "SUPPORTED_CANDIDATE, SUPPORTED, ESTABLISHED, and CORROBORATED remain distinct owner states; this surface does not collapse them into ROOT_CAUSE."
            )
