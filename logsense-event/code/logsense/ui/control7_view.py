"""Control 7 (AIA-LOG-001) panel — run declaration → manifest → measurement.

Renders the functional Event Recording experience inside the competition
stepper. Every element reads or writes through ``IntegrationService`` — the
page never recomputes measurements itself. The final control verdict is
explicitly not evaluated here; HAIEC applies the frozen threshold later.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from logsense.competition.expected_events import (
    RUN_SCOPED_MATCH_FIELDS,
    ExpectedManifestError,
    load_manifest_text,
)
from logsense.competition.fixture_packs import list_fixtures
from logsense.competition.run import CompetitionRunError
from logsense.integrations.service import IntegrationRequestError
from logsense.ui import shared
from logsense.workspace.cases import CaseWorkspaceError


def _state_badge(state: str) -> str:
    return {
        "RESOLVED": "RESOLVED — all assessable evidence unambiguously assigned",
        "PARTIAL": (
            "PARTIAL — events bound, but unresolved or unattributable "
            "(identifier-less) evidence remains"
        ),
        "AMBIGUOUS": "AMBIGUOUS — conflicting run identifiers detected",
        "NOT_RESOLVED": "NOT_RESOLVED — no events bound to this run",
    }.get(state, state)


def _render_resolution(resolution: dict[str, Any]) -> None:
    state = str(resolution.get("resolutionState") or "")
    st.markdown(f"**Run `{resolution.get('runId')}` — run resolution: {state}**")
    st.caption(_state_badge(state))
    cols = st.columns(4)
    qualified = resolution.get("qualifiedEventRefs") or resolution.get("eventRefs") or []
    cols[0].metric("Qualified events", len(qualified))
    cols[1].metric("Unresolved", len(resolution.get("unresolvedEvidenceRefs") or []))
    cols[2].metric("Ambiguous", len(resolution.get("ambiguousEvidenceRefs") or []))
    cols[3].metric("Unidentified", int(resolution.get("unidentifiedEventCount") or 0))
    st.caption(
        "Binding basis: "
        + ", ".join(f"`{item}`" for item in resolution.get("bindingBasis") or ())
        + " — run membership comes from allowlisted identifier kinds only, "
        "never timestamp proximity or shared semantic attributes."
    )
    ambiguous_refs = resolution.get("ambiguousEvidenceRefs") or []
    if ambiguous_refs:
        st.error(
            f"{len(ambiguous_refs)} record(s) have conflicting run identifiers "
            "and were excluded from measurement: " + ", ".join(f"`{ref}`" for ref in ambiguous_refs)
        )
    for ref in resolution.get("unresolvedEvidenceRefs") or []:
        st.caption(f"Unresolved evidence: `{ref}`")


def _render_measurement(measurement: dict[str, Any]) -> None:
    coverage = measurement.get("coverage") or {}
    timing = measurement.get("timing") or {}
    st.markdown(
        f"### CONTROL 7 — EVENT RECORDING\n\n"
        f"Run: `{measurement.get('runId')}` · Manifest: `{measurement.get('manifestId')}`"
    )
    st.markdown(
        f"**Run resolution: {measurement.get('resolutionState') or 'UNKNOWN'}** · "
        f"**Measurement: {measurement.get('measurementState') or 'UNKNOWN'}**"
    )
    excluded = (measurement.get("excludedEvidence") or {}).get("ambiguousEvidenceRefs") or []
    if excluded:
        st.error(
            f"{len(excluded)} record(s) have conflicting run identifiers and "
            "were excluded from measurement: " + ", ".join(f"`{ref}`" for ref in excluded)
        )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected events", (measurement.get("expected") or {}).get("count"))
    c2.metric("Observed/matched", (measurement.get("observed") or {}).get("matchedCount"))
    percent = coverage.get("percent")
    c3.metric("Coverage", f"{percent:.2f}%" if percent is not None else "n/a")
    c4.metric("Missing", len(measurement.get("missingEvents") or []))
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Duplicates", len(measurement.get("duplicates") or []))
    c6.metric("Unexpected", len(measurement.get("unexpectedEvents") or []))
    c7.metric("Measured gaps", timing.get("measuredGaps"))
    c8.metric("Gap violations", timing.get("violatingGaps"))
    overall_expected = coverage.get("overallExpected")
    if overall_expected is not None and overall_expected != coverage.get("expectedRequired"):
        overall_percent = coverage.get("overallPercent")
        st.caption(
            "Required-scope coverage: "
            f"{coverage.get('matchedRequired')}/{coverage.get('expectedRequired')} "
            f"({f'{percent:.2f}%' if percent is not None else 'n/a'}). "
            "Overall expected events (including optional): "
            f"{coverage.get('overallMatched')}/{overall_expected} "
            f"({f'{overall_percent:.2f}%' if overall_percent is not None else 'n/a'}) — "
            "optional events are excluded from the required denominator."
        )
    st.info(
        "Final control verdict: **not evaluated here** — HAIEC applies the "
        "frozen threshold. Coverage and timing are separate measurements: "
        "100% coverage does not imply all gaps satisfied the limit."
    )

    with st.expander("Expected event path — matched vs missing", expanded=True):
        matched_by_expected = {
            item["expectedEventId"]: item for item in measurement.get("matched") or ()
        }
        rows = []
        for entry in measurement.get("missingEvents") or ():
            rows.append(
                {
                    "ordinal": entry.get("ordinal"),
                    "expected": entry.get("expectedEventId"),
                    "eventType": entry.get("eventType"),
                    "actor": entry.get("actorId"),
                    "state": "MISSING",
                    "observed": None,
                    "timestamp": None,
                    "matchBasis": None,
                }
            )
        for expected_id, item in matched_by_expected.items():
            rows.append(
                {
                    "ordinal": item.get("ordinal"),
                    "expected": expected_id,
                    "eventType": None,
                    "actor": None,
                    "state": "MATCHED",
                    "observed": item.get("observedEventRef"),
                    "timestamp": item.get("observedEventTime"),
                    "matchBasis": ", ".join(item.get("matchBasis") or ()),
                }
            )
        rows.sort(key=lambda row: (row["ordinal"] or 0, str(row["expected"])))
        st.dataframe(rows, use_container_width=True, hide_index=True)

    unexpected = measurement.get("unexpectedEvents") or []
    if unexpected:
        with st.expander(f"Unexpected observed events ({len(unexpected)})"):
            st.dataframe(list(unexpected), use_container_width=True, hide_index=True)
    duplicates = measurement.get("duplicates") or []
    if duplicates:
        with st.expander(f"Duplicates ({len(duplicates)})"):
            st.dataframe(list(duplicates), use_container_width=True, hide_index=True)

    with st.expander("Sequence comparison", expanded=False):
        st.dataframe(
            list(measurement.get("sequenceDivergences") or ()),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Ordering facts only — a divergence is not a root cause.")

    with st.expander("Timing gaps", expanded=bool(timing.get("declaredGapLimitMs") is not None)):
        if measurement.get("timingGaps"):
            st.dataframe(
                list(measurement["timingGaps"]),
                use_container_width=True,
                hide_index=True,
            )
            if timing.get("declaredGapLimitMs") is not None:
                comparator = timing.get("effectiveGapComparator") or "LTE"
                rule = f"gap {'<' if comparator == 'LT' else '≤'} {timing['declaredGapLimitMs']} ms"
                if timing.get("gapComparatorSource") == "LEGACY_DEFAULT":
                    st.caption(
                        f"Effective legacy rule: {rule} "
                        f"({timing.get('thresholdSource')}, {timing.get('thresholdVersionRef')}). "
                        "Comparator was not explicitly declared in this historical "
                        "manifest — the historical ≤ behavior is preserved for compatibility."
                    )
                else:
                    st.caption(
                        f"Declared timing rule: {rule} "
                        f"({timing.get('thresholdSource')}, {timing.get('thresholdVersionRef')})."
                    )
            st.caption("NOT_MEASURED rows mean at least one timestamp was missing — never zero.")
        else:
            st.caption("No consecutive matched pairs eligible for gap measurement.")

    st.caption(
        "Limitations: " + ", ".join(f"`{item}`" for item in measurement.get("limitations") or ())
    )


MATCH_FIELD_OPTIONS = (
    "eventType",
    "actorId",
    "operation",
    "eventId",
    "traceId",
    "requestId",
    "sessionId",
    "taskId",
    "actionCorrelationId",
    "modelCallId",
    "toolCallId",
)
_DRAFT_KEY = "c7_manifest_draft"


def _blank_draft() -> dict[str, Any]:
    return {
        "manifestId": "",
        "label": "",
        "sourceBasis": "BLANK",
        "notes": "",
        "gapLimitMs": None,
        "gapComparator": "LTE",
        "gapComparatorLegacy": False,
        "thresholdSource": "",
        "thresholdVersionRef": "",
        "references": {},
        "limitations": [],
        "rows": [
            {
                "ordinal": 1,
                "expectedEventId": "E01",
                "eventType": "",
                "actorId": "",
                "operation": "",
                "required": True,
                "note": "",
                "match": {},
            }
        ],
    }


def _draft() -> dict[str, Any]:
    draft = st.session_state.get(_DRAFT_KEY)
    if not isinstance(draft, dict):
        draft = _blank_draft()
        st.session_state[_DRAFT_KEY] = draft
    return draft


def _manifest_into_draft(manifest: dict[str, Any], *, basis: str) -> None:
    """Load a manifest/template/draft payload into the visual editor state."""
    timing = manifest.get("timing") or {}
    st.session_state[_DRAFT_KEY] = {
        "manifestId": str(manifest.get("manifestId") or ""),
        "label": str(manifest.get("label") or ""),
        "sourceBasis": basis,
        "notes": str(manifest.get("notes") or ""),
        "gapLimitMs": timing.get("declaredGapLimitMs"),
        # Legacy manifests omit the comparator — keep it None so the editor
        # shows the compatibility disclosure; saving writes an explicit value.
        "gapComparator": timing.get("declaredGapComparator") or "LTE",
        "gapComparatorLegacy": (
            timing.get("declaredGapLimitMs") is not None
            and timing.get("declaredGapComparator") is None
        ),
        "thresholdSource": str(timing.get("thresholdSource") or ""),
        "thresholdVersionRef": str(timing.get("thresholdVersionRef") or ""),
        "references": dict(manifest.get("references") or {}),
        "limitations": list(manifest.get("limitations") or ()),
        "rows": [
            {
                "ordinal": int(row.get("ordinal") or i),
                "expectedEventId": str(row.get("expectedEventId") or f"E{i:02d}"),
                "eventType": str(row.get("eventType") or ""),
                "actorId": str(row.get("actorId") or ""),
                "operation": str(row.get("operation") or ""),
                "required": bool(row.get("required", True)),
                "note": str(row.get("note") or ""),
                "match": dict(row.get("match") or {}),
            }
            for i, row in enumerate(manifest.get("events") or (), start=1)
        ]
        or _blank_draft()["rows"],
    }


def _draft_to_manifest(draft: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(
        draft["rows"], key=lambda r: (int(r.get("ordinal") or 0), str(r["expectedEventId"]))
    )
    events = []
    for index, row in enumerate(rows, start=1):
        events.append(
            {
                "expectedEventId": str(row.get("expectedEventId") or f"E{index:02d}"),
                "ordinal": index,
                "eventType": str(row.get("eventType") or "") or None,
                "actorId": str(row.get("actorId") or "") or None,
                "operation": str(row.get("operation") or "") or None,
                "required": bool(row.get("required", True)),
                "note": str(row.get("note") or "") or None,
                "match": {
                    str(k): str(v)
                    for k, v in (row.get("match") or {}).items()
                    if str(k).strip() and str(v).strip()
                },
            }
        )
    timing: dict[str, Any] = {}
    if draft.get("gapLimitMs") is not None:
        timing["declaredGapLimitMs"] = draft["gapLimitMs"]
        # New saved versions always carry an explicit comparator — the
        # editor defaults to LTE and never emits a legacy-null manifest.
        timing["declaredGapComparator"] = draft.get("gapComparator") or "LTE"
    if draft.get("thresholdSource"):
        timing["thresholdSource"] = draft["thresholdSource"]
    if draft.get("thresholdVersionRef"):
        timing["thresholdVersionRef"] = draft["thresholdVersionRef"]
    return {
        "schemaVersion": "competition-expected-events/0.1",
        "manifestId": str(draft.get("manifestId") or "").strip(),
        "label": str(draft.get("label") or "").strip() or None,
        "events": events,
        "timing": timing or None,
        "references": {k: v for k, v in (draft.get("references") or {}).items() if v},
        "limitations": list(draft.get("limitations") or ()),
        "sourceBasis": draft.get("sourceBasis") or "BLANK",
        "notes": str(draft.get("notes") or "") or None,
    }


def _optional_scope_warning(rows: list[dict[str, Any]]) -> str | None:
    """Scored-scope disclosure: optional events stay out of the required
    coverage denominator — the operator owns that declaration."""
    optional = [r for r in rows if not r.get("required", True)]
    if not optional:
        return None
    ids = ", ".join(f"`{r['expectedEventId']}`" for r in optional)
    return (
        f"{len(optional)} expected events are optional and are excluded "
        "from required-event coverage. For competition-scored C7 events, "
        f"mark every in-scope event as Required: {ids}"
    )


def _merge_editor_rows(
    draft_rows: list[dict[str, Any]], edited: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge ``st.data_editor`` output back into draft rows.

    Match rules are bound by **expectedEventId**, never row position — a
    delete/insert/reorder in the editor must not migrate one event's match
    block onto another. An edited ID that no longer matches an existing
    draft row starts with an empty (fail-closed) match block; the operator
    reviews it before saving.
    """
    match_by_id: dict[str, dict[str, Any]] = {}
    for row in draft_rows:
        event_id = str(row.get("expectedEventId") or "")
        if event_id and event_id not in match_by_id:
            match_by_id[event_id] = dict(row.get("match") or {})
    merged = []
    for i, row in enumerate(edited):
        event_id = str(row.get("expectedEventId") or f"E{i + 1:02d}")
        merged.append(
            {
                "ordinal": int(row.get("ordinal") or i + 1),
                "expectedEventId": event_id,
                "eventType": str(row.get("eventType") or ""),
                "actorId": str(row.get("actorId") or ""),
                "operation": str(row.get("operation") or ""),
                "required": bool(row.get("required", True)),
                "note": str(row.get("note") or ""),
                "match": match_by_id.get(event_id, {}),
            }
        )
    return merged


