"""Control 16 / ACN-COST-001 — post-run token & retry reconciliation panel.

Operator-facing projection of the deterministic measurement. LogSense reports
``ActualRunTokens`` only — HAIEC owns the frozen cap and the final verdict.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from logsense.competition.fixture_packs import fixture_names, list_fixtures
from logsense.competition.guidance import HAIEC_EVENT_FOOTNOTE
from logsense.competition.run import CompetitionRunError
from logsense.integrations.service import IntegrationRequestError
from logsense.ui import shared
from logsense.workspace.cases import CaseWorkspaceError

_C16_FIXTURES = {m["fixtureId"]: m for m in list_fixtures() if m.get("control") == "ACN-COST-001"}


def _fmt_tokens(value: Any) -> str:
    return f"{int(value):,}" if isinstance(value, int) else "—"


def _render_measurement(measurement: dict[str, Any]) -> None:
    state = str(measurement.get("measurementState") or "NOT_MEASURED")
    st.markdown(f"**Measurement: `{state}`**")
    if state == "MEASURED":
        st.metric("Actual Run Tokens", _fmt_tokens(measurement.get("actualRunTokens")))
    else:
        st.metric("Actual Run Tokens", "Not fully established")
        if state == "PARTIAL":
            st.caption(
                f"Known qualified subtotal: "
                f"{_fmt_tokens(measurement.get('knownQualifiedTokens'))} — "
                "a partial subtotal is never presented as ActualRunTokens."
            )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Input tokens", _fmt_tokens(measurement.get("totalInputTokens")))
    c2.metric("Output tokens", _fmt_tokens(measurement.get("totalOutputTokens")))
    c3.metric("Executed calls", measurement.get("providerExecutedCalls", 0))
    c4.metric("Explicit retries", measurement.get("retryExecutions", 0))
    d1, d2, d3 = st.columns(3)
    d1.metric(
        "Duplicate telemetry suppressed", measurement.get("duplicateTelemetryRecordsSuppressed", 0)
    )
    d2.metric(
        "Pending / unknown",
        f"{measurement.get('pendingCalls', 0)} / {measurement.get('unknownExecutionCalls', 0)}",
    )
    d3.metric("Denied before execution", measurement.get("deniedBeforeExecutionCalls", 0))

    if measurement.get("expectedAgents"):
        block = measurement["expectedAgents"]
        missing = block.get("missingExpectedAgents") or []
        label = ", ".join(block.get("expectedAgents") or ()) or "—"
        st.caption(
            f"Expected agents: {label} · observed: "
            f"{', '.join(block.get('observedAgents') or ()) or '—'}"
            + (f" · **missing evidence for: {', '.join(missing)}**" if missing else "")
        )
    elif measurement.get("participatingAgents"):
        st.caption(
            "Participating agents: "
            + ", ".join(measurement["participatingAgents"])
            + " (no expected-agent set declared)"
        )

    rows = measurement.get("perAgentBreakdown") or []
    if rows:
        st.markdown("**Per-agent breakdown**")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    limitations = measurement.get("limitations") or []
    if limitations:
        with st.expander("Limitations", expanded=state != "MEASURED"):
            for item in limitations:
                st.write(f"- `{item}`")


def _render_drilldown(measurement: dict[str, Any]) -> None:
    records = measurement.get("usageRecords") or []
    if not records:
        return
    st.markdown("**Per-call drilldown**")
    groups = {
        "Qualified counted calls": [r for r in records if r.get("contributesToActual")],
        "Denied before execution": [
            r for r in records if r.get("executionState") == "DENIED_BEFORE_EXECUTION"
        ],
        "Failed before execution": [
            r for r in records if r.get("executionState") == "FAILED_BEFORE_EXECUTION"
        ],
        "Pending / unresolved": [
            r for r in records if r.get("executionState") in {"DISPATCHED_PENDING", "UNKNOWN"}
        ],
        "Executed — usage not qualified": [
            r
            for r in records
            if r.get("executionState") == "PROVIDER_EXECUTED" and not r.get("contributesToActual")
        ],
    }

    def _row(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "Agent": r.get("agentId") or "—",
            "Model Call ID": r.get("modelCallId") or "—",
            "Provider Request ID": r.get("providerRequestId") or "—",
            "Attempt": r.get("attemptNumber") or "—",
            "Execution State": r.get("executionState"),
            "Input": r.get("inputTokens"),
            "Output": r.get("outputTokens"),
            "Total": (
                r["inputTokens"] + r["outputTokens"]
                if isinstance(r.get("inputTokens"), int) and isinstance(r.get("outputTokens"), int)
                else "—"
            ),
            "Qualification": r.get("usageQualification"),
            "Source": r.get("sourceEventRef"),
        }

    for label, rows in groups.items():
        if not rows:
            continue
        with st.expander(f"{label} ({len(rows)})", expanded=label != "Qualified counted calls"):
            st.dataframe([_row(r) for r in rows], use_container_width=True, hide_index=True)
            for r in rows:
                if len(r.get("sourceEventRefs") or ()) > 1:
                    st.caption(
                        f"Duplicate telemetry for `{r.get('modelCallId') or r.get('providerRequestId')}`: "
                        + ", ".join(r["sourceEventRefs"])
                    )
                if r.get("rawTokenFields"):
                    st.caption(
                        "Raw provider token fields preserved (not scored): "
                        + ", ".join(f"{k}={v}" for k, v in sorted(r["rawTokenFields"].items()))
                    )

    excluded = measurement.get("excludedEvidence") or {}
    ambiguous = excluded.get("ambiguousRunRefs") or []
    unresolved = excluded.get("unresolvedRunRefs") or []
    if ambiguous or unresolved:
        with st.expander("Ambiguous / unresolved run membership", expanded=True):
            for ref in ambiguous:
                st.write(f"- `{ref}` — ambiguous (could belong to another run)")
            for ref in unresolved:
                st.write(f"- `{ref}` — unresolved membership")


def render_control16_panel(case_id: str) -> None:
    """Functional Control 16 operator flow: active run → reconcile → drilldown
    → HAIEC handoff note."""
    svc = shared.service()

    st.markdown("#### Control 16 — Per-Run Token Usage")
    st.caption(
        "Reconcile actual provider token usage for the active run: every "
        "provider-executed model call counts, every genuine retry counts "
        "again, duplicate telemetry counts once. LogSense measures — HAIEC "
        "owns the cap and the final result."
    )

    if _C16_FIXTURES:
        with st.expander("Optional: load a built-in Control 16 fixture", expanded=False):
            pick = st.selectbox(
                "Fixture",
                [n for n in fixture_names() if n in _C16_FIXTURES],
                format_func=lambda name: f"{name} — {_C16_FIXTURES[name]['label']}",
                key="c16_fixture_pick",
            )
            st.caption(_C16_FIXTURES[pick]["description"])
            if st.button("Load fixture into this case", key="c16_fixture_load"):
                try:
                    with st.spinner("Importing fixture evidence, resolving run, reconciling…"):
                        output = svc.import_competition_fixture(case_id=case_id, fixture_name=pick)
                except (IntegrationRequestError, CaseWorkspaceError, CompetitionRunError) as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        f"Fixture loaded — run `{output['run']['runId']}` "
                        f"({output['run']['resolutionState']}), "
                        f"measurement `{output['measurement']['measurementState']}`."
                    )
                    st.rerun()

    active = svc.active_run(case_id)
    run_id = str(active.get("runId") or "")
    st.markdown("**1 — Active run**")
    if not run_id:
        st.info("No active run — confirm one on the Runs step first.")
        return
    st.write(f"`{run_id}` — {active.get('runRole') or 'no role'}")

    st.markdown("**2 — Reconcile usage**")
    expected_raw = st.text_input(
        "Expected agent IDs (optional, comma-separated measurement completeness context)",
        key="c16_expected_agents",
    )
    expected_ids = [a.strip() for a in expected_raw.split(",") if a.strip()] or None
    if st.button("Run Control 16 reconciliation", type="primary", key="c16_measure"):
        try:
            output = svc.run_control16_measurement(
                case_id=case_id, run_id=run_id, expected_agent_ids=expected_ids
            )
        except (IntegrationRequestError, CaseWorkspaceError, CompetitionRunError) as exc:
            st.error(str(exc))
        else:
            st.session_state["c16_last_measurement"] = output["measurement"]
            st.rerun()

    measurement = svc.load_control16_measurement(case_id, run_id)
    if measurement is None:
        st.info("No Control 16 reconciliation yet for this run.")
        return
    if measurement.get("activeSnapshotRef") != svc.analysis_snapshot_state(case_id).get(
        "snapshotId"
    ):
        st.warning(
            "This measurement was produced against a prior analysis snapshot — "
            "it is preserved history, not current truth. Reconcile again."
        )
    _render_measurement(measurement)
    _render_drilldown(measurement)

    st.markdown("**3 — Handoff**")
    st.caption(HAIEC_EVENT_FOOTNOTE)
    if measurement.get("measurementState") == "MEASURED":
        st.markdown("**MEASUREMENT READY**")
        st.info(
            "Export the Competition Evidence Bundle and evaluate ACN-COST-001 "
            "against the frozen HAIEC token-cap policy. LogSense never emits "
            "the verdict."
        )
    else:
        blockers = measurement.get("limitations") or []
        st.warning(
            "Handoff not ready — measurement is "
            f"`{measurement.get('measurementState')}`. Blocking evidence gaps: "
            + (", ".join(str(b) for b in blockers[:4]) if blockers else "none recorded")
        )
    bundle = svc.load_competition_bundle(case_id, run_id)
    if bundle:
        st.download_button(
            "Download Competition Evidence Bundle",
            data=(json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            file_name=f"{case_id}-{run_id}-competition-evidence-bundle.json",
            mime="application/json",
            key="c16_dl_bundle",
        )

    st.markdown("**What this measures**")
    st.caption(
        "A retry that reached the provider counts again. Duplicate telemetry "
        "for the same provider execution counts once. Missing usage is not "
        "zero usage. A timeout after dispatch may still incur provider usage. "
        "A denied request counts zero only when evidence establishes the "
        "provider did not execute it. LogSense measures actual usage; HAIEC "
        "owns the frozen cap and final result."
    )
