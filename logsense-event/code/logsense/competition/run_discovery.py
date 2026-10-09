"""Deterministic run-candidate discovery.

Groups canonical events into candidate executions using the explicit
identifier kinds the competition run resolver already trusts. Two events join
one candidate cluster only when they share an allowlisted identifier
kind+value — timestamp proximity never establishes membership, and no
confidence score is fabricated.

Candidates are proposals for the operator: confirming one persists a real
``CompetitionRun`` declaration via the existing declaration/resolution owner.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from logsense.competition.run import (
    RUN_SCOPED_KINDS,
    event_identifiers,
    normalize_run_declaration,
    resolve_competition_run,
)

RUN_CANDIDATE_SCHEMA = "run-candidate-discovery/0.1"

# Identifier-kind strength ladder used only to label the candidate's basis —
# never a confidence score. Run-scoped identifiers are the strongest.
_BASIS_ORDER = (
    "runId",
    "scenarioRunId",
    "traceId",
    "requestId",
    "sessionId",
    "agentExecutionId",
    "modelCallId",
    "toolCallId",
    "mcpCallId",
    "mcpRequestId",
    "actionCorrelationId",
    "taskId",
    "contextId",
    "correlationId",
    "spanId",
    "parentSpanId",
)

_BASIS_LABELS = {
    "runId": "RUN_ID",
    "scenarioRunId": "RUN_ID",
    "traceId": "TRACE_BOUND",
    "requestId": "REQUEST_BOUND",
    "sessionId": "SESSION_BOUND",
    "spanId": "NESTED_CALL_IDENTIFIER",
    "parentSpanId": "NESTED_CALL_IDENTIFIER",
}

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_CANDIDATES = 10


def _basis_label(kind: str) -> str:
    return _BASIS_LABELS.get(kind, "IDENTIFIER_BOUND")


def _suggest_run_id(cluster_ids: Mapping[str, frozenset[str]]) -> str:
    """Derive a declaration-ready runId from the strongest identifier value."""
    for kind in _BASIS_ORDER:
        values = sorted(cluster_ids.get(kind) or ())
        if not values:
            continue
        raw = values[0] if kind in RUN_SCOPED_KINDS else f"{kind}:{values[0]}"
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.")[:64]
        if _RUN_ID_RE.fullmatch(candidate):
            return candidate
    return "run-candidate-1"


def _union_find_clusters(
    event_ids: dict[str, dict[str, frozenset[str]]],
) -> list[list[str]]:
    """Cluster event refs that share at least one identifier kind+value."""
    parent = {ref: ref for ref in event_ids}

    def find(ref: str) -> str:
        while parent[ref] != ref:
            parent[ref] = parent[parent[ref]]
            ref = parent[ref]
        return ref

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_identifier: dict[tuple[str, str], str] = {}
    for ref in sorted(event_ids):
        for kind, values in event_ids[ref].items():
            for value in values:
                key = (kind, value)
                if key in by_identifier:
                    union(ref, by_identifier[key])
                else:
                    by_identifier[key] = ref

    clusters: dict[str, list[str]] = {}
    for ref in sorted(event_ids):
        clusters.setdefault(find(ref), []).append(ref)
    return list(clusters.values())


def discover_run_candidates(
    canonical_events: Sequence[Mapping[str, Any]],
    *,
    declared_kinds: Sequence[str] = (),
    existing_declarations: Sequence[Mapping[str, Any]] = (),
    max_candidates: int = _MAX_CANDIDATES,
) -> dict[str, Any]:
    """Discover candidate executions from explicit event identifiers.

    Returns bounded ``run-candidate-discovery/0.1`` output. Events carrying
    no identifiers are counted but never form a candidate. Ambiguous evidence
    (conflicting run-scoped identifiers) surfaces through the resolution
    counts rather than being silently assigned.
    """
    event_rows: list[tuple[str, Mapping[str, Any], dict[str, frozenset[str]]]] = []
    for event in canonical_events:
        ref = str(event.get("eventId") or "")
        if not ref:
            continue
        event_rows.append((ref, event, event_identifiers(event, declared_kinds=declared_kinds)))

    identified = {ref: ids for ref, _e, ids in event_rows if ids}
    unidentified = [ref for ref, _e, ids in event_rows if not ids]
    clusters = _union_find_clusters(identified)

    existing_ids = {str(d.get("runId")) for d in existing_declarations if d.get("runId")}

    # Rank clusters: most events first, stable by first ref.
    clusters.sort(key=lambda members: (-len(members), members[0]))

    event_by_ref = {ref: event for ref, event, _ids in event_rows}
    candidates: list[dict[str, Any]] = []
    candidate_declarations: list[dict[str, Any]] = []
    cluster_payloads: list[tuple[list[str], dict[str, frozenset[str]], str]] = []

    for members in clusters[:max_candidates]:
        cluster_ids: dict[str, set[str]] = {}
        for ref in members:
            for kind, values in identified[ref].items():
                cluster_ids.setdefault(kind, set()).update(values)
        frozen = {kind: frozenset(values) for kind, values in cluster_ids.items()}
        suggested = _suggest_run_id(frozen)
        declaration = normalize_run_declaration(
            {
                "runId": suggested,
                "identifiers": {
                    kind: sorted(values)
                    for kind, values in frozen.items()
                    if kind not in RUN_SCOPED_KINDS or values != frozenset({suggested})
                },
            }
        )
        candidate_declarations.append(declaration)
        cluster_payloads.append((members, frozen, suggested))

    declared_others = [dict(d) for d in existing_declarations]
    for members, frozen_ids, suggested in cluster_payloads:
        declaration = next(d for d in candidate_declarations if d["runId"] == suggested)
        others = declared_others + [d for d in candidate_declarations if d["runId"] != suggested]
        resolution = resolve_competition_run(
            [event for _r, event, _i in event_rows],
            declaration,
            other_declarations=others,
        )
        times = sorted(
            str(event_by_ref[ref]["eventTime"])
            for ref in resolution["qualifiedEventRefs"]
            if event_by_ref[ref].get("eventTime")
        )
        source_refs = sorted(
            {
                str(event_by_ref[ref]["sourceRef"])
                for ref in resolution["qualifiedEventRefs"]
                if event_by_ref[ref].get("sourceRef")
            }
        )
        basis_kinds = sorted(
            frozen_ids, key=lambda k: (_BASIS_ORDER.index(k) if k in _BASIS_ORDER else 99)
        )
        basis_kind = basis_kinds[0] if basis_kinds else "identifier"
        candidates.append(
            {
                "candidateId": f"candidate:{suggested}",
                "suggestedRunId": suggested,
                "basis": _basis_label(basis_kind),
                "identifierBasis": [
                    {"kind": kind, "values": sorted(frozen_ids[kind])}
                    for kind in basis_kinds
                ],
                "declaration": declaration,
                "eventCount": len(members),
                "qualifiedCount": len(resolution["qualifiedEventRefs"]),
                "ambiguousCount": len(resolution["ambiguousEvidenceRefs"]),
                "unresolvedCount": len(resolution["unresolvedEvidenceRefs"]),
                "agentCount": len(resolution["agentIds"]),
                "sourceRefs": source_refs,
                "observedTime": (
                    {"first": times[0], "last": times[-1]} if times else None
                ),
                "resolutionState": resolution["resolutionState"],
                "alreadyDeclared": suggested in existing_ids
                or bool(set(frozen_ids.get("runId", ())) & existing_ids)
                or bool(set(frozen_ids.get("scenarioRunId", ())) & existing_ids),
                "limitations": list(resolution["limitations"]),
            }
        )

    overflow = len(clusters) - len(cluster_payloads)
    return {
        "schemaVersion": RUN_CANDIDATE_SCHEMA,
        "candidates": candidates,
        "unidentifiedEventCount": len(unidentified),
        "overflowClusterCount": max(0, overflow),
        "limitations": (
            ["CANDIDATES_REQUIRE_OPERATOR_CONFIRMATION"]
            + (["IDENTIFIER_KINDS_ALLOWLISTED_ONLY"])
            + ([f"CLUSTERS_BEYOND_DISPLAY_LIMIT:{overflow}"] if overflow > 0 else [])
        ),
    }