def _render_manifest_editor(svc: Any, case_id: str) -> None:
    """Visual expected-event editor — no JSON required in the normal path."""
    draft = _draft()

    with st.expander("Expected events", expanded=True):
        st.caption(
            "Add, remove, reorder and edit rows. **Order** defines the expected "
            "sequence. Rows with no match rule fail closed at measurement — "
            "they never absorb arbitrary evidence."
        )
        table_rows = [{k: v for k, v in row.items() if k != "match"} for row in draft["rows"]]
        edited = st.data_editor(
            table_rows,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="c7_draft_table",
            column_config={
                "ordinal": st.column_config.NumberColumn("Order", min_value=1, required=True),
                "expectedEventId": st.column_config.TextColumn("Expected event ID", required=True),
                "eventType": st.column_config.TextColumn("Event type"),
                "actorId": st.column_config.TextColumn("Actor / agent"),
                "operation": st.column_config.TextColumn("Operation"),
                "required": st.column_config.CheckboxColumn("Required"),
                "note": st.column_config.TextColumn("Note"),
            },
        )
        draft["rows"] = _merge_editor_rows(draft["rows"], edited)

    if not draft["rows"]:
        st.info("Add at least one expected event row.")
        return

    with st.expander("Match rules (deterministic — exact fields only)", expanded=False):
        st.caption(
            "Each match rule is an exact-equality field checked against "
            "canonical events (AND semantics). Prefer stable semantic fields "
            "(event type, actor, operation) so the manifest stays reusable "
            "across PASS / BREACH / RETEST runs. Run-specific IDs change "
            "between runs — add them only when the scenario requires it."
        )
        st.caption(
            "Common fields: "
            + ", ".join(f"`{field}`" for field in MATCH_FIELD_OPTIONS)
            + ". Any other canonical attribute key is accepted verbatim — "
            "matching stays exact-equality only, so an unsupported key "
            "simply fails closed."
        )
        row_ids = [str(r["expectedEventId"]) for r in draft["rows"]]
        target = st.selectbox("Expected event", row_ids, key="c7_match_row")
        row = next(r for r in draft["rows"] if str(r["expectedEventId"]) == target)
        match_rows = [{"field": k, "value": str(v)} for k, v in (row.get("match") or {}).items()]
        edited_match = st.data_editor(
            match_rows,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"c7_match_table_{target}",
            column_config={
                "field": st.column_config.TextColumn(
                    "Match field (canonical attribute key)", required=True
                ),
                "value": st.column_config.TextColumn("Exact value", required=True),
            },
        )
        run_scoped = [r["field"] for r in edited_match if r.get("field") in RUN_SCOPED_MATCH_FIELDS]
        if run_scoped:
            st.warning(
                "Run-scoped identifier(s) in match rules: "
                + ", ".join(f"`{f}`" for f in run_scoped)
                + " — these may legitimately change between CALIBRATION / PASS / "
                "BREACH / RETEST runs and can make the manifest non-reusable."
            )
        row["match"] = {
            str(r["field"]): str(r["value"])
            for r in edited_match
            if r.get("field") and str(r.get("value") or "").strip()
        }
        if not row["match"]:
            st.caption(
                "This expected event has no match rules — it will report "
                "MISSING at measurement (fail closed). Add criteria before "
                "saving if this row should match evidence."
            )

    with st.expander("Timing and governance references", expanded=False):
        gap = st.number_input(
            "Declared gap limit (ms) — optional",
            min_value=0,
            value=int(draft.get("gapLimitMs") or 0),
            step=1000,
            key="c7_gap_limit",
        )
        draft["gapLimitMs"] = float(gap) if gap else None
        if draft["gapLimitMs"] is not None:
            comparator = st.selectbox(
                "Gap comparator — required when a gap limit is declared",
                ("LTE", "LT"),
                index=0 if draft.get("gapComparator") != "LT" else 1,
                format_func=lambda c: (
                    "≤ limit — gap may equal the limit"
                    if c == "LTE"
                    else "< limit — gap equal to the limit violates"
                ),
                key="c7_gap_comparator",
                help="The competition declares whether a measured gap must be strictly less than the limit (LT) or at most equal to it (LTE).",
            )
            draft["gapComparator"] = comparator
            if draft.get("gapComparatorLegacy"):
                st.warning(
                    "This manifest predates explicit timing comparators. "
                    "LogSense is preserving the historical ≤ behavior for "
                    "compatibility — confirm the comparator before saving; "
                    "the new version will record it explicitly."
                )
        c1, c2 = st.columns(2)
        draft["thresholdSource"] = c1.text_input(
            "Threshold source (optional)",
            value=draft.get("thresholdSource") or "",
            key="c7_thr_src",
        )
        draft["thresholdVersionRef"] = c2.text_input(
            "Threshold version ref (optional)",
            value=draft.get("thresholdVersionRef") or "",
            key="c7_thr_ref",
        )
        st.caption(
            "HAIEC governance references — stored as references only; LogSense "
            "never creates or mutates the HAIEC control."
        )
        refs = dict(draft.get("references") or {})
        for field in (
            "controlRef",
            "controlVersionRef",
            "thresholdVersionRef",
            "enforcementPointRef",
            "scenarioCaptureRef",
        ):
            value = st.text_input(
                field,
                value=str(refs.get(field) or ""),
                key=f"c7_ref_{field}",
            )
            if value.strip():
                refs[field] = value.strip()
            else:
                refs.pop(field, None)
        draft["references"] = refs

    st.markdown("**Save reviewed manifest**")
    c1, c2 = st.columns([2, 1])
    draft["manifestId"] = c1.text_input(
        "Manifest ID",
        value=draft.get("manifestId") or "",
        placeholder="c7-standard",
        key="c7_manifest_id",
    )
    draft["label"] = c2.text_input(
        "Label", value=draft.get("label") or "", key="c7_manifest_label_edit"
    )
    draft["notes"] = st.text_input(
        "Notes (optional)", value=draft.get("notes") or "", key="c7_manifest_notes"
    )
    empty_match = [r["expectedEventId"] for r in draft["rows"] if not (r.get("match") or {})]
    if empty_match:
        st.warning(
            "Rows with no match rules will fail closed at measurement: "
            + ", ".join(f"`{r}`" for r in empty_match)
        )
    scope_warning = _optional_scope_warning(draft["rows"])
    if scope_warning:
        st.warning(scope_warning)
    if st.button("Save reviewed manifest", key="c7_manifest_save_draft", type="primary"):
        try:
            saved = svc.save_expected_event_manifest(
                case_id=case_id,
                manifest=_draft_to_manifest(draft),
                source_basis=str(draft.get("sourceBasis") or "BLANK"),
            )
        except (ExpectedManifestError, IntegrationRequestError, CaseWorkspaceError) as exc:
            st.error(str(exc))
        else:
            st.success(
                f"Saved `{saved['manifestRef']}` — digest "
                f"`{str(saved.get('manifestDigest'))[:24]}…`. Saved versions are "
                "immutable; editing and saving again creates a new version."
            )
            st.rerun()


