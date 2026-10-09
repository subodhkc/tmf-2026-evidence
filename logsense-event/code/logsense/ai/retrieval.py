from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:/-]+")
_MAX_TOP_K = 8

# Retrieval is intentionally limited to deterministic typed read projections.
_TYPED_SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("forensicClaim", "forensicClaims", ("claimId",)),
    ("evidenceCard", "evidenceCards", ("claimId",)),
    ("investigationStory", "investigationStories", ("storyId",)),
    ("investigationInsight", "investigationInsights", ("insightId",)),
    ("trustBreakCandidate", "trustBreakCandidates", ("candidateId",)),
    ("recoveryProjection", "recoveryProjections", ("recoveryId",)),
    ("executionArchetype", "executionArchetypes", ("archetypeId", "actionGroupRef")),
    ("delegatedActionIntegrity", "delegatedActionIntegrity", ("evaluationId", "actionGroupRef")),
    ("effectEnvelope", "effectEnvelopeAssessments", ("assessmentId", "actionGroupRef")),
    ("guardrailMediation", "guardrailMediation", ("mediationId", "actionGroupRef")),
    ("adapterQualification", "adapterQualifications", ("adapterId",)),
    ("evidenceFrontier", "evidenceFrontier", ("frontierId",)),
)


@dataclass(frozen=True)
class RetrievalCandidate:
    object_type: str
    ref: str
    lexical_score: float
    semantic_score: float | None
    combined_score: float
    matched_tokens: tuple[str, ...]


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(value) if len(token) > 1}


def _flatten_search_text(value: Any, *, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(value, Mapping):
        return " ".join(_flatten_search_text(child, depth=depth + 1) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_flatten_search_text(child, depth=depth + 1) for child in value)
    if value is None:
        return ""
    return str(value)


def _identity(row: Mapping[str, Any], identity_fields: Sequence[str]) -> str | None:
    for field in identity_fields:
        if row.get(field) is not None and str(row[field]):
            return str(row[field])
    return None


class BoundedRetrievalIndex:
    """Deterministic routing index over typed read-only projections.

    Retrieval candidates are hints only. They contain no raw evidence payload and
    cannot be cited as forensic evidence. A provider must call an exact LogSense
    read tool before any reference becomes citation-eligible.
    """

    def __init__(self, *, analysis: Mapping[str, Any] | None = None, report: Mapping[str, Any] | None = None):
        self._analysis = dict(analysis or {})
        self._report = dict(report or {})
        self._rows = self._build_rows()

    def _source(self, key: str) -> Any:
        if key in self._report:
            return self._report[key]
        return self._analysis.get(key)

    def _build_rows(self) -> tuple[tuple[str, str, set[str]], ...]:
        rows: list[tuple[str, str, set[str]]] = []
        for object_type, key, identity_fields in _TYPED_SOURCES:
            source = self._source(key)
            if isinstance(source, Mapping):
                source = [source]
            for row in source or ():
                if not isinstance(row, Mapping):
                    continue
                ref = _identity(row, identity_fields)
                if not ref:
                    continue
                rows.append((object_type, ref, _tokens(_flatten_search_text(row))))
        return tuple(sorted(rows, key=lambda item: (item[0], item[1])))

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        semantic_scorer: Callable[[str, str, str], float | None] | None = None,
        semantic_weight: float = 0.25,
    ) -> tuple[RetrievalCandidate, ...]:
        if not query.strip():
            return ()
        if top_k < 1 or top_k > _MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {_MAX_TOP_K}")
        if semantic_weight < 0 or semantic_weight > 0.5:
            raise ValueError("semantic_weight must be between 0 and 0.5")

        query_tokens = _tokens(query)
        candidates: list[RetrievalCandidate] = []
        for object_type, ref, row_tokens in self._rows:
            matched = tuple(sorted(query_tokens & row_tokens))
            lexical = len(matched) / max(1, len(query_tokens))
            semantic = semantic_scorer(query, object_type, ref) if semantic_scorer else None
            if semantic is not None and not 0 <= semantic <= 1:
                raise ValueError("semantic scorer must return a value in [0, 1] or None")
            if lexical <= 0 and (semantic is None or semantic <= 0):
                continue
            combined = lexical if semantic is None else (1 - semantic_weight) * lexical + semantic_weight * semantic
            candidates.append(
                RetrievalCandidate(
                    object_type=object_type,
                    ref=ref,
                    lexical_score=round(lexical, 6),
                    semantic_score=None if semantic is None else round(semantic, 6),
                    combined_score=round(combined, 6),
                    matched_tokens=matched,
                )
            )
        candidates.sort(key=lambda row: (-row.combined_score, row.object_type, row.ref))
        return tuple(candidates[:top_k])


def routing_hint(candidates: Sequence[RetrievalCandidate]) -> str:
    """Serialize safe routing metadata only; no evidence text is included."""
    if not candidates:
        return "No typed retrieval candidates were found. Use read-only tools to inspect deterministic projections."
    lines = ["Typed routing candidates (NOT evidence; call exact tools before citing):"]
    for row in candidates:
        lines.append(f"- {row.object_type}: {row.ref} (routing_score={row.combined_score:.3f})")
    return "\n".join(lines)
