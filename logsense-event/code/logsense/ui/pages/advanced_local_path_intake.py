from __future__ import annotations

from pathlib import Path

import streamlit as st

from logsense.pipeline.intake import EvidenceIntakeError, commit_evidence, preview_evidence
from logsense.presentation import manifest_rows
from logsense.user_config import resolve_workspace_root
from logsense.workspace.cases import CaseWorkspaceError, commit_evidence_to_case, list_cases

st.set_page_config(page_title="LogSense — Local Path Intake", layout="wide")
st.title("Folder / Local Path Intake")
st.caption(
    "Uses the same deterministic intake path as file/archive gather. Preview first; commit only on explicit action."
)

workspace_root = resolve_workspace_root()
cases = list_cases(workspace_root)
if not cases:
    st.warning("Create a case in the main workbench before committing local-path evidence.")
    st.stop()

case_id = st.selectbox("Case", [row.case_id for row in cases])
raw_paths = st.text_area(
    "Local files or directories",
    help="One local file or directory path per line. Directories are recursively enumerated by the canonical intake engine.",
)

paths = [Path(line.strip()).expanduser() for line in raw_paths.splitlines() if line.strip()]
if not paths:
    st.info("Enter at least one local file or directory path.")
    st.stop()

missing = [str(path) for path in paths if not path.exists()]
if missing:
    st.error("These local paths do not exist:")
    st.write(missing)
    st.stop()

try:
    manifest = preview_evidence(paths)
except EvidenceIntakeError as exc:
    st.error(str(exc))
    st.stop()

st.write("Manifest ID:", f"`{manifest.manifest_id}`")
st.write("Dataset digest:", f"`{manifest.dataset_digest}`")
st.metric("Evidence files", manifest.file_count)
st.metric("Total bytes", manifest.total_size_bytes)
st.dataframe(manifest_rows(manifest), use_container_width=True)
st.caption(
    "Directory traversal here means enumerating the user-selected local directory. Archive traversal/symlink escapes remain rejected by the canonical intake engine."
)

if st.button("Commit manifest to case", type="primary"):
    try:
        committed = commit_evidence(manifest)
        payload = commit_evidence_to_case(workspace_root, case_id=case_id, committed=committed)
    except (EvidenceIntakeError, CaseWorkspaceError) as exc:
        st.error(str(exc))
    else:
        st.success(f"Committed immutable evidence: {payload['manifestId']}")