def _render_manifest_sources(svc: Any, case_id: str) -> None:
    """Four entry choices: blank / calibration draft / template / advanced import."""
    entry = st.radio(
        "Start the expected-event manifest",
        (
            "Create blank",
            "Draft from calibration run",
            "Start from template",
            "Advanced import (JSON/YAML)",
        ),
        horizontal=True,
        key="c7_manifest_entry",
    )
    if entry == "Create blank":
        if st.button("Start blank manifest", key="c7_entry_blank"):
            st.session_state[_DRAFT_KEY] = _blank_draft()
            st.rerun()
    elif entry == "Draft from calibration run":
        st.caption(
            "Reconstructs a DRAFT from a run's qualified canonical events "
            "only — ambiguous and unresolved evidence is never used. "
            "Run-scoped identifiers are not embedded, so the result stays "
            "reusable across PASS / BREACH / RETEST."
        )
        runs = svc.list_competition_runs(case_id)
        if not runs:
            st.info("Confirm a run on the Runs step first.")
        else:
            run_options = [f"{r['runId']} — {r.get('runRole') or 'no role'}" for r in runs]
            pick = st.selectbox("Source run", run_options, key="c7_cal_run")
            draft_id = st.text_input(
                "Draft manifest ID", value="c7-draft", key="c7_cal_manifest_id"
            )
            if st.button("Generate draft from run", key="c7_cal_generate"):
                run_id = str(pick).split(" — ")[0]
                try:
                    draft = svc.draft_manifest_from_run(
                        case_id=case_id, run_id=run_id, manifest_id=draft_id
                    )
                except (
                    IntegrationRequestError,
                    CaseWorkspaceError,
                    ExpectedManifestError,
                ) as exc:
                    st.error(str(exc))
                else:
                    _manifest_into_draft(draft, basis="CALIBRATION_DRAFT")
                    st.rerun()
    elif entry == "Start from template":
        templates = {t["manifestId"]: t for t in svc.manifest_templates()}
        pick = st.selectbox(
            "Template",
            list(templates),
            format_func=lambda k: f"{k} — {templates[k]['label']}",
            key="c7_template_pick",
        )
        if st.button("Load template", key="c7_template_load"):
            _manifest_into_draft(dict(templates[pick]), basis="TEMPLATE")
            st.rerun()
    else:
        upload = st.file_uploader(
            "Expected-event manifest (JSON or YAML)",
            type=["json", "yaml", "yml"],
            key="c7_manifest_upload",
        )
        if upload is not None and st.button("Import file", key="c7_manifest_import_file"):
            try:
                manifest = load_manifest_text(
                    upload.getvalue().decode("utf-8"),
                    format_hint=str(upload.name).rsplit(".", 1)[-1],
                )
            except ExpectedManifestError as exc:
                st.error(str(exc))
            else:
                _manifest_into_draft(manifest, basis="IMPORTED")
                st.rerun()
        pasted = st.text_area("Or paste JSON/YAML", height=160, key="c7_manifest_paste")
        if st.button("Import pasted manifest", key="c7_manifest_import_paste"):
            try:
                manifest = load_manifest_text(pasted)
            except ExpectedManifestError as exc:
                st.error(str(exc))
            else:
                _manifest_into_draft(manifest, basis="IMPORTED")
                st.rerun()


