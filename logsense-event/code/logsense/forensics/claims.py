from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

_STORY_CLASS = {
    "EFFECT_ENVELOPE_EXCEEDED": "CONSEQUENCE",
    "TARGET_DRIFT": "STATE_OBSERVATION",
    "TOOL_SURFACE_DRIFT": "CAPABILITY",
    "AUTHORITY_CONTINUITY_BREAK": "AUTHORITY",
    "EVIDENCE_CONTRADICTION": "GENERIC",
    "EVIDENCE_FRONTIER": "GENERIC",
    "RECOVERY_DIVERGENCE": "RECOVERY",
    "MATERIAL_CONSEQUENCE": "CONSEQUENCE",
    "DEFERRED_EXECUTION_DIVERGENCE": "ACTION_ATTRIBUTION",
    "MEDIATION_INTEGRITY_BREAK": "AUTHORITY",
}

_STRENGTH_TO_STATE = {
    "STRONG": "ESTABLISHED",
    "MODERATE": "PARTIAL",
    "WEAK": "PARTIAL",
    "CONTRADICTED": "CONTRADICTED",
    "MISSING": "UNKNOWN",
}


def _refs(values: Sequence[Any]) -> list[str]:
    return sorted({str(value) for value in values if value is not None and str(value)})


def _digest(values: Sequence[str]) -> str:
    raw = json.dumps(sorted(set(values)), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def project_forensic_claims(
    analysis: Mapping[str, Any],
    *,
    snapshot_ref: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Project material claims from existing deterministic owners only.

    InvestigationStory and CauseEvaluation remain the canonical truth owners.
    This function creates traceable read models; it never strengthens owner state.
    """
    snapshot_ref = snapshot_ref or str((analysis.get("snapshot") or {}).get("snapshotId") or "")
    claims: list[dict[str, Any]] = []

    for ordinal, story in enumerate(analysis.get("investigationStories") or (), start=1):
        family = str(story.get("family") or "")
        strength = str(story.get("evidenceStrength") or "MISSING").upper()
        state = _STRENGTH_TO_STATE.get(strength, "UNKNOWN")
        established = [str(x) for x in story.get("whatEstablished") or () if str(x)]
        statement = "; ".join(established) or str(story.get("summary") or story.get("title") or family)
        evidence_refs = _refs(story.get("evidenceRefs") or ())
        claims.append({
            "claimId": f"{story.get('storyId') or f'story:{ordinal}'}:claim",
            "claimClass": _STORY_CLASS.get(family, "GENERIC"),
            "subjectRefs": _refs(story.get("subjectRefs") or ()),
            "statement": statement,
            "canonicalOwner": {"ownerType": "InvestigationStory", "ownerRef": story.get("storyId")},
            "evidenceState": state,
            "evidenceStrength": strength if strength in {"STRONG", "MODERATE", "WEAK", "CONTRADICTED", "MISSING"} else "MISSING",
            "currentness": "UNKNOWN",
            "scopeCompleteness": "UNKNOWN",
            "independentSourceFamilyCount": None,
            "dispositiveSource": None,
            "evidenceRefs": evidence_refs,
            "strengthBasis": [f"OWNER_EVIDENCE_STRENGTH:{strength}"],
            "limitations": _refs(story.get("limitations") or ()),
            "notClaimed": _refs(story.get("notClaimed") or ()),
            "closeWith": _refs(story.get("closeWith") or ()),
            "provenance": {"storyFamily": family, "drillDownRefs": _refs(story.get("drillDownRefs") or ())},
            "snapshotRef": snapshot_ref,
        })

    for ordinal, cause in enumerate(analysis.get("causeEvaluations") or (), start=1):
        state = str(cause.get("state") or cause.get("result") or "UNKNOWN").upper()
        if state not in {"ESTABLISHED", "CORROBORATED", "SUPPORTED", "SUPPORTED_CANDIDATE", "CONTRADICTED"}:
            continue
        evidence_state = (
            "ESTABLISHED" if state in {"ESTABLISHED", "CORROBORATED", "SUPPORTED"}
            else "CONTRADICTED" if state == "CONTRADICTED"
            else "PARTIAL"
        )
        if state in {"CORROBORATED", "ESTABLISHED"}:
            strength = "STRONG"
        elif state in {"SUPPORTED", "SUPPORTED_CANDIDATE"}:
            strength = "MODERATE"
        else:
            strength = "CONTRADICTED"
        ref = str(cause.get("evaluationId") or cause.get("causeId") or f"cause:{ordinal}")
        claims.append({
            "claimId": f"{ref}:claim",
            "claimClass": "CAUSE",
            "subjectRefs": _refs(cause.get("subjectRefs") or cause.get("actionGroupRefs") or ()),
            "statement": f"cause evaluation {ref}: {state}",
            "canonicalOwner": {"ownerType": "CauseEvaluation", "ownerRef": ref},
            "evidenceState": evidence_state,
            "evidenceStrength": strength,
            "currentness": "UNKNOWN",
            "scopeCompleteness": "UNKNOWN",
            "independentSourceFamilyCount": len({str(x) for x in cause.get("independentLineageFamilies") or ()}) or None,
            "dispositiveSource": None,
            "evidenceRefs": _refs(cause.get("evidenceRefs") or ()),
            "strengthBasis": [f"CAUSE_EVALUATION_STATE:{state}"],
            "limitations": _refs(cause.get("limitations") or ()),
            "notClaimed": ["ROOT_CAUSE"] if state != "CORROBORATED" else ["ROOT_CAUSE_UNLESS_SEPARATELY_ESTABLISHED"],
            "closeWith": _refs(cause.get("gapRefs") or ()),
            "provenance": {"ruleId": cause.get("ruleId")},
            "snapshotRef": snapshot_ref,
        })

    return tuple(sorted(claims, key=lambda row: str(row["claimId"])))


def build_evidence_cards(
    analysis: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Resolve claim evidence membership without converting orphan refs to absence."""
    events = {str(row.get("eventId")): row for row in analysis.get("canonicalEvents") or () if row.get("eventId")}
    sources = {str(row.get("sourceId")): row for row in analysis.get("sourceDescriptors") or () if row.get("sourceId")}
    lineage_by_event = {
        str(key): str(value)
        for key, value in ((analysis.get("sourceIndependence") or {}).get("lineageByEvent") or {}).items()
    }
    cards: list[dict[str, Any]] = []

    for claim in claims:
        members = _refs(claim.get("evidenceRefs") or ())
        resolved: list[str] = []
        orphans: list[str] = []
        source_rows: list[dict[str, Any]] = []
        lineages: set[str] = set()
        for ref in members:
            event = events.get(ref)
            if event is None:
                orphans.append(ref)
                continue
            resolved.append(ref)
            source_ref = str(event.get("sourceRef") or "")
            source = sources.get(source_ref, {})
            lineage = lineage_by_event.get(ref) or str(source.get("lineageFamilyId") or "")
            if lineage:
                lineages.add(lineage)
            source_rows.append({
                "evidenceRef": ref,
                "sourceRef": source_ref or None,
                "producer": source.get("producer"),
                "sourceKind": source.get("sourceKind"),
                "lineageFamily": lineage or None,
                "adapterId": source.get("adapterId"),
                "adapterVersion": source.get("adapterVersion"),
            })

        limitations = {str(x) for x in claim.get("limitations") or () if str(x)}
        if orphans:
            limitations.add("ORPHAN_REF_NE_MISSING_EVIDENCE")
        if len(source_rows) > 1:
            limitations.add("SOURCE_COUNT_NE_SOURCE_INDEPENDENCE")
        cards.append({
            "claimId": claim.get("claimId"),
            "resolvedEvidenceRefs": sorted(resolved),
            "sources": sorted(source_rows, key=lambda row: row["evidenceRef"]),
            "lineageFamilies": sorted(lineages),
            "membershipDigest": _digest(members),
            "memberCount": len(members),
            "resolvedCount": len(resolved),
            "orphanCount": len(orphans),
            "orphanRefs": sorted(orphans),
            "correlationBasis": [],
            "frontierViolations": [],
            "limitations": sorted(limitations),
        })

    return tuple(sorted(cards, key=lambda row: str(row.get("claimId") or "")))


def project_claims_and_evidence_cards(analysis: Mapping[str, Any]) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    claims = project_forensic_claims(analysis)
    cards = build_evidence_cards(analysis, claims)
    card_by_claim = {str(card["claimId"]): card for card in cards}
    enriched: list[dict[str, Any]] = []
    for claim in claims:
        row = dict(claim)
        card = card_by_claim.get(str(row["claimId"]))
        if card is not None:
            row["independentSourceFamilyCount"] = len(card["lineageFamilies"])
        enriched.append(row)
    return tuple(enriched), cards
