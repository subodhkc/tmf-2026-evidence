from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_WORKFLOW = (
    "CASE", "GATHER", "MANIFEST", "EVIDENCE", "EXPLORE", "TIMELINE",
    "ACTIONS", "COMPARE", "FINDINGS", "PROOF", "REPORT",
)

_STATUS_LABELS = {
    "UNKNOWN": "Unknown", "NOT_ASSESSED": "Not assessed", "PARTIAL": "Partial",
    "CONTRADICTED": "Contradicted", "INCOMPARABLE": "Incomparable",
    "MISSING": "Missing evidence", "PRESENT": "Present", "ESTABLISHED": "Established",
    "SUPPORTED": "Supported", "OPEN": "Open", "TEST_DEFINED": "Test defined",
    "EVIDENCE_COLLECTED": "Evidence collected", "CLOSED": "Closed",
}


def workflow_steps() -> tuple[str, ...]:
    return _WORKFLOW


def status_view(status: Any) -> dict[str, str]:
    normalized = str(status or "UNKNOWN").strip().upper() or "UNKNOWN"
    return {
        "state": normalized,
        "label": _STATUS_LABELS.get(normalized, normalized.replace("_", " ").title()),
        "semanticClass": (
            "uncertain" if normalized in {"UNKNOWN", "NOT_ASSESSED", "PARTIAL", "INCOMPARABLE", "MISSING"}
            else "contradicted" if normalized == "CONTRADICTED"
            else "established" if normalized in {"PRESENT", "ESTABLISHED", "SUPPORTED", "CLOSED"}
            else "open"
        ),
    }


def manifest_rows(manifest: Any) -> list[dict[str, Any]]:
    entries = getattr(manifest, "entries", None)
    if entries is None and isinstance(manifest, Mapping):
        entries = manifest.get("entries", ())
    rows: list[dict[str, Any]] = []
    for entry in entries or ():
        if isinstance(entry, Mapping):
            get = entry.get
        else:
            def get(key: str, default: Any = None, obj: Any = entry) -> Any:
                return getattr(obj, key, default)
        limitations = get("limitations", ()) or ()
        rows.append({
            "path": get("logical_path", get("logicalPath", "")),
            "sizeBytes": get("size_bytes", get("sizeBytes", 0)),
            "sha256": get("sha256", ""),
            "format": get("format_family", get("formatFamily", "opaque")),
            "adapterId": get("adapter_id", get("adapterId", "")),
            "limitations": sorted({str(x) for x in limitations if str(x)}),
        })
    return sorted(rows, key=lambda row: str(row["path"]))


def report_overview(report: Mapping[str, Any]) -> dict[str, Any]:
    forensic_case = report.get("forensicCase") or {}
    states = list(forensic_case.get("states") or ())
    transitions = list(forensic_case.get("transitions") or ())
    stories = list(report.get("investigationStories") or ())
    frontiers = list(report.get("evidenceFrontier") or ())
    contradictions = list(report.get("evidenceContradictions") or ())
    return {
        "caseId": report.get("caseId"), "analysisRunId": report.get("analysisRunId"),
        "reportDigest": report.get("reportDigest"), "scenarioStates": states,
        "transitions": transitions, "whatEstablished": list(report.get("whatEstablished") or ()),
        "whatNotEstablished": list(report.get("whatNotEstablished") or ()),
        "storyCount": len(stories),
        "openFrontierCount": sum(1 for item in frontiers if item.get("state") in {None, "OPEN", "TEST_DEFINED", "EVIDENCE_COLLECTED"}),
        "contradictionCount": len(contradictions), "limitations": list(report.get("limitations") or ()),
    }


def proof_frontier_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [{
        "frontierId": item.get("frontierId"), "state": status_view(item.get("state")),
        "missingFact": item.get("missingFact"), "whyNeeded": item.get("whyNeeded"),
        "verificationRequirement": item.get("verificationRequirement"),
        "currentEvidenceRefs": list(item.get("currentEvidenceRefs") or ()),
        "proposedTestRef": item.get("proposedTestRef"), "isFinding": False,
    } for item in report.get("evidenceFrontier") or ()]
    return sorted(rows, key=lambda row: str(row.get("frontierId") or ""))


