from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from logsense.ai.session import InvestigatorTurn


def investigator_scope_summary(
    analysis: Mapping[str, Any] | None,
    report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a bounded read-only summary of the loaded investigator scope."""
    analysis = analysis or {}
    report = report or {}
    return {
        "caseId": report.get("caseId") or analysis.get("caseId"),
        "analysisRunId": report.get("analysisRunId") or analysis.get("analysisRunId"),
        "evidenceSetId": report.get("evidenceSetId") or analysis.get("evidenceSetId"),
        "reportDigest": report.get("reportDigest"),
        "claimCount": len(report.get("forensicClaims") or analysis.get("forensicClaims") or ()),
        "storyCount": len(report.get("investigationStories") or analysis.get("investigationStories") or ()),
        "openFrontierCount": sum(
            1
            for item in report.get("evidenceFrontier") or analysis.get("evidenceFrontier") or ()
            if isinstance(item, Mapping)
            and str(item.get("state") or "OPEN").upper() in {"OPEN", "TEST_DEFINED", "EVIDENCE_COLLECTED"}
        ),
        "limitations": list(report.get("limitations") or analysis.get("limitations") or ()),
        "canonicalMutationAllowed": False,
    }


def investigator_turn_view(turn: InvestigatorTurn) -> dict[str, Any]:
    """Project one audited investigator turn without strengthening provider output."""
    answer = turn.answer
    tool_results: Sequence[Mapping[str, Any]] = turn.tool_results
    return {
        "question": turn.question,
        "answer": answer.text,
        "citations": list(answer.citations),
        "uncertainty": list(answer.uncertainty),
        "provider": answer.provider,
        "toolCalls": list(answer.tool_calls),
        "toolResultCount": len(tool_results),
        "toolStates": [
            {
                "tool": item.get("tool"),
                "state": item.get("state"),
                "citations": list(item.get("citations") or ()),
                "contentTrust": item.get("contentTrust"),
                "canonicalMutationAllowed": item.get("canonicalMutationAllowed"),
            }
            for item in tool_results
        ],
        "canonicalMutationAllowed": False,
    }
