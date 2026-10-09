"""Ask LogSense — AI investigator over the active case's deterministic output.

The active case's analysis/report bind automatically; the operator never
uploads internal JSON. Provider (OpenAI or Claude) and keys are chosen here or
in ``logsense setup``; keys are never shown, logged, or stored in case data.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from logsense.ai.provider import (
    PROVIDER_LABELS,
    InvestigatorBoundaryError,
    provider_key_env,
    provider_model_env,
)
from logsense.ai.session import InvestigatorSession
from logsense.ai.tools import InvestigatorToolbox
from logsense.presentation.ask_logsense import (
    investigator_scope_summary,
    investigator_turn_view,
)
from logsense.ui import shared
from logsense.user_config import provider_key_source, resolve_ai_provider

st.title("Ask LogSense")
st.caption(
    "AI investigator over deterministic LogSense evidence. It can explain and "
    "navigate; it cannot establish, modify, or promote forensic truth. Every "
    "answer is checked against the evidence the model actually retrieved."
)

shared.render_case_sidebar()

# --- provider + key ----------------------------------------------------------------
with st.sidebar:
    st.divider()
    st.markdown("#### AI investigator")
    shared.render_ai_configuration()

provider = resolve_ai_provider()
provider_label = PROVIDER_LABELS.get(provider, provider)
if not provider_key_source(provider):
    st.warning(
        f"No {provider_label} key configured. Add it in the sidebar, switch provider, "
        "or run `logsense setup`."
    )

# --- deterministic scope ----------------------------------------------------------
results = shared.case_results()
analysis: dict = {}
report: dict = {}
if results:
    analysis, report = results["analysis"], results.get("report") or {}
    cid = shared.active_case_id()
    st.caption(f"Bound to active case `{cid}` — analysis `{analysis.get('analysisRunId', 'n/a')}`.")
else:
    st.info(
        "No analyzed case is active. Run analysis on the **Case & Evidence** page "
        "first — or load JSON manually for an ad-hoc question."
    )
    with st.expander("Ad-hoc: load analysis/report JSON", expanded=False):
        up_analysis = st.file_uploader("Analysis JSON", type=["json"], key="ask_override_analysis")
        up_report = st.file_uploader("Report JSON", type=["json"], key="ask_override_report")
        analysis = shared.parse_json_upload(up_analysis, "analysis") or {}
        report = shared.parse_json_upload(up_report, "report") or {}

if not analysis and not report:
    st.stop()

scope = investigator_scope_summary(analysis, report)
left, middle, right = st.columns(3)
left.metric("Forensic claims", scope["claimCount"])
middle.metric("Material stories", scope["storyCount"])
right.metric("Open proof boundaries", scope["openFrontierCount"])
st.write("Evidence set:", scope["evidenceSetId"] or "Not supplied")
st.write(
    "Report digest:", f"`{scope['reportDigest']}`" if scope["reportDigest"] else "Not supplied"
)
st.caption("Canonical mutation allowed: No")

# --- TM FORUM JUDGE CONSOLE ---------------------------------------------------------
from logsense.ai.judge_router import route_judge_question  # noqa: E402
from logsense.competition import haiec_proof, judge_console  # noqa: E402

st.divider()
st.subheader("TM Forum Judge Console")
st.caption(
    "Ask one question. AI may interpret it; LogSense and HAIEC provide the authoritative facts."
)
st.markdown(f"**{judge_console.CENTRAL_PRINCIPLE}**")

_service = shared.service()
_case_id = shared.active_case_id()
competition: dict = shared.competition_payload() or {}
proofs: list[dict] = []
try:
    proofs = _service.imported_haiec_proofs(_case_id) if _case_id else []
except Exception:  # noqa: BLE001 — proof listing is advisory, never blocks the page
    proofs = []
_summary = haiec_proof.imported_proof_summary(proofs)

_comp_runs = competition.get("competitionRuns") or ()
_run_ids = sorted(
    {str(r.get("runId")) for r in _comp_runs if isinstance(r, dict) and r.get("runId")}
)
_active_run = None
try:
    _active_run = str((_service.active_run(_case_id) or {}).get("runId") or "") or None
except Exception:  # noqa: BLE001
    _active_run = None
if _active_run and _active_run not in _run_ids:
    _run_ids.append(_active_run)

pc1, pc2, pc3, pc4 = st.columns(4)
pc1.metric("Active run", _active_run or "—")
pc2.metric("Analysis", str(analysis.get("analysisRunId") or "—")[:12])
pc3.metric("HAIEC proofs", _summary["importedCount"])
pc4.metric("Control results", _summary["validResultCount"])
freeze = (
    "yes — " + ", ".join(_summary["eventFreezeStates"]) if _summary["eventFreezeImported"] else "no"
)
st.caption(
    f"Event Freeze imported: {freeze} · case `{_case_id}` · "
    "imported proof is NOT canonical runtime evidence"
)

with st.expander("Authoritative HAIEC Proof — manual import", expanded=False):
    st.caption(
        "Imported files are persisted with the case as AUTHORITATIVE EXTERNAL "
        "ASSURANCE PROOF SNAPSHOTS (SHA-256 bound). They never enter runtime "
        "evidence, measurements, or deduplication. No network or credentials needed."
    )
    if proofs:
        st.dataframe(
            [
                {
                    "file": p.get("originalFileName"),
                    "sha256": str(p.get("sha256") or "")[:16] + "…",
                    "type": p.get("detectedSourceType"),
                    "importedAt": p.get("importedAt"),
                    "results": len(p.get("results") or ()),
                    "eventFreeze": p.get("eventFreezeState"),
                    "validation": p.get("validationState"),
                }
                for p in proofs
            ],
            use_container_width=True,
        )
        for p in proofs:
            if p.get("validationErrors"):
                st.warning(f"`{p.get('originalFileName')}`: {', '.join(p['validationErrors'])}")
    else:
        st.info("No HAIEC proof imported yet.")
    upload = st.file_uploader(
        "Import HAIEC JSON — Control Test result or Judgment-Day manifest",
        type=["json"],
        key="haiec_proof_upload",
    )
    if upload is not None and st.button("Import HAIEC Proof"):
        record = _service.import_haiec_proof(
            _case_id, file_name=upload.name, content=upload.getvalue()
        )
        if record.get("duplicate"):
            st.info("Exact duplicate — already imported (idempotent, digest unchanged).")
        elif record.get("validationState") == "VALID":
            st.success(f"Imported `{record['originalFileName']}` — {record['detectedSourceType']}.")
        else:
            st.warning(
                f"Imported `{record['originalFileName']}` as {record['validationState']}: "
                + ", ".join(record.get("validationErrors") or [])
            )
        st.rerun()

st.markdown("#### Question")
_sel_col, _ctrl_col = st.columns(2)
_selected_run: str | None = _sel_col.selectbox(
    "Run",
    ["(none)"] + _run_ids,
    index=_run_ids.index(_active_run) + 1 if _active_run in _run_ids else 0,
)
_selected_run = None if _selected_run == "(none)" else _selected_run
_selected_control = _ctrl_col.selectbox("Control", ["(auto)", "C7", "C9", "C16"])
_t1, _t2 = st.columns(2)
_time_from = _t1.text_input(
    "T1 — from (optional)", key="judge_t1", placeholder="2026-10-03T14:32:00Z"
)
_time_to = _t2.text_input("T2 — to (optional)", key="judge_t2", placeholder="2026-10-03T14:35:00Z")

_run_label = _selected_run or "<run>"
_examples = [
    f"What happened in {_run_label} between T1 and T2?",
    f"Was Control 9 satisfied for {_run_label}?",
    f"Show the exact evidence behind Control 16 for {_run_label}.",
    f"What remains unproven for {_run_label}?",
]
_example = st.pills(
    "Guaranteed judge questions", _examples, selection_mode="single", key="judge_pills"
)
_judge_q = st.text_area(
    "Judge question",
    value=_example or "",
    height=90,
    placeholder="What happened in RUN-X between 14:32 and 14:35? — or — Was Control 9 satisfied for RUN-X?",
    key="judge_question",
)


def _judge_history() -> list[dict[str, Any]]:
    history = st.session_state.setdefault("judge_turns", [])
    return history if isinstance(history, list) else []


if st.button("Answer (deterministic)", type="primary", key="judge_ask"):
    question = _judge_q.strip()
    # substitute operator-entered T1/T2 into the placeholder example
    if _time_from.strip():
        question = question.replace("T1", _time_from.strip())
    if _time_to.strip():
        question = question.replace("T2", _time_to.strip())
    if (
        _selected_control != "(auto)"
        and "control" not in question.lower()
        and "c7" not in question.lower()
        and "c9" not in question.lower()
        and "c16" not in question.lower()
    ):
        question = f"{question} — control {_selected_control}"
    routed = route_judge_question(question, known_run_ids=_run_ids, selected_run_id=_selected_run)
    jturn: dict[str, Any] = {"question": question, "routed": routed}
    if routed["routable"]:
        _toolbox = InvestigatorToolbox(analysis=analysis, report=report, competition=competition)
        jturn["answer"] = judge_console.judge_answer(
            routed, toolbox=_toolbox, competition=competition
        )
        jturn["toolAudit"] = _toolbox.audit_results()
    _judge_history().append(jturn)
    st.session_state["judge_last_turn"] = jturn

_last = st.session_state.get("judge_last_turn")
if _last:
    _routed = _last["routed"]
    st.markdown("#### Detected query")
    st.dataframe(
        [
            {
                "route": _routed["route"],
                "runId": _routed.get("runId"),
                "controlId": _routed.get("controlId"),
                "from": _routed.get("fromTime"),
                "to": _routed.get("toTime"),
                "windowRef": _routed.get("windowRef"),
                "routable": _routed["routable"],
                "missing": ", ".join(_routed.get("missing") or ()),
            }
        ],
        use_container_width=True,
    )
    if not _routed["routable"]:
        st.error("QUESTION NOT ROUTABLE DETERMINISTICALLY")
        st.caption(
            "No parameter was guessed. Select a run/control above, or use one of the "
            "four guaranteed example questions. Missing: " + ", ".join(_routed.get("missing") or ())
        )
        st.write("Known runs:", ", ".join(f"`{r}`" for r in _run_ids) or "none")
        st.write("Known controls: `C7` `C9` `C16`")
        st.write("Supported examples:")
        for ex in _examples:
            st.write(f"- {ex}")
        if provider_key_source(provider) and st.button(
            "Interpret with AI investigator instead", key="judge_ai_fallback"
        ):
            _toolbox = InvestigatorToolbox(
                analysis=analysis, report=report, competition=competition
            )
            try:
                _provider_instance = shared.create_provider_from_ui()
            except Exception as exc:  # noqa: BLE001
                st.error(shared.provider_unavailable_message(exc))
            else:
                _session = InvestigatorSession(provider=_provider_instance, toolbox=_toolbox)
                try:
                    _ai_turn = _session.ask(_last["question"])
                except Exception as exc:  # noqa: BLE001
                    st.error(shared.provider_unavailable_message(exc))
                else:
                    st.session_state["ask_logsense_last_turn"] = investigator_turn_view(_ai_turn)
                    _judge_history()[-1]["aiView"] = investigator_turn_view(_ai_turn)
                    st.rerun()
    else:
        _answer = _last["answer"]
        _banner = _answer.get("banner") or {}
        _route = _answer.get("route")
        if _route == "ASSURANCE":
            if _answer.get("state") == "FOUND":
                st.success(f"ANSWER BASIS — {_banner.get('basis')}")
            elif _answer.get("state") == "CONFLICT":
                st.error(f"ANSWER BASIS — {_answer.get('headline')}")
            else:
                st.warning(f"ANSWER BASIS — {_banner.get('basis')}")
        else:
            st.info(f"ANSWER BASIS — {_banner.get('basis')}")
        _bcols = st.columns(max(len(_banner) - 1, 1))
        for col, (k, v) in zip(
            _bcols, [(k, v) for k, v in _banner.items() if k != "basis"], strict=False
        ):
            col.metric(k, str(v))

        _tool = _answer.get("toolResult") or {}
        _payload = _tool.get("payload")
        if _route == "FORENSIC" and isinstance(_payload, dict):
            st.caption(_payload.get("copy", {}).get("banner", ""))
            st.caption(_payload.get("copy", {}).get("ordering", ""))
            st.write(
                f"Window `{_payload.get('from')}` → `{_payload.get('to')}` · "
                f"**{_payload.get('matchedCount', 0)} matching events** · "
                f"{_payload.get('excludedUnknownTime', 0)} excluded unknown-time"
            )
            if not _payload.get("crossClockEstablished"):
                st.warning("CROSS-CLOCK COMPARABILITY NOT ESTABLISHED")
            if _payload.get("rows"):
                st.dataframe(_payload["rows"], use_container_width=True)
            else:
                st.info("No events matched this window.")
        elif _route == "ASSURANCE":
            if _answer.get("state") == "FOUND":
                _res = _answer["result"]
                st.markdown(f"### {_res.get('result')}")
                st.write(
                    "Verdict owner: **HAIEC** · Recomputed by LogSense: NO · Recomputed by AI: NO"
                )
                st.caption(
                    f"Imported source: `{(_res.get('importedFrom') or {}).get('fileName')}` · "
                    f"SHA-256 `{str((_res.get('importedFrom') or {}).get('sha256'))[:16]}…`"
                )
                st.dataframe(
                    [{k: v for k, v in _res.items() if v not in (None, [], {}, "")}],
                    use_container_width=True,
                )
                if _answer.get("measurement") is not None:
                    st.markdown("#### Side-by-side proof chain")
                    _m, _h = st.columns(2)
                    _m.markdown("**LOGSENSE — MEASUREMENT**")
                    _m.dataframe([_answer["measurement"]], use_container_width=True)
                    _h.markdown("**HAIEC — CONTROL RESULT**")
                    _h.dataframe(
                        [
                            {
                                k: _res[k]
                                for k in (
                                    "controlId",
                                    "runId",
                                    "result",
                                    "controlVersionRef",
                                    "policyDigest",
                                    "resultDigest",
                                )
                                if _res.get(k)
                            }
                        ],
                        use_container_width=True,
                    )
                    st.metric("Linkage state", _answer.get("linkage"))
            elif _answer.get("state") == "CONFLICT":
                st.error("AUTHORITATIVE RESULT CONFLICT — OPERATOR REVIEW REQUIRED")
                for _m_row in _answer.get("matches") or []:
                    st.dataframe(
                        [{k: v for k, v in _m_row.items() if k != "detail"}],
                        use_container_width=True,
                    )
            else:
                st.warning("NOT AVAILABLE — IMPORT AUTHORITATIVE HAIEC CONTROL TEST RESULT")
                st.write(
                    f"Expected controlId: `{(_answer.get('expected') or {}).get('controlId')}` · "
                    f"expected runId: `{(_answer.get('expected') or {}).get('runId')}`"
                )
                st.write(
                    "LogSense measurement for this control+run: "
                    + ("exists" if _answer.get("measurementExists") else "does not exist")
                )
                st.caption(
                    "LogSense measurement is never compared against the HAIEC-owned "
                    "threshold. Import the HAIEC Control Test JSON above."
                )
        elif _route == "MEASUREMENT":
            if _payload:
                st.dataframe(
                    [
                        {
                            k: v
                            for k, v in _payload.items()
                            if isinstance(v, (str, int, float, bool)) or v is None
                        }
                    ],
                    use_container_width=True,
                )
                with st.expander("Full measurement payload"):
                    st.json(_payload)
            else:
                st.info("No measurement found for this exact control + run.")
            st.caption("MEASUREMENT IS NOT A VERDICT — the control verdict is HAIEC's.")
        elif _route == "GAP-STATUS":
            if _payload:
                st.json(_payload)
            else:
                st.info("No event readiness projection is available for this case yet.")

        if _tool.get("citations"):
            with st.expander("Proof / citations"):
                for ref in _tool["citations"]:
                    st.code(ref, language=None)
        if _tool.get("limitations"):
            st.caption("Limitations: " + " · ".join(str(x) for x in _tool["limitations"]))
        st.markdown("#### Drill-down")
        _d1, _d2 = st.columns(2)
        _d1.page_link("pages/timeline_actions.py", label="Open Timeline / Forensic Window")
        _d2.page_link("pages/competition.py", label="Open Competition / Event workbench")

if _judge_history():
    with st.expander(f"Judge session history ({len(_judge_history())} turns)"):
        for item in reversed(_judge_history()):
            st.markdown(f"**Q:** {item['question']}")
            st.caption(f"Route: {item['routed']['route']} · routable: {item['routed']['routable']}")

# --- question ---------------------------------------------------------------------
st.divider()
st.subheader("Question")
st.caption("Suggested:")
suggested = st.pills("Suggested questions", shared.SUGGESTED_QUESTIONS, selection_mode="single")
default_question = suggested or ""
question = st.text_area(
    "Ask about established facts, evidence, uncertainty, recovery, causes, comparison perimeter, or next evidence.",
    value=default_question,
    height=110,
    placeholder="What is established, what remains unresolved, and which evidence supports that conclusion?",
    key="ask_question",
)

history = st.session_state.setdefault("ask_turns", [])
if st.button("Ask LogSense", type="primary", disabled=not question.strip()):
    if not provider_key_source(provider):
        st.error(
            f"{provider_label} needs an API key first — add it in the sidebar or run `logsense setup`."
        )
        st.stop()
    toolbox = InvestigatorToolbox(
        analysis=analysis,
        report=report,
        competition=shared.competition_payload(),
    )
    try:
        provider_instance = shared.create_provider_from_ui()
    except Exception as exc:
        st.error(shared.provider_unavailable_message(exc))
        st.stop()
    session = InvestigatorSession(provider=provider_instance, toolbox=toolbox)
    with st.spinner(f"{provider_label} is investigating the deterministic output..."):
        try:
            turn = session.ask(question)
        except InvestigatorBoundaryError as exc:
            st.error(f"Investigator response rejected by deterministic provenance gate: {exc}")
        except Exception as exc:
            st.error(shared.provider_unavailable_message(exc))
        else:
            view: dict[str, Any] | None = investigator_turn_view(turn)
            history.append(view)
            st.session_state["ask_logsense_last_turn"] = view

view = st.session_state.get("ask_logsense_last_turn")
if view:
    st.divider()
    st.subheader("Answer")
    st.write(view["answer"])

    st.markdown("#### Citations")
    if view["citations"]:
        for ref in view["citations"]:
            st.code(ref, language=None)
    else:
        st.warning("No citations returned.")

    st.markdown("#### Uncertainty / limits")
    if view["uncertainty"]:
        for item in view["uncertainty"]:
            st.write(f"- {item}")
    else:
        st.caption("No additional uncertainty supplied by the investigator response.")

    with st.expander("Audited read-only tool trace"):
        st.write("Provider:", view["provider"])
        st.write("Tool calls:", view["toolCalls"] or [])
        st.write("Tool results:", view["toolResultCount"])
        if view["toolStates"]:
            st.dataframe(view["toolStates"], use_container_width=True)
        else:
            st.info("No tools were invoked.")
        st.caption(
            "Tool payload content is treated as untrusted data. Canonical mutation allowed: No."
        )

if history:
    with st.expander(f"Session history ({len(history)} turns)"):
        for item in reversed(history):
            st.markdown(f"**Q:** {item['question']}")
            st.caption(f"Provider: {item['provider']} · tools: {item['toolResultCount']}")

st.caption(
    f"Provider: {provider_label} · key env `{provider_key_env(provider)}` · "
    f"model env `{provider_model_env(provider)}`"
)
