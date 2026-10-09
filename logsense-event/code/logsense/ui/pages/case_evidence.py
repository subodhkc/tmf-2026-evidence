"""Case & Evidence — create/open a case, add evidence, run analysis.

Canonical path only: uploads go through the same preview/commit intake the
API uses, and analysis runs through ``IntegrationService.analyze_case``. The
operator never sees or uploads internal analysis/report JSON.
"""

from __future__ import annotations

import streamlit as st

from logsense.pipeline.intake import preview_evidence
from logsense.presentation.workbench import manifest_rows
from logsense.ui import shared, workbench_views
from logsense.workspace.cases import (
    CaseExistsError,
    CaseWorkspaceError,
    create_case,
    evidence_inventory,
)

st.title("Case & Evidence")
st.caption(
    "One case = one investigation. Add raw evidence files, preview what will be "
    "committed, commit them immutably, then run deterministic analysis."
)

workspace_root = shared.workspace_root()

# --- 1. Case selection / creation -------------------------------------------------
st.subheader("1. Open or create a case")
open_col, create_col = st.columns(2)
with open_col:
    ids = shared.list_case_ids()
    options = [""] + ids
    picked = st.selectbox(
        "Open existing case",
        options,
        index=options.index(shared.active_case_id()) if shared.active_case_id() in options else 0,
        format_func=lambda value: value or "— select a case —",
    )
    if picked:
        shared.set_active_case(picked)
with create_col, st.form("create_case_form"):
    new_id = st.text_input("New case ID", placeholder="tmf-run-001")
    new_title = st.text_input("Title", placeholder="Competition run investigation")
    if st.form_submit_button("Create case"):
        try:
            create_case(workspace_root, case_id=new_id, title=new_title or None)
        except (CaseWorkspaceError, CaseExistsError, ValueError) as exc:
            st.error(str(exc))
        else:
            shared.set_active_case(new_id.strip())
            st.rerun()

case_id = shared.active_case_id()
if not case_id:
    st.info("Select or create a case to continue.")
    st.stop()

st.success(f"Active case: **{case_id}**")

# --- 2. Evidence upload / preview / commit ---------------------------------------
st.subheader("2. Add evidence")
st.caption(
    "Supported today: CSV, JSON, JSONL/NDJSON, YAML, plain-text logs, OTLP trace "
    "payloads, and ZIP/TAR archives. Unknown formats are preserved but not force-mapped. "
    + shared.GLOSSARY["Evidence"]
)
uploads = st.file_uploader(
    "Evidence files or archive",
    accept_multiple_files=True,
    type=None,
    help="Staged locally; committed only when you press Commit.",
)
if uploads:
    tmp, paths = shared.temp_extracted_paths(uploads)
    try:
        manifest = preview_evidence(paths)
        st.session_state["manifest_rows"] = manifest_rows(manifest)
        st.session_state["manifest_id"] = manifest.manifest_id
        st.session_state["dataset_digest"] = manifest.dataset_digest
        st.dataframe(st.session_state["manifest_rows"], use_container_width=True)
        st.caption("Manifest preview — no evidence semantics inferred yet.")
        if st.button("Commit evidence to case", type="primary"):
            try:
                payload = shared.commit_uploads_to_case(case_id, uploads)
            except Exception as exc:
                st.error(shared.intake_error_text(exc))
            else:
                st.success(f"Committed immutable evidence: `{payload['manifestId']}`")
                st.rerun()
    except Exception as exc:
        st.error(shared.intake_error_text(exc))
    finally:
        tmp.cleanup()

with st.expander("Advisory AI assist — explain these files (optional)"):
    st.caption(
        "AI suggestions here are advisory only — never canonical mappings or findings. "
        "A suggestion still has to be approved through the deterministic profile/mapping path."
    )
    note = st.text_area(
        "Ask AI to describe the uploaded evidence or suggest likely source types",
        key="advisory_prompt",
        placeholder="e.g. What do these files appear to contain and which source roles should I expect?",
    )
    file_names = ", ".join(str(u.name) for u in uploads) if uploads else ""
    if st.button("Ask for advisory explanation", disabled=not note.strip()):
        try:
            provider = shared.create_provider_from_ui()
            toolbox_prompt = (
                f"{note}\n\nOperator uploaded evidence filenames (names only, no content): {file_names}"
                if file_names
                else note
            )
            from logsense.ai.tools import InvestigatorToolbox

            answer = provider.ask(toolbox_prompt, InvestigatorToolbox())
        except Exception as exc:
            st.error(shared.provider_unavailable_message(exc))
        else:
            st.write(answer.text)
            st.caption("Advisory only — not forensic evidence.")

# --- 3. Committed inventory + manifest -------------------------------------------
workbench_views.render_manifest(workspace_root, case_id)
workbench_views.render_evidence_inventory(
    workspace_root, case_id, (shared.case_results(case_id) or {}).get("analysis")
)

# --- 4. Run deterministic analysis -----------------------------------------------
st.subheader("3. Run deterministic analysis")
st.caption(
    "Runs the canonical analysis spine over the committed evidence and stores the "
    "result inside the case. The same result feeds Summary, Timeline, Ask LogSense, "
    "and Export — no JSON files to manage."
)
artifact_count = len(evidence_inventory(workspace_root, case_id))
if artifact_count == 0:
    st.info("Commit at least one evidence file before running analysis.")
else:
    st.write(f"{artifact_count} committed artifact(s) ready.")
    if st.button("Run deterministic analysis", type="primary"):
        with st.spinner("Analyzing committed evidence deterministically..."):
            try:
                shared.run_case_analysis(case_id)
            except Exception as exc:
                st.error(shared.intake_error_text(exc))
            else:
                st.success("Analysis complete — results are attached to this case.")
                st.page_link("pages/investigation_summary.py", label="Open Investigation Summary")
if shared.case_results(case_id):
    st.caption("An analysis already exists for this case. Re-running replaces it.")