def _render_saved_manifests(svc: Any, case_id: str) -> None:
    manifests = svc.list_expected_manifests(case_id)
    if not manifests:
        st.caption("No reviewed manifests saved yet.")
        return
    st.markdown("**Saved manifests**")
    for manifest in manifests:
        versions = svc.list_expected_manifest_versions(case_id, str(manifest["manifestId"]))
        timing = manifest.get("timing") or {}
        cols = st.columns([3, 2, 2, 2])
        cols[0].write(
            f"`{manifest.get('manifestRef') or manifest['manifestId']}` — {manifest.get('label')}"
        )
        cols[1].write(
            f"{len(manifest.get('events') or [])} events · "
            f"{manifest.get('sourceBasis') or 'IMPORTED'}"
        )
        if timing.get("declaredGapLimitMs") is not None:
            comparator = timing.get("declaredGapComparator")
            if comparator:
                gap_rule = (
                    f"gap {'<' if comparator == 'LT' else '≤'} {timing['declaredGapLimitMs']} ms"
                )
            else:
                gap_rule = f"gap ≤ {timing['declaredGapLimitMs']} ms (legacy)"
            cols[2].write(gap_rule)
        else:
            cols[2].write("no gap limit")
        if cols[3].button("Edit → new version", key=f"c7_edit_{manifest['manifestId']}"):
            payload = dict(manifest)
            for transient in (
                "manifestVersion",
                "manifestDigest",
                "manifestRef",
                "createdAt",
            ):
                payload.pop(transient, None)
            _manifest_into_draft(payload, basis=str(manifest.get("sourceBasis") or "IMPORTED"))
            st.rerun()
        if len(versions) > 1:
            st.caption(
                "Versions: "
                + " · ".join(f"`{v.get('manifestRef')}`" for v in versions)
                + " — every saved version is immutable."
            )


