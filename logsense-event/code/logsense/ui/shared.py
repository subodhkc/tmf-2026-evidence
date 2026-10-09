"""Shared session helpers for the LogSense workbench pages.

Every page funnels through the same canonical owners:

- cases/evidence live in the user-local workspace (``LOGSENSE_WORKSPACE``);
- deterministic analysis runs through ``IntegrationService.analyze_case``;
- results persist in the case workspace and follow the active case across
  pages — operators never upload internal analysis/report JSON;
- AI providers are chosen per installation and never see anything except
  tool-derived deterministic projections.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from logsense.ai.provider import (
    PROVIDER_LABELS,
    PROVIDER_NAMES,
    provider_key_env,
    provider_model_env,
)
from logsense.integrations.service import IntegrationRequestError, IntegrationService
from logsense.pipeline.intake import EvidenceIntakeError
from logsense.user_config import (
    provider_key_source,
    resolve_ai_provider,
    resolve_workspace_root,
    save_ai_provider,
    save_secret,
    secrets_path,
)
from logsense.workspace.cases import (
    CaseExistsError,
    CaseWorkspaceError,
    create_case,
    evidence_inventory,
    list_cases,
    list_manifests,
    load_case,
)

SAMPLE_CASE_ID = "sample-gfb-001"

SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "What happened?",
    "What is the strongest evidence?",
    "What changed first?",
    "What is established versus still unproven?",
    "What evidence is missing?",
    "What should we collect next?",
    "Show me the first qualified divergence.",
    "Are there contradictions between sources?",
    "Which parts of this incident are relevant to Controls 7, 9 or 16?",
    "Which expected event is missing from the competition run?",
    "Why is the Control 7 coverage not 100%?",
    "Which timing gap violated the declared limit?",
)

GLOSSARY: dict[str, str] = {
    "Evidence": "Raw or normalized records LogSense can trace back to the source.",
    "Established": "Supported by the available evidence at this scope.",
    "Not assessed": "LogSense does not currently have enough evidence to make this determination.",
    "Contradiction": "Two qualified sources disagree. This does not automatically prove tampering.",
    "First divergence": (
        "The earliest qualified difference we can establish. It is not automatically root cause."
    ),
    "Evidence frontier": (
        "The next missing fact needed to resolve an open question. A frontier is not a finding."
    ),
    "Source qualification": "Whether a source is suitable to support this specific claim.",
    "Deterministic": (
        "Computed by the LogSense engine from evidence only — no AI involved, reproducible."
    ),
}


def workspace_root() -> Path:
    return resolve_workspace_root()


def service() -> IntegrationService:
    return IntegrationService(workspace_root=workspace_root())


def active_case_id() -> str:
    return str(st.session_state.get("case_id") or "")


def set_active_case(case_id: str) -> None:
    st.session_state["case_id"] = case_id


# ---- resume state (R5-03) ------------------------------------------------------
# Persisted under the workspace so a competition investigation survives an app
# restart. Local convenience state only — never a forensic truth source.


def _ui_state_path() -> Path:
    return workspace_root() / "ui-state.json"


def load_ui_state() -> dict[str, Any]:
    path = _ui_state_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_ui_state(**fields: Any) -> None:
    state = load_ui_state()
    state.update(fields)
    state["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = _ui_state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def note_competition_state(case_id: str, step: int) -> None:
    """Record the last competition case/step so a restart can resume it."""
    if not case_id:
        return
    save_ui_state(lastCompetitionCaseId=case_id, competitionStep=int(step))


def competition_resume() -> dict[str, Any] | None:
    """Resume target for a prior competition investigation, if it still exists."""
    state = load_ui_state()
    case_id = str(state.get("lastCompetitionCaseId") or "")
    if not case_id or case_id not in list_case_ids():
        return None
    return {
        "caseId": case_id,
        "competitionStep": int(state.get("competitionStep") or 0),
        "updatedAt": state.get("updatedAt"),
    }


def checkpoint_export(case_id: str) -> bytes:
    """JSON bytes of the lightweight competition checkpoint (identities only)."""
    payload = service().export_checkpoint(case_id)
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def list_case_ids() -> list[str]:
    return [row.case_id for row in list_cases(workspace_root())]


def case_results(case_id: str | None = None) -> dict[str, Any] | None:
    """Load the active case's persisted deterministic outputs, if any."""
    cid = case_id or active_case_id()
    if not cid:
        return None
    try:
        return service().load_case_results(cid)
    except (CaseWorkspaceError, KeyError, ValueError):
        return None


