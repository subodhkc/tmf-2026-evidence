from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from logsense.forensics.claims import project_claims_and_evidence_cards

_PRESENTATION_KEYS = {"renderedAt", "renderTimestamp", "uiState", "currentTime", "processId", "llmText"}
_ROOT_CAUSE_TOKENS = {"ROOT_CAUSE", "ROOT_CAUSE_ESTABLISHED"}


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _PRESENTATION_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, set):
        return sorted(_stable(item) for item in value)
    return value


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _refs(values: Sequence[Any]) -> list[str]:
    return sorted({str(value) for value in values if value is not None and str(value)})


def _rows(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _story_nonclaims(stories: Sequence[Mapping[str, Any]]) -> list[str]:
    return _refs([item for story in stories for item in story.get("notClaimed", ())])


def _what_established(analysis: Mapping[str, Any]) -> list[str]:
    established: list[str] = []
    for story in _rows(analysis.get("investigationStories")):
        established.extend(str(item) for item in story.get("whatEstablished", ()) if str(item))
    for cause in _rows(analysis.get("causeEvaluations")):
        state = str(cause.get("state") or cause.get("result") or "")
        if state in {"ESTABLISHED", "SUPPORTED", "CORROBORATED"}:
            ref = cause.get("evaluationId") or cause.get("causeId") or state
            established.append(f"cause evaluation {ref}: {state}")
    return _refs(established)


def _what_not_established(analysis: Mapping[str, Any], forensic_case: Mapping[str, Any] | None) -> list[str]:
    rows = set(_story_nonclaims(_rows(analysis.get("investigationStories"))))
    rows.update({
        "DIVERGENCE_NE_ROOT_CAUSE",
        "EARLIEST_TRUST_BREAK_NE_ROOT_CAUSE",
        "EVIDENCE_CONTRADICTION_NE_EVIDENCE_TAMPERING",
        "FRONTIER_NE_FINDING",
        "RECOVERY_COMPLETED_NE_STATE_RESTORED",
        "STATE_RESTORED_NE_IMPACT_RESOLVED",
        "EFFECT_ENVELOPE_EXCEEDED_NE_ROOT_CAUSE",
        "BROADER_DAI_NE_ROOT_CAUSE",
        "STORY_NE_FORENSIC_FACT",
        "MISSING_EVIDENCE_NE_PROVEN_ABSENCE",
    })
    if forensic_case and forensic_case.get("firstDeterministicDivergence"):
        rows.add("FIRST_DIVERGENCE_NE_ROOT_CAUSE")
    return sorted(rows)


def _verification_actions(frontiers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in frontiers:
        if item.get("state") not in {None, "OPEN", "TEST_DEFINED", "EVIDENCE_COLLECTED"}:
            continue
        rows.append({
            "frontierId": item.get("frontierId"),
            "priority": item.get("priority"),
            "missingFact": item.get("missingFact"),
            "verificationRequirement": item.get("verificationRequirement"),
            "proposedTestRef": item.get("proposedTestRef"),
            "currentEvidenceRefs": _refs(item.get("currentEvidenceRefs", ())),
        })
    return sorted(rows, key=lambda row: str(row.get("frontierId") or ""))


def _case_summary(forensic_case: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not forensic_case:
        return None
    states = sorted(_rows(forensic_case.get("states")), key=lambda row: int(row.get("scenarioSequence", 0)))
    transitions = _rows(forensic_case.get("transitions"))
    return {
        "caseId": forensic_case.get("caseId"),
        "scenarioId": forensic_case.get("scenarioId"),
        "caseDigest": forensic_case.get("caseDigest"),
        "states": [{
            "stateId": state.get("stateId"),
            "stateLabel": state.get("stateLabel"),
            "scenarioSequence": state.get("scenarioSequence"),
            "evidenceSetId": state.get("evidenceSetId"),
            "analysisRunId": state.get("analysisRunId"),
            "snapshotDigest": state.get("snapshotDigest"),
            "analysisPerimeterRef": state.get("analysisPerimeterRef"),
            "evidenceRefs": _refs(state.get("evidenceRefs", ())),
            "evidenceFrontierRefs": _refs(state.get("evidenceFrontierRefs", ())),
            "limitations": _refs(state.get("limitations", ())),
        } for state in states],
        "transitions": [{
            "fromStateId": row.get("fromStateId"),
            "toStateId": row.get("toStateId"),
            "availability": row.get("availability"),
            "comparisonDigest": row.get("comparisonDigest"),
            "divergenceRefs": _refs(row.get("divergenceRefs", ())),
            "divergenceKinds": _refs(row.get("divergenceKinds", ())),
            "dimensions": _refs(row.get("dimensions", ())),
            "proofRefs": _refs(row.get("proofRefs", ())),
            "gapRefs": _refs(row.get("gapRefs", ())),
            "limitations": _refs(row.get("limitations", ())),
        } for row in transitions],
        "firstQualifiedDivergence": forensic_case.get("firstDeterministicDivergence"),
        "unresolvedRefs": _refs(forensic_case.get("unresolvedRefs", ())),
        "limitations": _refs(forensic_case.get("limitations", ())),
    }


def build_deterministic_forensic_report(
    analysis: Mapping[str, Any],
    *,
    forensic_case: Mapping[str, Any] | None = None,
    schema_version: str = "1.0",
    rendered_at: str | None = None,
) -> dict[str, Any]:
    """Project canonical LogSense outputs into one deterministic forensic report.

    This function never establishes new evidence, causality, authority, tampering,
    recovery, or root-cause state. It only organizes already-established owners.
    Presentation-only metadata is excluded from the semantic report digest.
    """
    stories = _rows(analysis.get("investigationStories"))
    frontiers = _rows(analysis.get("evidenceFrontier"))
    case_summary = _case_summary(forensic_case)
    projected_claims, projected_cards = project_claims_and_evidence_cards(analysis)
    forensic_claims = _rows(analysis.get("forensicClaims")) or [dict(row) for row in projected_claims]
    evidence_cards = _rows(analysis.get("evidenceCards")) or [dict(row) for row in projected_cards]

    semantic: dict[str, Any] = {
        "schemaVersion": schema_version,
        "caseId": analysis.get("caseId"),
        "evidenceSetId": analysis.get("evidenceSetId"),
        "analysisRunId": analysis.get("analysisRunId"),
        "snapshot": analysis.get("snapshot"),
        "analysisPerimeterIdentity": analysis.get("analysisPerimeterIdentity"),
        "forensicCase": case_summary,
        "collectionHealth": analysis.get("sourceCoverage"),
        "materialDivergences": _rows(analysis.get("divergences")),
        "causeEvaluations": _rows(analysis.get("causeEvaluations")),
        "gapFindings": _rows(analysis.get("gaps")),
        "delegatedActionIntegrity": _rows(analysis.get("delegatedActionIntegrity")),
        "effectEnvelopeAssessments": _rows(analysis.get("effectEnvelopeAssessments")),
        "guardrailMediations": _rows(analysis.get("guardrailMediations")),
        "recoveryProjections": _rows(analysis.get("recoveryProjections")),
        "evidenceContradictions": _rows(analysis.get("contradictions")),
        "evidenceFrontier": frontiers,
        "investigationStories": stories,
        "forensicClaims": forensic_claims,
        "evidenceCards": evidence_cards,
        "sourceDescriptors": _rows(analysis.get("sourceDescriptors")),
        "whatEstablished": _what_established(analysis),
        "whatNotEstablished": _what_not_established(analysis, forensic_case),
        "verificationActions": _verification_actions(frontiers),
        "limitations": _refs(analysis.get("limitations", ())),
    }

    serialized = json.dumps(_stable(semantic), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if any(token in serialized for token in _ROOT_CAUSE_TOKENS):
        for cause in semantic["causeEvaluations"]:
            if cause.get("state") in {"ROOT_CAUSE", "ROOT_CAUSE_ESTABLISHED"}:
                raise ValueError("report projection cannot promote a cause evaluation to root cause")

    return {
        **semantic,
        "reportDigest": _digest(semantic),
        "note": (
            "Deterministic projection of canonical analysis — no new claims are "
            "established here. 'whatEstablished' and 'whatNotEstablished' bound "
            "what the evidence supports; 'limitations' list the bounds. "
            "'reportDigest' covers the semantic fields only; 'presentation' is "
            "display-only metadata. Measurement files keep verdict null — "
            "governance verdicts belong to the evaluator (e.g. HAIEC)."
        ),
        "presentation": {"renderedAt": rendered_at} if rendered_at is not None else {},
    }


def build_report_from_analysis(
    analysis: Mapping[str, Any],
    *,
    forensic_case: Mapping[str, Any] | None = None,
    rendered_at: str | None = None,
) -> dict[str, Any]:
    """Application-service entry point for UI/API/MCP/AI consumers."""
    return build_deterministic_forensic_report(analysis, forensic_case=forensic_case, rendered_at=rendered_at)
