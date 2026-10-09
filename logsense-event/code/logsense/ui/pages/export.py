"""Export — surface what the deterministic engine already produced.

One download per canonical artifact, plus a single ZIP bundle for handoff.
Everything exported is deterministic LogSense output; no AI content and no
secrets are ever included.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from logsense.competition.event_pack import (
    render_control7_html,
    render_control9_html,
    render_control16_html,
    render_gap_register_html,
    render_run_register_html,
)
from logsense.ui import shared

st.title("Export")
st.caption(
    "Deterministic outputs only — analysis, report, manifest, and open gaps. "
    "API keys, model names, and AI answers are never included."
)

shared.render_case_sidebar()
case_id = shared.ensure_case()
payloads = shared.case_export_payloads(case_id)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


if not payloads["analysis"]:
    st.warning(
        "No analysis has been run for this case yet — export will contain the "
        "manifest and inventory only. Run deterministic analysis first for a "
        "complete bundle."
    )
    st.page_link("pages/case_evidence.py", label="Go to Case & Evidence")

st.subheader("Individual outputs")
col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "Deterministic analysis JSON",
        data=_json_bytes(payloads["analysis"]),
        file_name=f"{case_id}-analysis.json",
        mime="application/json",
        disabled=not payloads["analysis"],
    )
    st.download_button(
        "Evidence manifest / inventory",
        data=_json_bytes(payloads["manifest"]),
        file_name=f"{case_id}-manifest.json",
        mime="application/json",
        disabled=not payloads["manifest"]["artifacts"],
    )
with col2:
    st.download_button(
        "Deterministic forensic report JSON",
        data=_json_bytes(payloads["report"]),
        file_name=f"{case_id}-report.json",
        mime="application/json",
        disabled=not payloads["report"],
    )
    st.download_button(
        "Open gaps / frontier list",
        data=_json_bytes(payloads["gaps"]),
        file_name=f"{case_id}-gaps.json",
        mime="application/json",
        disabled=not (payloads["gaps"]["gaps"] or payloads["gaps"]["evidenceFrontier"]),
    )

if payloads.get("control-7-event-recording"):
    st.subheader("Competition measurement")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.download_button(
            "Control 7 event recording measurement",
            data=_json_bytes(payloads["control-7-event-recording"]),
            file_name=f"{case_id}-control-7-event-recording.json",
            mime="application/json",
        )
    with cc2:
        st.download_button(
            "Competition evidence bundle",
            data=_json_bytes(payloads["competition-evidence-bundle"]),
            file_name=f"{case_id}-competition-evidence-bundle.json",
            mime="application/json",
            disabled=not payloads.get("competition-evidence-bundle"),
        )
    st.caption(
        "Measurement only — LogSense does not emit SATISFIED/NOT SATISFIED; "
        "HAIEC applies the frozen threshold."
    )

st.subheader("Case evidence bundle")
st.caption(
    "One ZIP containing analysis.json, report.json, manifest.json, gaps.json, "
    "and metadata.json — ready to attach to a competition submission or review."
)
st.download_button(
    "Download Case Evidence Bundle",
    data=shared.case_export_bundle(case_id),
    file_name=f"{case_id}-evidence-bundle.zip",
    mime="application/zip",
    type="primary",
)

# Competition registers + Judgment-Day pack — rendered only when the case has
# competition content (runs or measurements). LogSense evidence phase outputs;
# completing them does not claim the competition is complete.
svc = shared.service()
competition_runs = svc.list_competition_runs(case_id)
has_competition = bool(
    competition_runs or payloads.get("competition-evidence-bundle") or payloads.get("control-7-event-recording")
)
if has_competition:
    st.divider()
    st.subheader("Competition evidence — registers and judge views")
    st.caption(
        "LogSense evidence phase outputs. A finished export does not mean the "
        "competition is complete — HAIEC still owns the Control Test result."
    )
    run_reg = svc.competition_run_register(case_id)
    gap_reg = svc.competition_gap_register(case_id)

    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown("**Run register** — roles and measurement states (no verdicts).")
        st.download_button(
            "run-register.json",
            data=_json_bytes(run_reg),
            file_name=f"{case_id}-run-register.json",
            mime="application/json",
        )
        st.download_button(
            "run-register.html",
            data=render_run_register_html(run_reg).encode("utf-8"),
            file_name=f"{case_id}-run-register.html",
            mime="text/html",
        )
    with rc2:
        st.markdown("**Gap register** — every gap, its consequence, next action.")
        st.download_button(
            "gap-register.json",
            data=_json_bytes(gap_reg),
            file_name=f"{case_id}-gap-register.json",
            mime="application/json",
        )
        st.download_button(
            "gap-register.html",
            data=render_gap_register_html(gap_reg).encode("utf-8"),
            file_name=f"{case_id}-gap-register.html",
            mime="text/html",
        )

    st.markdown("**Human-readable control evidence** — opens without LogSense.")
    hc1, hc2, hc3 = st.columns(3)
    active = svc.active_run(case_id)
    active_run_id = str(active.get("runId") or "") or None
    for column, code, loader, renderer, label in (
        (hc1, "control-7", svc.load_control7_measurement, render_control7_html, "C7 event recording"),
        (hc2, "control-9", svc.load_control9_measurement, render_control9_html, "C9 drift & performance"),
        (hc3, "control-16", svc.load_control16_measurement, render_control16_html, "C16 spend cap"),
    ):
        with column:
            measurement = loader(case_id, active_run_id) if active_run_id else None
            st.download_button(
                f"{label}.html",
                data=renderer(measurement or {}).encode("utf-8"),
                file_name=f"{case_id}-{code}.html",
                mime="text/html",
                disabled=not measurement,
            )
            st.download_button(
                f"{label}.json (canonical)",
                data=_json_bytes(measurement or {}),
                file_name=f"{case_id}-{code}.json",
                mime="application/json",
                disabled=not measurement,
            )
            if not measurement:
                st.caption(f"Run {code} measurement first for the active run.")

    st.divider()
    st.subheader("TMF-JUDGE-EVIDENCE-PACK.zip")
    st.caption(
        "One-click portable pack: START-HERE index, package manifest, run and "
        "gap registers, per-run evidence JSON + readable HTML, architecture "
        "template, and any externally supplied HAIEC references. Opens on a "
        "machine without LogSense installed. No secrets, no AI answers, no "
        "verdicts."
    )
    pack_bytes, pack_manifest = svc.judge_evidence_pack(case_id)
    st.download_button(
        "Download TMF-JUDGE-EVIDENCE-PACK.zip",
        data=pack_bytes,
        file_name="TMF-JUDGE-EVIDENCE-PACK.zip",
        mime="application/zip",
        type="primary",
    )
    with st.expander("Pack contents", expanded=False):
        for row in pack_manifest.get("files") or ():
            st.write(
                f"- `{row['path']}` — sha256 `{str(row.get('sha256') or '')[:16]}…`"
            )