def run_case_analysis(case_id: str | None = None) -> dict[str, Any]:
    """Run canonical deterministic analysis over the case's committed evidence."""
    cid = case_id or active_case_id()
    if not cid:
        raise CaseWorkspaceError("no active case")
    return service().analyze_case(case_id=cid)


def commit_uploads_to_case(case_id: str, uploads: list[Any]) -> dict[str, Any]:
    """Commit uploaded files through the same canonical intake the API uses."""
    files = [
        {
            "name": str(upload.name),
            "contentBase64": base64.b64encode(upload.getvalue()).decode("ascii"),
        }
        for upload in uploads
    ]
    return service().import_evidence({"caseId": case_id, "files": files})


def commit_paths_to_case(case_id: str, paths: list[Path]) -> dict[str, Any]:
    """Commit local file paths through the canonical preview/commit pipeline."""
    files = [
        {"name": path.name, "contentBase64": base64.b64encode(path.read_bytes()).decode("ascii")}
        for path in paths
    ]
    return service().import_evidence({"caseId": case_id, "files": files})


def ensure_case() -> str:
    """Return the active case ID or stop the page with guidance."""
    cid = active_case_id()
    if cid:
        return cid
    st.warning("No case is open. Create or open a case first.")
    st.page_link("pages/case_evidence.py", label="Go to Case & Evidence")
    st.stop()
    raise AssertionError("unreachable")  # st.stop() halts the script


