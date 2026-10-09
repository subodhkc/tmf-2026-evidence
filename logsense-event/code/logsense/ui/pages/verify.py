from __future__ import annotations

import hashlib
import json
from typing import Any

import streamlit as st

from logsense.analysis.spine import ArtifactEvidence
from logsense.forensics.verification import VerificationContractError, build_forensic_test
from logsense.forensics.verification_workflow import (
    finalize_frontier_verification,
    prepare_frontier_verification,
)
from logsense.presentation.verification import (
    verification_closure_view,
    verification_preparation_view,
)
from logsense.ui import shared

st.title("Verification Loop")
st.caption(
    "Analyze new evidence into a fresh snapshot first. Frontier closure is a separate bounded step. "
    + shared.GLOSSARY["Evidence frontier"]
)

shared.render_case_sidebar()
_case_results = shared.case_results()
_prior_analysis_default = (_case_results or {}).get("analysis")
_report_default = (_case_results or {}).get("report")
if _prior_analysis_default:
    st.caption(
        f"Active case `{shared.active_case_id()}` supplies the prior analysis automatically."
    )


def _load_json(upload: Any, label: str) -> dict[str, Any] | None:
    if upload is None:
        return None
    try:
        value = json.loads(upload.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        st.error(f"Invalid {label} JSON: {exc}")
        return None
    if not isinstance(value, dict):
        st.error(f"{label} must contain one JSON object.")
        return None
    return value


def _artifact(upload: Any, ingested_at: str) -> ArtifactEvidence:
    content = upload.getvalue()
    name = str(upload.name)
    digest = hashlib.sha256(name.encode("utf-8") + b"\0" + content).hexdigest()
    return ArtifactEvidence(
        artifact_id=f"verification:artifact:{digest[:24]}",
        path=name,
        content=content,
        ingested_at=ingested_at,
        media_type=getattr(upload, "type", None) or None,
    )


left, right = st.columns(2)
with left:
    prior_analysis_upload = st.file_uploader(
        "Prior deterministic analysis JSON", type=["json"], key="verify_prior_analysis"
    )
with right:
    report_upload = st.file_uploader(
        "Deterministic report JSON with evidence frontier", type=["json"], key="verify_report"
    )

prior_analysis = _load_json(prior_analysis_upload, "analysis") or _prior_analysis_default
report = _load_json(report_upload, "report") or _report_default
prior_snapshot = (prior_analysis or {}).get("snapshot") or {}
frontiers = list(
    (report or {}).get("evidenceFrontier") or (prior_analysis or {}).get("evidenceFrontier") or ()
)

if not prior_snapshot:
    st.info(
        "Load prior deterministic analysis JSON containing its immutable snapshot to execute verification."
    )
if not frontiers:
    st.info("Load a report or analysis containing at least one evidence-frontier item.")

selected_frontier: dict[str, Any] | None = None
if frontiers:
    frontier_by_id = {
        str(item.get("frontierId")): item for item in frontiers if item.get("frontierId")
    }
    selected_id = st.selectbox("Frontier item", sorted(frontier_by_id))
    selected_frontier = frontier_by_id[selected_id]
    st.write("Missing fact:", selected_frontier.get("missingFact") or "Unknown")
    st.write("Why needed:", selected_frontier.get("whyNeeded") or "")
    st.write("Verification requirement:", selected_frontier.get("verificationRequirement") or "")
    st.write("Subjects:", selected_frontier.get("subjectRefs") or [])
    st.caption("Frontier item != finding. Closing a frontier does not establish root cause.")

st.divider()
st.subheader("1. Prepare new evidence snapshot")
verification_uploads = st.file_uploader(
    "Verification artifacts",
    accept_multiple_files=True,
    key="verification_artifacts",
    help="These artifacts are analyzed deterministically into a new EvidenceSet and InvestigationSnapshot.",
)
case_id = str(prior_snapshot.get("caseId") or (prior_analysis or {}).get("caseId") or "")
default_set = f"{case_id}:verification" if case_id else "verification:evidence-set"
default_run = f"{case_id}:verification:run" if case_id else "verification:run"
evidence_set_id = st.text_input("New EvidenceSet ID", value=default_set)
analysis_run_id = st.text_input("New analysis run ID", value=default_run)
created_at = st.text_input("Verification timestamp (ISO-8601)", placeholder="2026-09-30T04:30:00Z")

if st.button(
    "Analyze verification evidence",
    type="primary",
    disabled=not (prior_snapshot and selected_frontier and verification_uploads and created_at),
):
    artifacts = [_artifact(upload, created_at) for upload in verification_uploads]
    try:
        prepared: dict[str, Any] | None = prepare_frontier_verification(
            prior_snapshot=prior_snapshot,
            verification_artifacts=artifacts,
            evidence_set_id=evidence_set_id,
            analysis_run_id=analysis_run_id,
            created_at=created_at,
        )
    except (VerificationContractError, ValueError) as exc:
        st.error(str(exc))
    else:
        st.session_state["prepared_frontier_verification"] = prepared
        st.session_state["prepared_frontier_id"] = (selected_frontier or {}).get("frontierId")
        st.success(
            "New immutable verification snapshot prepared. No frontier state has been changed."
        )

prepared = st.session_state.get("prepared_frontier_verification")
prepared_frontier_id = st.session_state.get("prepared_frontier_id")
if prepared:
    prep_view = verification_preparation_view(prepared)
    a, b = st.columns(2)
    a.write(f"Prior snapshot: `{prep_view['priorSnapshotRef']}`")
    b.write(f"New snapshot: `{prep_view['newSnapshotRef']}`")
    st.write("Dataset digest:", prep_view["datasetDigest"])
    st.write(
        "Verification-eligible evidence refs:",
        prep_view["availableEvidenceRefs"] or ["None emitted"],
    )
    if prep_view["refDeltas"]:
        with st.expander("Before / after reference delta"):
            st.json(prep_view["refDeltas"])
    st.caption(
        "Removed from the observed set does not prove absence. Snapshot delta does not establish root cause."
    )

st.divider()
st.subheader("2. Finalize bounded ForensicTest")
if not prepared:
    st.info("Prepare verification evidence before finalizing a test.")
elif selected_frontier and prepared_frontier_id != selected_frontier.get("frontierId"):
    st.warning(
        "The prepared evidence belongs to a different frontier selection. Prepare again for this frontier before finalizing."
    )
else:
    subjects = [str(x) for x in (selected_frontier or {}).get("subjectRefs", ()) if str(x)]
    if not subjects:
        st.error(
            "Selected frontier has no bounded subject scope; verification cannot be finalized."
        )
    else:
        target = st.selectbox("Verification target", subjects)
        proposed = str((selected_frontier or {}).get("proposedTestRef") or "")
        test_id = st.text_input("ForensicTest ID", value=proposed or f"{prepared_frontier_id}:test")
        result = st.selectbox("Test result", ["INCONCLUSIVE", "PASS", "FAIL"])
        available_refs = list(prepared.get("availableEvidenceRefs") or ())
        evidence_refs = st.multiselect("Evidence refs from the new analysis", available_refs)
        closure_options = (
            ["TEST_RESULT", "DOCUMENTED_NON_EXECUTION"] if result == "PASS" else ["TEST_RESULT"]
        )
        closure_basis = st.selectbox("Closure basis", closure_options)
        predicate_text = ""
        if closure_basis == "DOCUMENTED_NON_EXECUTION":
            predicate_text = st.text_input(
                "Exact non-execution predicate", placeholder="Exact bounded action did not execute"
            )
            st.caption(
                "Documented non-execution is bounded to this predicate and does not establish capability absence."
            )
        closure_reason = st.text_input("Closure reason (optional)")
        finalize_time = st.text_input(
            "Closure timestamp (ISO-8601)", value=created_at, key="verification_closed_at"
        )

        if st.button("Finalize verification", disabled=not finalize_time):
            predicate = (
                {"verificationTarget": target, "predicate": predicate_text}
                if closure_basis == "DOCUMENTED_NON_EXECUTION" and predicate_text
                else None
            )
            try:
                forensic_test = build_forensic_test(
                    test_id=test_id,
                    title=str(
                        (selected_frontier or {}).get("missingFact") or "Frontier verification"
                    ),
                    hypothesis=str(
                        (selected_frontier or {}).get("verificationRequirement")
                        or "Bounded verification requirement"
                    ),
                    expected_behavior=str(
                        (selected_frontier or {}).get("verificationRequirement")
                        or "Bounded expected behavior"
                    ),
                    verification_target=target,
                    result=result,
                    required_evidence=(
                        str(
                            (selected_frontier or {}).get("verificationRequirement")
                            or "qualified evidence"
                        ),
                    ),
                    evidence_refs=tuple(evidence_refs),
                    predicate_scope=predicate,
                )
                finalized: dict[str, Any] | None = finalize_frontier_verification(
                    prepared,
                    frontier=selected_frontier or {},
                    forensic_test=forensic_test,
                    closed_at=finalize_time,
                    closure_basis=closure_basis,
                    closure_reason=closure_reason or None,
                    documented_non_execution_predicate=predicate,
                )
            except (VerificationContractError, ValueError) as exc:
                st.error(str(exc))
            else:
                st.session_state["finalized_frontier_verification"] = finalized
                st.success("Verification finalized against the new snapshot.")

finalized = st.session_state.get("finalized_frontier_verification")
if finalized:
    view = verification_closure_view(finalized)
    st.markdown("#### Verification result")
    st.write("Closure state:", view["closureState"]["label"])
    st.write("Reason:", view["closureReason"] or "")
    st.write("Evidence refs:", view["evidenceRefs"])
    st.write("Prior snapshot:", view["priorSnapshotRef"])
    st.write("New snapshot:", view["newSnapshotRef"])
    st.write("Root cause claimed:", view["rootCauseClaimed"])
    st.write("Capability absence claimed:", view["capabilityAbsentClaimed"])
    if view["semanticLimitations"]:
        st.write("Semantic limits:", view["semanticLimitations"])
    if view["refDeltas"]:
        with st.expander("Snapshot comparison"):
            st.json(view["refDeltas"])
