"""Deterministic provider-independent judge-question router.

Navigation only — it extracts explicit parameters from recognized
competition question patterns and selects a route. It never establishes
truth, never guesses missing run IDs or controls, and never evaluates a
measurement against a threshold. Anything it cannot parse safely is left
``routable=False`` so the UI can ask for the missing explicit parameter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from logsense.competition.haiec_proof import SUPPORTED_CONTROL_ALIASES

ROUTE_FORENSIC = "FORENSIC"
ROUTE_ASSURANCE = "ASSURANCE"
ROUTE_MEASUREMENT = "MEASUREMENT"
ROUTE_GAP_STATUS = "GAP-STATUS"
ROUTE_UNKNOWN = "UNKNOWN"

CONTROL_BY_NUMBER = {"7": "C7", "9": "C9", "16": "C16"}

_CONTROL_RE = re.compile(
    r"\b(?:control\s*(?:no\.?\s*|number\s*)?(7|9|16)\b|\bc\s*(7|9|16)\b|"
    r"(AIA-LOG-001|AIA-ARC-006|ACN-COST-001))",
    re.IGNORECASE,
)
_ISO_TIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_HMS_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
_BETWEEN_RE = re.compile(r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s+for\b|\s+in\b|$)", re.IGNORECASE)
_FROM_TO_RE = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:\s+for\b|\s+in\b|$)", re.IGNORECASE)

_FORENSIC_HINTS = (
    "what happened",
    "show events",
    "show actions",
    "show calls",
    "timeline",
    "what did the agent",
    "what did the agents",
    "show run",
    "show the events",
    "what events",
)
_VERDICT_HINTS = (
    "satisfied",
    "not satisfied",
    "hold",
    "did the control",
    "was the control",
    "did control",
    "was control",
    "control test",
    "verdict",
)
_MEASUREMENT_HINTS = (
    "show control",
    "show evidence for control",
    "show the evidence",
    "show measurement",
    "show the measurement",
    "evidence behind",
    "show tokens",
    "show drift",
)
_CALCULATION_HINTS = (
    "show calculation",
    "show the calculation",
    "show frozen rule",
    "show the frozen rule",
    "show policy",
    "show threshold",
)
_GAP_HINTS = (
    "unproven",
    "what remains",
    "show gaps",
    "show the gaps",
    "what is unknown",
    "what's unknown",
    "show retest",
    "what is missing",
)


def _extract_control(question: str) -> str | None:
    match = _CONTROL_RE.search(question)
    if not match:
        return None
    for group in match.groups():
        if group:
            value = group.upper()
            if value in SUPPORTED_CONTROL_ALIASES:
                return value
            return CONTROL_BY_NUMBER.get(value.lstrip("C"))
    return None


def _extract_run_id(question: str, known_run_ids: Sequence[str]) -> str | None:
    """Exact token match against known persisted run IDs only — a run is
    never guessed from prose."""
    for run_id in sorted({str(r) for r in known_run_ids if str(r)}, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(run_id)}(?![\w-])", question, re.IGNORECASE):
            return run_id
    backticked = re.search(r"`([A-Za-z0-9][\w:.-]+)`", question)
    if backticked:
        return backticked.group(1)
    return None


def _extract_times(question: str) -> tuple[str | None, str | None]:
    for pattern in (_BETWEEN_RE, _FROM_TO_RE):
        match = pattern.search(question)
        if match:
            return match.group(1).strip(), match.group(2).strip().rstrip("?.")
    times = _ISO_TIME_RE.findall(question) or _HMS_RE.findall(question)
    if len(times) >= 2:
        return times[0], times[1]
    return None, None


def route_judge_question(
    question: str,
    *,
    known_run_ids: Sequence[str] = (),
    selected_run_id: str | None = None,
) -> dict[str, Any]:
    """Route one judge question to a deterministic answer path.

    Returns the detected route plus explicitly extracted parameters and the
    list of parameters still missing. ``routable`` is true only when every
    parameter the route requires was explicit in the question or selected
    in the UI — never inferred.
    """
    text = str(question or "").strip()
    lowered = text.lower()
    control_id = _extract_control(text)
    run_id = _extract_run_id(text, known_run_ids) or selected_run_id
    from_time, to_time = _extract_times(text)

    wants_forensic = any(hint in lowered for hint in _FORENSIC_HINTS) or bool(from_time and to_time)
    wants_verdict = any(hint in lowered for hint in _VERDICT_HINTS)
    wants_measurement = any(hint in lowered for hint in _MEASUREMENT_HINTS)
    wants_calculation = any(hint in lowered for hint in _CALCULATION_HINTS)
    wants_gap = any(hint in lowered for hint in _GAP_HINTS)

    missing: list[str] = []
    if wants_verdict and control_id or wants_calculation and control_id:
        route = ROUTE_ASSURANCE
        if not run_id:
            missing.append("runId")
    elif wants_measurement and control_id:
        route = ROUTE_MEASUREMENT
        if not run_id:
            missing.append("runId")
    elif wants_gap:
        route = ROUTE_GAP_STATUS
    elif wants_forensic:
        route = ROUTE_FORENSIC
        if not run_id:
            missing.append("runId")
        if not (from_time and to_time):
            missing.append("timeWindow")
    elif control_id:
        # a bare control mention without an explicit question is never routed
        route = ROUTE_UNKNOWN
        missing.append("questionIntent")
    else:
        route = ROUTE_UNKNOWN
        missing.append("questionIntent")
        if not run_id:
            missing.append("runId")
        if not control_id:
            missing.append("controlId")

    return {
        "route": route,
        "routable": route != ROUTE_UNKNOWN and not missing,
        "question": text,
        "runId": run_id,
        "controlId": control_id,
        "fromTime": from_time,
        "toTime": to_time,
        "windowRef": None,
        "missing": missing,
        "explicit": {
            "runId": _extract_run_id(text, known_run_ids) is not None,
            "controlId": control_id is not None,
            "timeWindow": from_time is not None and to_time is not None,
        },
    }


def canonical_control_key(control_id: str | None) -> str | None:
    """Resolve a control identity to its C-number — exact alias only."""
    value = str(control_id or "").upper()
    if value in {"C7", "C9", "C16"}:
        return value
    resolved = SUPPORTED_CONTROL_ALIASES.get(value)
    return resolved if resolved in {"C7", "C9", "C16"} else (value or None)


def measurement_tool_for_control(control_id: str | None) -> str | None:
    """Map a control identity to its deterministic measurement tool."""
    key = canonical_control_key(control_id)
    if key is None:
        return None
    return {
        "C7": "get_control7_event_measurement",
        "C9": "get_control9_drift_measurement",
        "C16": "get_control16_usage_measurement",
    }.get(key)


def judge_context(proofs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compact proof-state for the deterministic router/UI header."""
    from logsense.competition.haiec_proof import imported_proof_summary

    return imported_proof_summary(proofs)