def ensure_results() -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Return (case_id, analysis, report) for the active case, or guide the user."""
    cid = ensure_case()
    results = case_results(cid)
    if results is None:
        st.info(
            "This case has no analysis yet. Add evidence on the **Case & Evidence** "
            "page, then press **Run deterministic analysis**."
        )
        st.page_link("pages/case_evidence.py", label="Go to Case & Evidence")
        st.stop()
        raise AssertionError("unreachable")  # st.stop() halts the script
    return cid, dict(results["analysis"]), results.get("report")


def render_case_sidebar() -> None:
    """Compact case picker shown in the sidebar of every workbench page."""
    with st.sidebar:
        st.markdown("#### Case")
        ids = list_case_ids()
        options = [""] + ids
        current = active_case_id()
        index = options.index(current) if current in options else 0
        picked = st.selectbox(
            "Active case",
            options,
            index=index,
            format_func=lambda value: value or "— select or create —",
            label_visibility="collapsed",
        )
        if picked and picked != current:
            set_active_case(picked)
        st.caption(f"Workspace: `{workspace_root()}`")
        cid = active_case_id()
        if cid:
            artifacts = evidence_inventory(workspace_root(), cid)
            has_results = case_results(cid) is not None
            st.caption(
                f"{len(artifacts)} committed artifact(s) · "
                + ("analysis available" if has_results else "not analyzed yet")
            )
        st.caption("AI: " + ai_status_line())


def ai_status_line() -> str:
    provider = resolve_ai_provider()
    source = provider_key_source(provider)
    label = PROVIDER_LABELS.get(provider, provider)
    return f"{label} ({'configured' if source else 'no key'})"


def render_ai_configuration(*, show_model: bool = True) -> None:
    """Provider picker + masked key entry shared by Start Here / Ask / setup.

    Keys land in the process environment and — only on explicit opt-in — the
    user-local secrets file. They are never written to cases, reports, or
    exports and never displayed.
    """
    provider = resolve_ai_provider()
    labels = [PROVIDER_LABELS[name] for name in PROVIDER_NAMES]
    chosen_label = st.radio(
        "AI investigator",
        labels,
        index=PROVIDER_NAMES.index(provider) if provider in PROVIDER_NAMES else 0,
        horizontal=True,
        help="AI explains and investigates deterministic evidence; it cannot change forensic truth.",
    )
    provider = PROVIDER_NAMES[labels.index(chosen_label)]
    if provider != resolve_ai_provider():
        save_ai_provider(provider)
        os.environ["LOGSENSE_AI_PROVIDER"] = provider

    key_env = provider_key_env(provider)
    source = provider_key_source(provider)
    if source:
        st.success(f"{chosen_label} key configured — stored in {source}.")
    else:
        key = st.text_input(
            f"{chosen_label} API key",
            type="password",
            key=f"key_input_{provider}",
            help="Stored only in this session unless you opt to remember it.",
        )
        remember = st.checkbox("Remember on this device", key=f"remember_{provider}", value=False)
        if key:
            os.environ[key_env] = key
            if remember:
                save_secret(key_env, key)
                save_secret("LOGSENSE_AI_PROVIDER", provider)
                st.caption(f"Saved to {secrets_path()} — outside the repo and outside evidence.")
            st.rerun()
    if show_model:
        model_env = provider_model_env(provider)
        model = st.text_input(
            "Model (optional)",
            value=os.getenv(model_env, ""),
            key=f"model_input_{provider}",
            help="Leave blank to use the provider default.",
        )
        if model:
            os.environ[model_env] = model


def create_provider_from_ui() -> Any:
    """Build the configured investigator provider for the active session."""
    from logsense.ai.provider import create_provider

    return create_provider(resolve_ai_provider())


def provider_unavailable_message(exc: Exception) -> str:
    return str(exc)


def run_sample_investigation() -> str:
    """Create/load the bundled Golden sample case, commit evidence, analyze.

    Idempotent: reuses the existing sample case and re-runs analysis only if
    results are missing.
    """
    from logsense.samples import SAMPLE_FILES, sample_dir

    root = workspace_root()
    cid = SAMPLE_CASE_ID
    if cid not in list_case_ids():
        with contextlib.suppress(CaseExistsError):
            create_case(root, case_id=cid, title="Sample investigation — GFB-001")
    set_active_case(cid)
    if not evidence_inventory(root, cid):
        files = [
            {
                "name": name,
                "contentBase64": base64.b64encode((sample_dir() / name).read_bytes()).decode(
                    "ascii"
                ),
            }
            for name in SAMPLE_FILES
        ]
        service().import_evidence({"caseId": cid, "files": files})
    if case_results(cid) is None:
        service().analyze_case(case_id=cid)
    return cid


def parse_json_upload(upload: Any, label: str) -> dict[str, Any] | None:
    """JSON upload override used by Advanced pages (never required)."""
    if upload is None:
        return None
    import json

    try:
        value = json.loads(upload.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        st.error(f"Invalid {label} JSON: {exc}")
        return None
    if not isinstance(value, dict):
        st.error(f"Expected one {label} JSON object.")
        return None
    return value


def analysis_with_override(key: str) -> dict[str, Any] | None:
    """Active-case analysis, with an Advanced-only manual JSON override."""
    with st.expander("Override: load analysis JSON manually", expanded=False):
        upload = st.file_uploader("Analysis JSON", type=["json"], key=key)
    override = parse_json_upload(upload, "analysis")
    if override is not None:
        return override
    cid, analysis, _report = ensure_results()
    _ = cid
    return analysis


def report_with_override(key: str) -> dict[str, Any] | None:
    with st.expander("Override: load report JSON manually", expanded=False):
        upload = st.file_uploader("Report JSON", type=["json"], key=key)
    override = parse_json_upload(upload, "report")
    if override is not None:
        return override
    _cid, _analysis, report = ensure_results()
    return report


def ask_question(
    question: str,
    analysis: dict,
    report: dict,
    competition: dict | None = None,
) -> dict:
    """Run one provider-agnostic investigator turn over deterministic outputs."""
    from typing import cast

    from logsense.ai.session import InvestigatorSession
    from logsense.ai.tools import InvestigatorToolbox
    from logsense.presentation.ask_logsense import investigator_turn_view

    toolbox = InvestigatorToolbox(analysis=analysis, report=report, competition=competition)
    session = InvestigatorSession(provider=create_provider_from_ui(), toolbox=toolbox)
    return cast(dict, investigator_turn_view(session.ask(question)))


def competition_payload(case_id: str | None = None) -> dict | None:
    """Deterministic competition surface for the investigator toolbox, if any."""
    cid = case_id or active_case_id()
    if not cid:
        return None
    try:
        payload = service().competition_tool_payload(cid)
    except (CaseWorkspaceError, IntegrationRequestError):
        return None
    has_competition_content = any(
        payload.get(key)
        for key in (
            "competitionRuns",
            "control7Measurements",
            "control9Measurements",
            "control16Measurements",
            "competitionBundle",
            "importedHaiecProofs",
        )
    )
    if not has_competition_content:
        return None
    return payload


def case_export_payloads(case_id: str) -> dict[str, Any]:
    """Collect the deterministic export payloads for one case."""
    root = workspace_root()
    results = case_results(case_id) or {}
    analysis: dict[str, Any] = results.get("analysis") or {}
    report: dict[str, Any] = results.get("report") or {}
    inventory = [dict(row) for row in evidence_inventory(root, case_id)]
    manifests = [dict(row) for row in list_manifests(root, case_id)]
    record = load_case(root, case_id)
    gaps = {
        "caseId": case_id,
        "gaps": analysis.get("gaps") or [],
        "evidenceFrontier": report.get("evidenceFrontier")
        or analysis.get("evidenceFrontier")
        or [],
        "contradictions": report.get("evidenceContradictions")
        or analysis.get("contradictions")
        or [],
    }
    metadata = {
        "caseId": record.case_id,
        "title": record.title,
        "createdAt": record.created_at,
        "truthOwner": "DETERMINISTIC_LOGSENSE_CORE",
        "analysisRunId": (report or analysis).get("analysisRunId"),
        "reportDigest": report.get("reportDigest"),
        "snapshot": (analysis.get("snapshot") or {}).get("snapshotId"),
        "artifactCount": len(inventory),
        "manifestCount": len(manifests),
        "note": "Deterministic LogSense outputs. AI is not a forensic truth owner.",
    }
    payloads: dict[str, Any] = {
        "analysis": analysis,
        "report": report,
        "manifest": {"manifests": manifests, "artifacts": inventory},
        "gaps": gaps,
        "metadata": metadata,
    }
    try:
        svc = service()
        measurement = svc.load_control7_measurement(case_id)
        bundle = svc.load_competition_bundle(case_id)
    except (CaseWorkspaceError, IntegrationRequestError):
        measurement = bundle = None
    if measurement is not None:
        metadata["competitionRunId"] = measurement.get("runId")
        payloads["control-7-event-recording"] = measurement
        if bundle is not None:
            payloads["competition-evidence-bundle"] = bundle
    return payloads


def case_export_bundle(case_id: str) -> bytes:
    """ZIP of the deterministic case outputs — ready to attach to a submission."""
    import io
    import zipfile

    payloads = case_export_payloads(case_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in payloads.items():
            if value:
                archive.writestr(
                    f"{name}.json",
                    (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                )
    return buffer.getvalue()


def intake_error_text(exc: Exception) -> str:
    if isinstance(exc, (EvidenceIntakeError, CaseWorkspaceError, IntegrationRequestError)):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def temp_extracted_paths(uploads: list[Any]) -> tuple[tempfile.TemporaryDirectory[str], list[Path]]:
    """Write uploads to a temp dir for canonical preview (caller owns cleanup)."""
    tmp = tempfile.TemporaryDirectory(prefix="logsense-ui-")
    root = Path(tmp.name)
    paths: list[Path] = []
    used: set[str] = set()
    for index, upload in enumerate(uploads, start=1):
        name = Path(str(upload.name)).name or f"upload-{index}"
        if name in used:
            name = f"{index}-{name}"
        used.add(name)
        target = root / name
        target.write_bytes(upload.getvalue())
        paths.append(target)
    return tmp, paths