def _render_handoff(svc: Any, case_id: str, run_id: str) -> None:
    """Send-to-HAIEC panel — deterministic checklist, no verdict."""
    st.markdown("**HAIEC handoff**")
    status = svc.haiec_handoff_status(case_id, run_id)
    state_label = (
        "HAIEC HANDOFF COMPLETE"
        if status["handoffComplete"]
        else ("MEASUREMENT READY" if status["measurementReady"] else "NOT READY")
    )
    st.markdown(f"**{state_label}**")
    for check in status["checks"]:
        icon = "?" if check.get("optional") else ("✓" if check["met"] else "✗")
        mark = "" if check["met"] else " — missing"
        st.write(f"{icon} {check['item']}{mark}")
    st.info(
        "LogSense has reconstructed and measured this run. HAIEC owns the "
        "frozen child control/threshold and final Control Test result. " + str(status["nextAction"])
    )
    bundle = svc.load_competition_bundle(case_id, run_id)
    if bundle:
        st.download_button(
            "Download Competition Evidence Bundle",
            data=(json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            file_name=f"{case_id}-{run_id}-competition-evidence-bundle.json",
            mime="application/json",
            key="c7_dl_bundle",
        )
        st.caption(f"Bundle `{bundle.get('bundleId')}` — content-addressed, immutable.")


def _render_runs_matrix(svc: Any, case_id: str) -> None:
    """Runs sharing the same manifest/refs — orientation only, not comparison."""
    runs = svc.list_competition_runs(case_id)
    rows = []
    for run in runs:
        measurement = svc.load_control7_measurement(case_id, str(run["runId"]))
        refs = (measurement or {}).get("references") or {}
        rows.append(
            {
                "Run": run["runId"],
                "Role": run.get("runRole") or "—",
                "Manifest": (measurement or {}).get("expectedManifestRef") or "—",
                "Control ref": refs.get("controlVersionRef") or refs.get("controlRef") or "—",
                "Measurement": (measurement or {}).get("measurementState") or "—",
            }
        )
    if rows and any(r["Measurement"] != "—" for r in rows):
        with st.expander("Runs sharing manifests / control refs", expanded=False):
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.caption(
                "Run role is operator workflow metadata — it never determines "
                "the measurement. Broader multi-run comparison lands in a "
                "later slice."
            )


def _render_drilldown(svc: Any, case_id: str, measurement: dict[str, Any]) -> None:
    """Open the exact canonical record behind an observed event ref."""
    refs = [
        str(item["observedEventRef"])
        for item in measurement.get("matched") or ()
        if item.get("observedEventRef")
    ]
    refs += [
        str(item["observedEventRef"])
        for item in list(measurement.get("duplicates") or ())
        + list(measurement.get("unexpectedEvents") or ())
        if item.get("observedEventRef")
    ]
    if not refs:
        return
    with st.expander("Open exact evidence", expanded=False):
        pick = st.selectbox("Observed record", sorted(set(refs)), key="c7_drill_ref")
        results = svc.load_case_results(case_id) or {}
        canonical = (results.get("analysis") or {}).get("canonicalEvents") or []
        event = next((e for e in canonical if str(e.get("eventId")) == pick), None)
        if event is None:
            st.caption("Record not present in the active analysis snapshot.")
            return
        st.write(
            f"`{pick}` — class `{event.get('eventClass')}` · "
            f"time `{event.get('eventTime')}` · quality `{event.get('timeQuality')}`"
        )
        attrs = event.get("attributes") or {}
        if attrs:
            st.dataframe(
                [{"field": k, "value": str(v)} for k, v in attrs.items()],
                use_container_width=True,
                hide_index=True,
            )


def render_control7_panel(case_id: str) -> None:
    """Functional Control 7 operator flow: active run → manifest → measure
    → drilldown → HAIEC handoff."""
    svc = shared.service()

    st.markdown("#### Control 7 — Event Recording measurement")
    st.caption(
        "Measure the active confirmed run against a reviewed expected-event "
        "manifest. LogSense produces measurements only — HAIEC owns "
        "SATISFIED/NOT SATISFIED."
    )

    with st.expander("Optional: load a built-in Control 7 fixture", expanded=False):
        metas = {
            meta["fixtureId"]: meta
            for meta in list_fixtures()
            if meta.get("control", "AIA-LOG-001") == "AIA-LOG-001"
        }
        pick = st.selectbox(
            "Fixture",
            list(metas),
            format_func=lambda name: f"{name} — {metas[name]['label']}",
            key="c7_fixture_pick",
        )
        st.caption(metas[pick]["description"])
        if st.button("Load fixture into this case", key="c7_fixture_load"):
            try:
                with st.spinner("Importing fixture evidence, resolving run, measuring…"):
                    output = svc.import_competition_fixture(case_id=case_id, fixture_name=pick)
            except (IntegrationRequestError, CaseWorkspaceError, CompetitionRunError) as exc:
                st.error(str(exc))
            else:
                st.session_state["c7_last_measurement"] = output["measurement"]
                st.session_state["c7_last_resolution"] = output["run"]
                st.success(
                    f"Fixture loaded — run `{output['run']['runId']}` "
                    f"({output['run']['resolutionState']})."
                )
                st.rerun()

    # ---- 1 · active run ------------------------------------------------------
    st.markdown("**1 — Active run**")
    active = svc.active_run(case_id)
    if not active.get("runId"):
        st.warning(
            "**Active Run — Not selected.** Confirm and select the run you "
            "are investigating on the Runs step first."
        )
        if st.button("Go to Runs step", key="c7_goto_runs", type="primary"):
            st.session_state["competition_step"] = 5
            st.rerun()
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Run", active["runId"])
        c2.metric("Role", active.get("runRole") or "—")
        snap_state = svc.analysis_snapshot_state(case_id)
        c3.metric("Snapshot", snap_state.get("snapshotLabel") or "—")
        c4.metric("Resolution", active.get("resolutionState") or "unresolved")
        if str(snap_state.get("state", "")).startswith("STALE"):
            st.warning(
                "Evidence or mapping changed after this analysis. Run "
                "deterministic analysis again (Analyze step) to create a "
                "current snapshot before measuring."
            )
    with st.expander("Advanced: declare a run manually", expanded=False):
        st.caption(
            "Fallback for when deterministic discovery cannot identify the "
            "supplied run — the normal path uses the Runs step."
        )
        run_id_manual = st.text_input("Run ID", key="c7_run_id", placeholder="FM-A")
        label = st.text_input("Label (optional)", key="c7_run_label")
        trace_ids = st.text_input("Known trace IDs (comma-separated)", key="c7_traces")
        request_ids = st.text_input("Known request IDs (comma-separated)", key="c7_requests")
        session_ids = st.text_input("Known session IDs (comma-separated)", key="c7_sessions")
        notes = st.text_input("Notes / source (optional)", key="c7_notes")

        def _split(text: str) -> list[str]:
            return [item.strip() for item in text.split(",") if item.strip()]

        if st.button("Declare run", key="c7_declare"):
            try:
                declaration = svc.declare_competition_run(
                    case_id=case_id,
                    declaration={
                        "runId": run_id_manual,
                        "label": label or run_id_manual,
                        "traceIds": _split(trace_ids),
                        "requestIds": _split(request_ids),
                        "sessionIds": _split(session_ids),
                        "notes": notes or None,
                        "source": "COMPETITION_MODE_UI",
                    },
                )
            except (CompetitionRunError, IntegrationRequestError, CaseWorkspaceError) as exc:
                st.error(str(exc))
            else:
                st.success(f"Run `{declaration['runId']}` declared — provenance USER_DECLARED.")
                st.rerun()

    # ---- 2 · expected-event manifest ------------------------------------------
    st.markdown("**2 — Expected events**")
    _render_manifest_sources(svc, case_id)
    draft = st.session_state.get(_DRAFT_KEY)
    if isinstance(draft, dict) and draft.get("rows"):
        if draft.get("sourceBasis") == "CALIBRATION_DRAFT":
            st.warning(
                "This draft was reconstructed from observed calibration "
                "evidence. Observing an event in a calibration run does not "
                "prove this is the complete set of events the system should "
                "produce — review before saving."
            )
        for limitation in draft.get("limitations") or ():
            st.caption(f"`{limitation}`")
        _render_manifest_editor(svc, case_id)
    _render_saved_manifests(svc, case_id)

    # ---- 3 · measure -----------------------------------------------------------
    st.markdown("**3 — Measure**")
    manifests = svc.list_expected_manifests(case_id)
    declared_runs = svc.list_competition_runs(case_id)
    run_options = [str(run["runId"]) for run in declared_runs]
    active_id = str(active.get("runId") or "")
    selected_run = (
        st.selectbox(
            "Run",
            run_options,
            index=run_options.index(active_id) if active_id in run_options else 0,
            key="c7_run_select",
        )
        if run_options
        else None
    )
    manifest_options = [str(m.get("manifestRef") or m["manifestId"]) for m in manifests]
    selected_manifest = (
        st.selectbox("Manifest version", manifest_options, key="c7_manifest_select")
        if manifest_options
        else None
    )
    stale = str(svc.analysis_snapshot_state(case_id).get("state", "")).startswith("STALE")
    cols = st.columns(2)
    with cols[0]:
        if st.button(
            "Resolve run evidence",
            key="c7_resolve",
            disabled=not selected_run,
        ):
            try:
                resolved = svc.resolve_case_run(case_id=case_id, run_id=str(selected_run))
            except (IntegrationRequestError, CaseWorkspaceError) as exc:
                st.error(str(exc))
            else:
                st.session_state["c7_last_resolution"] = resolved
    with cols[1]:
        if st.button(
            "Run Control 7 measurement",
            key="c7_measure",
            type="primary",
            disabled=not selected_run or not selected_manifest or stale,
        ):
            try:
                with st.spinner("Resolving run and reconciling expected vs observed…"):
                    output = svc.run_control7_measurement(
                        case_id=case_id,
                        run_id=str(selected_run),
                        manifest_id=selected_manifest,
                    )
            except (IntegrationRequestError, CaseWorkspaceError) as exc:
                st.error(str(exc))
            else:
                st.session_state["c7_last_resolution"] = output["run"]
                st.session_state["c7_last_measurement"] = output["measurement"]

    resolution: dict[str, Any] | None = st.session_state.get("c7_last_resolution")
    if resolution is not None and selected_run and str(resolution.get("runId")) != selected_run:
        resolution = None
    if resolution is None and selected_run:
        try:
            resolution = svc.load_competition_resolution(case_id, str(selected_run))
        except (IntegrationRequestError, CaseWorkspaceError):
            resolution = None
    if resolution:
        st.divider()
        _render_resolution(resolution)

    measurement: dict[str, Any] | None = st.session_state.get("c7_last_measurement")
    if measurement is not None and selected_run and str(measurement.get("runId")) != selected_run:
        measurement = None
    if measurement is None and selected_run:
        try:
            measurement = svc.load_control7_measurement(case_id, str(selected_run))
        except (IntegrationRequestError, CaseWorkspaceError):
            measurement = None
    if measurement and selected_manifest:
        measured_manifest = str(
            measurement.get("expectedManifestRef") or measurement.get("manifestId") or ""
        )
        if measured_manifest and measured_manifest != str(selected_manifest):
            st.warning(
                f"Current stored measurement uses `{measured_manifest}`. "
                f"You selected `{selected_manifest}`. Run Control 7 to create "
                "a measurement for the selected manifest — the historical "
                "measurement remains unchanged."
            )
    if measurement:
        st.divider()
        st.markdown("#### Evidence drilldown")
        st.caption(
            "Which run, snapshot and manifest produced this — what matched, "
            "what was missing, what was excluded, what timing gaps existed."
        )
        _render_measurement(measurement)
        _render_drilldown(svc, case_id, measurement)
        health = svc.collection_health(case_id)
        if health.get("state") == "REPORTED":
            with st.expander("Collection health alongside this measurement", expanded=False):
                h1, h2, h3 = st.columns(3)
                h1.metric("Time quality", str(health.get("timeQuality") or "NOT_MEASURED"))
                h2.metric(
                    "Continuity",
                    str(health.get("continuityState") or "NOT_MEASURED").replace("_", " "),
                )
                h3.metric(
                    "Coverage",
                    str(health.get("coverageState") or "NOT_ASSESSED").replace("_", " "),
                )
                st.caption(
                    "Collection health is context, not part of the C7 result — "
                    "a measured sequence with partial collection still carries "
                    "that limitation."
                )
                for item in (health.get("limitations") or ())[:8]:
                    st.caption(f"- `{item}`")
        case_label = case_id or "case"
        run_label = str(measurement.get("runId") or "run")
        st.download_button(
            "Download control-7-event-recording.json",
            data=(json.dumps(measurement, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            file_name=f"{case_label}-{run_label}-control-7-event-recording.json",
            mime="application/json",
            key="c7_dl_measurement",
        )
        st.divider()
        _render_handoff(svc, case_id, run_label)
        _render_runs_matrix(svc, case_id)