def timeline_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [{
        "timelineEventId": item.get("timelineEventId"), "eventRef": item.get("eventRef"),
        "eventTime": item.get("eventTime") or item.get("normalizedTime"),
        "normalizedTime": item.get("normalizedTime"),
        "clockDomainRef": item.get("clockDomainRef"),
        "orderingBasis": item.get("orderingBasis"), "limitations": list(item.get("limitations") or ()),
        "semanticClass": item.get("semanticClass"),
        "actionGroupRef": item.get("actionGroupRef"),
        "sequenceIndex": item.get("sequenceIndex"),
        "sourceRefs": list(item.get("sourceRefs") or ()),
        "evidenceRefs": list(item.get("evidenceRefs") or ()),
        "timeQuality": item.get("timeQuality"),
    } for item in analysis.get("timelineEvents") or ()]
    # Clock domain lives on the temporal normalization record, not the
    # timeline event — join by eventRef so the UI can surface it where it
    # exists. Pure projection over canonical fields; no schema change.
    domain_by_event = {
        str(n.get("eventRef")): n.get("clockDomainRef")
        for n in analysis.get("temporalNormalizations") or ()
    }
    for row in rows:
        if row["clockDomainRef"] is None:
            row["clockDomainRef"] = domain_by_event.get(str(row["eventRef"]))
    return rows


def evidence_inventory_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [{
        "sourceId": item.get("sourceId"), "sourceKind": item.get("sourceKind"),
        "producer": item.get("producer"), "adapterId": item.get("adapterId"),
        "adapterVersion": item.get("adapterVersion"), "integrity": status_view(item.get("integrityState")),
        "completeness": status_view(item.get("completenessState")),
        "currentness": status_view(item.get("currentness")),
        "limitations": list(item.get("limitations") or ()),
    } for item in analysis.get("sourceDescriptors") or ()]
    return sorted(rows, key=lambda row: str(row.get("sourceId") or ""))


def action_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    lifecycle_by_action = {str(row.get("actionGroupRef")): row for row in analysis.get("actionLifecycleCoverage") or ()}
    five_plane_by_action = {str(row.get("actionGroupRef")): row for row in analysis.get("fivePlaneCoverage") or ()}
    rows = []
    for action in analysis.get("actionGroups") or ():
        ref = str(action.get("actionGroupId") or "")
        rows.append({
            "actionGroupId": ref,
            "canonicalOperation": (action.get("actionIdentity") or {}).get("canonicalOperation"),
            "identityState": status_view((action.get("actionIdentity") or {}).get("identityState")),
            "eventRefs": list(action.get("eventRefs") or ()), "lifecycle": lifecycle_by_action.get(ref),
            "fivePlaneCoverage": five_plane_by_action.get(ref), "limitations": list(action.get("limitations") or ()),
        })
    return rows


