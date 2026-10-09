"""Deterministic Judge Console answer composition.

Provider-independent: a routed judge question is executed against the
existing read-only investigator tools and composed into a structured
answer with an explicit answer-basis banner. Nothing here evaluates a
measurement, recomputes a verdict, or invents linkage — the tool result
is the truth, the banner only attributes it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from logsense.ai.judge_router import (
    ROUTE_ASSURANCE,
    ROUTE_FORENSIC,
    ROUTE_GAP_STATUS,
    ROUTE_MEASUREMENT,
    canonical_control_key,
    measurement_tool_for_control,
)
from logsense.ai.tools import InvestigatorToolbox
from logsense.competition.haiec_proof import (
    find_control_test_result,
    proof_chain_linkage,
)

CENTRAL_PRINCIPLE = "THE AI UNDERSTOOD THE QUESTION. IT DID NOT DECIDE THE ANSWER."

BANNERS = {
    ROUTE_FORENSIC: {
        "basis": "LOGSENSE DETERMINISTIC FORENSIC PROJECTION",
        "verdictOwner": "NONE",
        "aiRole": "question interpretation / explanation only",
        "controlVerdict": "NOT PRODUCED",
    },
    ROUTE_MEASUREMENT: {
        "basis": "LOGSENSE DETERMINISTIC MEASUREMENT",
        "verdictOwner": "HAIEC",
        "aiRole": "question interpretation / explanation only",
        "controlVerdict": "NOT PRODUCED — measurement is not a verdict",
    },
    ROUTE_ASSURANCE: {
        "basis": "IMPORTED HAIEC PERSISTED CONTROL TEST",
        "verdictOwner": "HAIEC",
        "logsenseRecomputation": "NO",
        "aiRecomputation": "NO",
    },
    ROUTE_GAP_STATUS: {
        "basis": "LOGSENSE DETERMINISTIC READINESS / GAP PROJECTION",
        "verdictOwner": "NONE",
        "aiRole": "question interpretation / explanation only",
        "controlVerdict": "NOT PRODUCED",
    },
}

_MEASUREMENT_SOURCE_KEYS = {
    "C7": "control7Measurements",
    "C9": "control9Measurements",
    "C16": "control16Measurements",
}


def measurement_for(
    competition: Mapping[str, Any], control_id: str | None, run_id: str | None
) -> dict[str, Any] | None:
    """Exact runId lookup on the deterministic measurement set — the
    side-by-side proof chain binds by identity, never by position."""
    canonical = canonical_control_key(control_id)
    if canonical is None or not run_id:
        return None
    key = _MEASUREMENT_SOURCE_KEYS.get(canonical)
    if key is None:
        return None
    rows = (competition or {}).get(key) or ()
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("runId")) == str(run_id):
            return dict(row)
    return None


def execute_judge_route(
    routed: Mapping[str, Any],
    *,
    toolbox: InvestigatorToolbox,
) -> dict[str, Any]:
    """Execute one routable judge question through the audited tool surface."""
    route = str(routed.get("route"))
    run_id = routed.get("runId")
    control_id = routed.get("controlId")
    if route == ROUTE_FORENSIC:
        result = toolbox.invoke(
            "get_forensic_window",
            run_id=run_id,
            from_time=routed.get("fromTime"),
            to_time=routed.get("toTime"),
        )
    elif route == ROUTE_ASSURANCE:
        result = toolbox.invoke(
            "get_imported_haiec_control_test_result",
            control_id=control_id,
            run_id=run_id,
            window_ref=routed.get("windowRef"),
        )
    elif route == ROUTE_MEASUREMENT:
        tool = measurement_tool_for_control(control_id)
        if tool is None:
            result = {"tool": None, "state": "NOT_FOUND", "payload": None, "citations": []}
        else:
            result = toolbox.invoke(tool, run_id=run_id)
    elif route == ROUTE_GAP_STATUS:
        result = toolbox.invoke("get_event_readiness")
    else:
        result = {"tool": None, "state": "UNKNOWN", "payload": None, "citations": []}
    return {
        "route": route,
        "banner": dict(BANNERS.get(route, {})),
        "toolResult": result,
        "routed": dict(routed),
    }


def assurance_answer(
    outcome: Mapping[str, Any],
    *,
    competition: Mapping[str, Any],
    control_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    """Compose the structured assurance answer around an imported-result
    lookup — NOT AVAILABLE fail-closed, CONFLICT visible, FOUND verbatim
    with the side-by-side measurement proof chain."""
    state = str(outcome.get("state"))
    answer: dict[str, Any] = {
        "state": state,
        "banner": dict(BANNERS[ROUTE_ASSURANCE]),
        "controlId": control_id,
        "runId": run_id,
    }
    measurement = measurement_for(competition, control_id, run_id)
    answer["measurement"] = (
        {
            "runId": measurement.get("runId"),
            "measurementState": measurement.get("measurementState"),
            "analysisRunId": measurement.get("analysisRunId"),
            "bundleId": measurement.get("bundleId"),
            "measurementDigest": measurement.get("measurementDigest"),
            "evidenceRefs": list(measurement.get("evidenceRefs") or ()),
            "limitations": list(measurement.get("limitations") or ()),
        }
        if measurement is not None
        else None
    )
    if state == "NOT_FOUND":
        answer["headline"] = "NOT AVAILABLE — IMPORT AUTHORITATIVE HAIEC CONTROL TEST RESULT"
        answer["measurementExists"] = measurement is not None
        answer["expected"] = {"controlId": control_id, "runId": run_id}
        return answer
    if state == "CONFLICT":
        answer["headline"] = "AUTHORITATIVE RESULT CONFLICT — OPERATOR REVIEW REQUIRED"
        answer["matches"] = list(outcome.get("matches") or ())
        return answer
    found = outcome.get("result") or {}
    detail = dict(found.get("detail") or {})
    answer["result"] = {
        "controlId": found.get("controlId"),
        "runId": found.get("runId"),
        "result": found.get("result"),
        "windowRef": found.get("windowRef"),
        "controlName": detail.get("controlName"),
        "controlVersionRef": detail.get("controlVersionRef"),
        "thresholdVersionRef": detail.get("thresholdVersionRef"),
        "policyDigest": detail.get("policyDigest"),
        "evaluatedAt": detail.get("evaluatedAt"),
        "reasonCodes": list(detail.get("reasonCodes") or ()),
        "evidenceRefs": list(detail.get("evidenceRefs") or ()),
        "limitations": list(detail.get("limitations") or ()),
        "calculation": detail.get("calculation"),
        "inputDigest": detail.get("inputDigest"),
        "outputDigest": detail.get("outputDigest"),
        # forward-compatible optional proof-chain fields
        "policyId": detail.get("policyId"),
        "frozenAt": detail.get("frozenAt"),
        "effectiveAt": detail.get("effectiveAt"),
        "resultId": detail.get("resultId"),
        "bundleId": detail.get("bundleId"),
        "haiecContentDigest": detail.get("haiecContentDigest"),
        "eventFreezeDigest": detail.get("eventFreezeDigest"),
        "scoredSetDigest": detail.get("scoredSetDigest"),
        "resultDigest": found.get("resultDigest"),
        "importedFrom": dict(found.get("importedFrom") or {}),
    }
    answer["linkage"] = proof_chain_linkage(measurement, found)
    return answer


def judge_answer(
    routed: Mapping[str, Any],
    *,
    toolbox: InvestigatorToolbox,
    competition: Mapping[str, Any],
) -> dict[str, Any]:
    """Full deterministic answer for a routable judge question."""
    executed = execute_judge_route(routed, toolbox=toolbox)
    if executed["route"] == ROUTE_ASSURANCE:
        composed = assurance_answer(
            (executed["toolResult"].get("payload") or {}),
            competition=competition,
            control_id=routed.get("controlId"),
            run_id=routed.get("runId"),
        )
        composed["route"] = ROUTE_ASSURANCE
        composed["toolResult"] = executed["toolResult"]
        composed["routed"] = dict(routed)
        return composed
    executed["measurement"] = measurement_for(
        competition, routed.get("controlId"), routed.get("runId")
    )
    return executed


def find_result(
    proofs: Sequence[Mapping[str, Any]], *, control_id: str, run_id: str
) -> dict[str, Any]:
    """Re-exported exact lookup for the Judge Console render path."""
    return find_control_test_result(proofs, control_id=control_id, run_id=run_id)
