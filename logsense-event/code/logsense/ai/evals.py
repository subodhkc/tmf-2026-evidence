from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from logsense.ai.provider import InvestigatorAnswer

_POSITIVE_CAUSAL_PATTERNS = (
    re.compile(r"\b(?:is|was)\s+(?:the\s+)?root cause\b", re.I),
    re.compile(r"\bcaused\b", re.I),
    re.compile(r"\bdue to\b", re.I),
)
_NEGATION_PREFIX = re.compile(r"(?:\bnot\b|\bno\b|\bnever\b|\bwithout\b)[^.!?]{0,32}$", re.I)
_CAUSAL_STATES = {"ESTABLISHED", "CORROBORATED"}


@dataclass(frozen=True)
class GoldenAgentEvalResult:
    case_id: str
    passed: bool
    false_causal_attributions: int
    unknown_citations: tuple[str, ...]
    missing_citation: bool
    missing_uncertainty: bool
    violations: tuple[str, ...]


def deterministic_reference_inventory(expected: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                walk(child, key)
        elif value is not None and key and (key.endswith("Id") or key.endswith("Ref")) or value is not None and key and key.endswith("Refs"):
            refs.add(str(value))

    walk(expected)
    return refs


def established_causal_refs(expected: Mapping[str, Any]) -> set[str]:
    """Return exact cause/evaluation refs that may support positive causal prose."""
    refs: set[str] = set()
    for evaluation in expected.get("cause_evaluations") or ():
        candidate = evaluation.get("candidate") or {}
        state = str(evaluation.get("resultState") or "").upper()
        candidate_state = str(candidate.get("establishmentState") or "").upper()
        if state not in _CAUSAL_STATES and candidate_state not in _CAUSAL_STATES:
            continue
        if evaluation.get("evaluationId"):
            refs.add(str(evaluation["evaluationId"]))
        if candidate.get("causeId"):
            refs.add(str(candidate["causeId"]))
    return refs


def case_has_established_causal_mechanism(expected: Mapping[str, Any]) -> bool:
    return bool(established_causal_refs(expected))


def count_positive_causal_attributions(text: str) -> int:
    count = 0
    for pattern in _POSITIVE_CAUSAL_PATTERNS:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 40):match.start()]
            if _NEGATION_PREFIX.search(prefix):
                continue
            count += 1
    return count


def evaluate_golden_answer(
    *,
    case_id: str,
    answer: InvestigatorAnswer,
    expected: Mapping[str, Any],
    require_uncertainty: bool = False,
    require_citation: bool = True,
) -> GoldenAgentEvalResult:
    """Evaluate model prose against deterministic Golden boundaries.

    This is a regression gate, not a truth engine. It rejects citations outside
    frozen expected references. Positive causal language is allowed only when
    the answer cites a cause/evaluation that the deterministic Golden oracle
    itself marks ESTABLISHED or CORROBORATED; unrelated established causes do
    not license causal claims about another mechanism.
    """
    inventory = deterministic_reference_inventory(expected)
    citations = {str(x) for x in answer.citations if str(x)}
    unknown = tuple(sorted(citations - inventory))
    causal_count = count_positive_causal_attributions(answer.text)
    causal_refs = established_causal_refs(expected)
    false_causal = causal_count if causal_count and not (citations & causal_refs) else 0
    missing_citation = require_citation and bool(answer.text.strip()) and not citations
    missing_uncertainty = require_uncertainty and not any(str(x).strip() for x in answer.uncertainty)
    violations: list[str] = []
    if unknown:
        violations.append("UNKNOWN_CITATION")
    if missing_citation:
        violations.append("MISSING_CITATION")
    if false_causal:
        violations.append("FALSE_CAUSAL_ATTRIBUTION")
    if missing_uncertainty:
        violations.append("MISSING_UNCERTAINTY")
    return GoldenAgentEvalResult(
        case_id=case_id,
        passed=not violations,
        false_causal_attributions=false_causal,
        unknown_citations=unknown,
        missing_citation=missing_citation,
        missing_uncertainty=missing_uncertainty,
        violations=tuple(violations),
    )