def artifact_profile_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose adapter/profile facts exactly as emitted by the analysis spine."""
    unresolved = {str(x.get("artifactId")): x for x in analysis.get("unresolvedArtifacts") or ()}
    rows = []
    for item in analysis.get("artifactResults") or ():
        artifact_id = str(item.get("artifactId") or "")
        unresolved_row = unresolved.get(artifact_id)
        rows.append({
            "artifactId": artifact_id, "path": item.get("path"), "sha256": item.get("sha256"),
            "syntaxAdapterId": item.get("syntaxAdapterId"), "format": item.get("format"),
            "profileState": status_view(item.get("profileState")),
            "schemaProfileRef": item.get("schemaProfileRef"),
            "semanticProfileIds": list(item.get("semanticProfileIds") or ()),
            "recordCount": item.get("recordCount"), "parsedRecordCount": item.get("parsedRecordCount"),
            "failedRecordCount": item.get("failedRecordCount"),
            "canonicalEventCount": item.get("canonicalEventCount"),
            "mappingState": status_view("NOT_ASSESSED" if unresolved_row else "ESTABLISHED"),
            "mappingReason": (unresolved_row or {}).get("reason"),
            "limitations": list(item.get("limitations") or ()),
        })
    return sorted(rows, key=lambda row: (str(row.get("path") or ""), row["artifactId"]))


def mapping_proposal_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose proposals as proposals; never turn them into approved mappings."""
    rows = []
    for item in analysis.get("mappingProposals") or ():
        rows.append({
            "proposalId": item.get("proposalId"), "artifactId": item.get("artifactId"),
            "path": item.get("path"), "sha256": item.get("sha256"),
            "templateProfileId": item.get("templateProfileId"),
            "syntaxAdapterId": item.get("syntaxAdapterId"),
            "semanticProfileIds": list(item.get("semanticProfileIds") or ()),
            "format": item.get("format"), "sourcePaths": list(item.get("sourcePaths") or ()),
            "basis": list(item.get("basis") or ()), "limitations": list(item.get("limitations") or ()),
            "approvalState": status_view("NOT_ASSESSED"), "autoApproved": False,
        })
    return sorted(rows, key=lambda row: str(row.get("proposalId") or ""))


def qualification_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in analysis.get("sourceQualifications") or ():
        rows.append({
            "qualificationId": item.get("qualificationId"), "sourceRef": item.get("sourceRef"),
            "profileId": item.get("profileId"), "claimClass": item.get("claimClass"),
            "decision": item.get("decision"), "subjectBinding": item.get("subjectBinding"),
            "basis": list(item.get("basis") or ()), "evidenceRefs": list(item.get("evidenceRefs") or ()),
            "gapRefs": list(item.get("gapRefs") or ()), "limitations": list(item.get("limitations") or ()),
        })
    return sorted(rows, key=lambda row: (str(row.get("sourceRef") or ""), str(row.get("claimClass") or ""), str(row.get("qualificationId") or "")))


def semantic_drilldown(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """One read-only projection for the PR-12 Explore/Profile surface."""
    sources = list(analysis.get("sourceDescriptors") or ())
    producers = sorted({str(row.get("producer")) for row in sources if row.get("producer")})
    provenance = [{
        "artifactId": row.get("artifactId"), "path": row.get("path"),
        "sha256": row.get("sha256"), "adapterId": row.get("syntaxAdapterId"),
        "schemaProfileRef": row.get("schemaProfileRef"), "semanticProfileIds": row.get("semanticProfileIds"),
    } for row in artifact_profile_rows(analysis)]
    return {
        "externalProducers": producers,
        "artifacts": artifact_profile_rows(analysis),
        "mappingProposals": mapping_proposal_rows(analysis),
        "qualifications": qualification_rows(analysis),
        "provenancePath": provenance,
        "upstreamRule": analysis.get("upstreamRule") if analysis.get("upstreamRule") is not None else {"state": "NOT_ASSESSED"},
        "definitionDelta": analysis.get("definitionDelta") if analysis.get("definitionDelta") is not None else {"state": "NOT_ASSESSED"},
        "limitations": list(analysis.get("limitations") or ()),
    }


def workbench_summary(analysis: Mapping[str, Any] | None, report: Mapping[str, Any] | None) -> dict[str, Any]:
    analysis = analysis or {}
    report = report or {}
    return {
        "workflow": list(_WORKFLOW), "caseId": report.get("caseId") or analysis.get("caseId"),
        "analysisRunId": report.get("analysisRunId") or analysis.get("analysisRunId"),
        "evidence": evidence_inventory_rows(analysis), "explore": semantic_drilldown(analysis),
        "timeline": timeline_rows(analysis), "actions": action_rows(analysis),
        "report": report_overview(report) if report else None,
        "proofFrontier": proof_frontier_rows(report) if report else [],
    }
