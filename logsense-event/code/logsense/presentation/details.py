from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .workbench import status_view


def relation_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render existing RelationEvaluation owners without upgrading decisions."""
    rows: list[dict[str, Any]] = []
    for item in analysis.get("relationEvaluations") or ():
        rows.append({
            "evaluationId": item.get("evaluationId"),
            "relationType": item.get("relationType"),
            "sourceRef": item.get("sourceRef"),
            "targetRef": item.get("targetRef"),
            "decision": status_view(item.get("decision")),
            "admissionBasis": item.get("admissionBasis"),
            "sourceIdentityState": status_view(item.get("sourceIdentityState")),
            "targetIdentityState": status_view(item.get("targetIdentityState")),
            "evidenceRefs": list(item.get("evidenceRefs") or ()),
            "lineageFamilies": list(item.get("lineageFamilies") or ()),
            "satisfiedConditions": list(item.get("satisfiedConditions") or ()),
            "missingConditions": list(item.get("missingConditions") or ()),
            "hardNegativesChecked": list(item.get("hardNegativesChecked") or ()),
            "limitations": list(item.get("limitations") or ()),
        })
    return sorted(rows, key=lambda row: str(row.get("evaluationId") or ""))


def state_transition_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render StateTransition owners without inferring operation attribution."""
    rows: list[dict[str, Any]] = []
    for item in analysis.get("stateTransitions") or ():
        rows.append({
            "transitionId": item.get("transitionId"),
            "subjectRef": item.get("subjectRef"),
            "property": item.get("property"),
            "before": item.get("before"),
            "after": item.get("after"),
            "effectiveAt": item.get("effectiveAt"),
            "operationAttributionState": status_view(item.get("operationAttributionState")),
            "operationEventRefs": list(item.get("operationEventRefs") or ()),
            "relationEvaluationRefs": list(item.get("relationEvaluationRefs") or ()),
            "evidenceRefs": list(item.get("evidenceRefs") or ()),
            "limitations": list(item.get("limitations") or ()),
        })
    return sorted(rows, key=lambda row: str(row.get("transitionId") or ""))


def forensic_claim_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("forensicClaims") or ():
        rows.append({
            "claimId": item.get("claimId"),
            "claimClass": item.get("claimClass"),
            "statement": item.get("statement"),
            "evidenceState": status_view(item.get("evidenceState")),
            "evidenceStrength": item.get("evidenceStrength"),
            "currentness": status_view(item.get("currentness")),
            "scopeCompleteness": status_view(item.get("scopeCompleteness")),
            "independentSourceFamilyCount": item.get("independentSourceFamilyCount"),
            "canonicalOwner": item.get("canonicalOwner"),
            "subjectRefs": list(item.get("subjectRefs") or ()),
            "evidenceRefs": list(item.get("evidenceRefs") or ()),
            "strengthBasis": list(item.get("strengthBasis") or ()),
            "notClaimed": list(item.get("notClaimed") or ()),
            "closeWith": list(item.get("closeWith") or ()),
            "limitations": list(item.get("limitations") or ()),
            "snapshotRef": item.get("snapshotRef"),
        })
    return sorted(rows, key=lambda row: str(row.get("claimId") or ""))


def evidence_card_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render resolved evidence membership; orphan refs remain explicit."""
    rows: list[dict[str, Any]] = []
    for item in report.get("evidenceCards") or ():
        rows.append({
            "claimId": item.get("claimId"),
            "membershipDigest": item.get("membershipDigest"),
            "memberCount": item.get("memberCount", 0),
            "resolvedCount": item.get("resolvedCount", 0),
            "orphanCount": item.get("orphanCount", 0),
            "resolvedEvidenceRefs": list(item.get("resolvedEvidenceRefs") or ()),
            "orphanRefs": list(item.get("orphanRefs") or ()),
            "sources": list(item.get("sources") or ()),
            "lineageFamilies": list(item.get("lineageFamilies") or ()),
            "correlationBasis": list(item.get("correlationBasis") or ()),
            "frontierViolations": list(item.get("frontierViolations") or ()),
            "limitations": list(item.get("limitations") or ()),
        })
    return sorted(rows, key=lambda row: str(row.get("claimId") or ""))


def analysis_perimeter_view(report: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the typed analysis perimeter or an explicit NOT_ASSESSED boundary."""
    perimeter = report.get("analysisPerimeterIdentity")
    forensic_case = report.get("forensicCase") or {}
    state_refs = sorted({
        str(state.get("analysisPerimeterRef"))
        for state in forensic_case.get("states") or ()
        if state.get("analysisPerimeterRef")
    })
    if isinstance(perimeter, Mapping):
        return {
            "state": "PRESENT",
            "identity": dict(perimeter),
            "caseStatePerimeterRefs": state_refs,
            "limitations": [],
        }
    return {
        "state": "NOT_ASSESSED",
        "identity": None,
        "caseStatePerimeterRefs": state_refs,
        "limitations": ["ANALYSIS_PERIMETER_IDENTITY_NOT_EMITTED"] if not perimeter else [],
    }


def cause_evaluation_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render CauseEvaluation owners without converting support into root cause."""
    rows: list[dict[str, Any]] = []
    for item in report.get("causeEvaluations") or ():
        state = str(item.get("state") or item.get("result") or "UNKNOWN")
        rows.append({
            "evaluationId": item.get("evaluationId") or item.get("causeId"),
            "ruleId": item.get("ruleId"),
            "state": status_view(state),
            "subjectRefs": list(item.get("subjectRefs") or item.get("actionGroupRefs") or ()),
            "evidenceRefs": list(item.get("evidenceRefs") or ()),
            "independentLineageFamilies": list(item.get("independentLineageFamilies") or ()),
            "gapRefs": list(item.get("gapRefs") or ()),
            "limitations": list(item.get("limitations") or ()),
            "rootCauseClaimed": False,
        })
    return sorted(rows, key=lambda row: str(row.get("evaluationId") or ""))
