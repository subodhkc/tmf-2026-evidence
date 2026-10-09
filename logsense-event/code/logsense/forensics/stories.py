from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _refs(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(str(x) for x in values if str(x)))


def _story(
    *,
    story_id: str,
    family: str,
    title: str,
    subject_refs: Sequence[Any],
    evidence_strength: str,
    what_established: Sequence[Any],
    expected: Any,
    observed: Any,
    divergence: str,
    why_it_matters: str,
    evidence_refs: Sequence[Any],
    drill_down_refs: Sequence[Any],
    snapshot_ref: str,
    limitations: Sequence[Any] = (),
    not_claimed: Sequence[Any] = (),
    close_with: Sequence[Any] = (),
    consequence: str | None = None,
) -> dict[str, Any]:
    return {
        "storyId": story_id,
        "family": family,
        "title": title,
        "summary": title,
        "subjectRefs": _refs(subject_refs),
        "evidenceStrength": evidence_strength,
        "whatEstablished": _refs(what_established),
        "expectedOrGoverningCondition": expected,
        "observedOrActual": observed,
        "divergence": divergence,
        "whyItMatters": why_it_matters,
        "consequence": consequence,
        "limitations": _refs(limitations),
        "notClaimed": _refs(not_claimed),
        "closeWith": _refs(close_with),
        "evidenceRefs": _refs(evidence_refs),
        "drillDownRefs": _refs(drill_down_refs),
        "snapshotRef": snapshot_ref,
    }


def project_investigation_stories(
    *,
    analysis_run_id: str,
    snapshot_ref: str,
    effect_envelopes: Sequence[Mapping[str, Any]] = (),
    delegated_action_integrity: Sequence[Mapping[str, Any]] = (),
    guardrail_mediations: Sequence[Mapping[str, Any]] = (),
    recovery_projections: Sequence[Mapping[str, Any]] = (),
    contradictions: Sequence[Mapping[str, Any]] = (),
    evidence_frontiers: Sequence[Mapping[str, Any]] = (),
) -> tuple[dict[str, Any], ...]:
    """Render bounded presentation records from existing deterministic owners."""
    rows: list[dict[str, Any]] = []
    ordinal = 1

    for item in effect_envelopes:
        if item.get("state") != "EXCEEDED":
            continue
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="EFFECT_ENVELOPE_EXCEEDED",
            title="Observed effect exceeded the explicit bound",
            subject_refs=(item.get("targetId"),),
            evidence_strength="STRONG",
            what_established=(f"{item.get('property')} effect envelope exceeded",),
            expected={"boundRef": item.get("boundRef"), "expectedLimit": item.get("expectedLimit")},
            observed={"observedDelta": item.get("observedDelta"), "state": item.get("state")},
            divergence=str(item.get("reasonCode") or "EFFECT_ENVELOPE_EXCEEDED"),
            why_it_matters="The observed effect is outside the explicitly bound operating envelope.",
            evidence_refs=item.get("evidenceRefs", ()),
            drill_down_refs=(item.get("assessmentId"), item.get("transitionRef"), item.get("boundRef")),
            snapshot_ref=snapshot_ref,
            limitations=item.get("limitations", ()),
            not_claimed=("ROOT_CAUSE",),
        ))
        ordinal += 1

    for item in delegated_action_integrity:
        if item.get("overallState") != "BROADER":
            continue
        broader = [
            str(row.get("dimension"))
            for row in item.get("dimensions", ())
            if row.get("comparison") == "BROADER"
        ]
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="AUTHORITY_CONTINUITY_BREAK",
            title="Observed action exceeded delegated scope",
            subject_refs=(item.get("actionGroupRef"),),
            evidence_strength="STRONG",
            what_established=tuple(f"{x} is broader than delegation" for x in broader),
            expected={"delegatedScopeDimensions": broader},
            observed={"overallState": item.get("overallState")},
            divergence="DELEGATED_ACTION_INTEGRITY_BROADER",
            why_it_matters="Execution crossed at least one explicitly delegated action dimension.",
            evidence_refs=item.get("evidenceRefs", ()),
            drill_down_refs=(item.get("evaluationId"),),
            snapshot_ref=snapshot_ref,
            limitations=item.get("limitations", ()),
            not_claimed=("ROOT_CAUSE", "MALICIOUS_INTENT"),
        ))
        ordinal += 1

    for item in guardrail_mediations:
        ordering_break = item.get("ordering") == "AFTER_EFFECT"
        argument_break = item.get("argumentIdentityPreserved") is False
        if not ordering_break and not argument_break:
            continue
        established: list[str] = []
        if ordering_break:
            established.append("approval/decision occurred after effect")
        if argument_break:
            established.append("approved and executed arguments differ")
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="MEDIATION_INTEGRITY_BREAK",
            title="Guardrail mediation integrity break",
            subject_refs=(item.get("actionGroupRef"),),
            evidence_strength="STRONG",
            what_established=established,
            expected={"ordering": "BEFORE_EFFECT", "argumentIdentityPreserved": True},
            observed={
                "ordering": item.get("ordering"),
                "argumentIdentityPreserved": item.get("argumentIdentityPreserved"),
            },
            divergence="MEDIATION_INTEGRITY_BREAK",
            why_it_matters="A declared guardrail cannot be treated as enforced when ordering or approved arguments diverge.",
            evidence_refs=item.get("mediationEvidenceRefs", ()),
            drill_down_refs=(item.get("mediationId"), item.get("guardrailRef")),
            snapshot_ref=snapshot_ref,
            limitations=item.get("limitations", ()),
            not_claimed=("ROOT_CAUSE", "MALICIOUS_INTENT"),
        ))
        ordinal += 1

    for item in recovery_projections:
        if item.get("state") not in {"PARTIAL", "CONTRADICTED"}:
            continue
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="RECOVERY_DIVERGENCE",
            title="Recovery evidence does not establish full restoration",
            subject_refs=item.get("recoveryActionRefs", ()),
            evidence_strength="CONTRADICTED" if item.get("state") == "CONTRADICTED" else "MODERATE",
            what_established=tuple(
                label for label, refs in (
                    ("rollback requested", item.get("rollbackRequestedRefs", ())),
                    ("rollback completed", item.get("rollbackCompletedRefs", ())),
                    ("state restored", item.get("stateRestoredRefs", ())),
                    ("service health restored", item.get("serviceHealthRestoredRefs", ())),
                    ("downstream impact resolved", item.get("downstreamImpactResolvedRefs", ())),
                ) if refs
            ),
            expected={"recoveryState": "ESTABLISHED"},
            observed={"recoveryState": item.get("state")},
            divergence="RECOVERY_DIVERGENCE",
            why_it_matters="Recovery is not complete until post-state, service-health, and impact evidence close the trajectory.",
            evidence_refs=item.get("evidenceRefs", ()),
            drill_down_refs=(item.get("recoveryId"),),
            snapshot_ref=snapshot_ref,
            limitations=item.get("limitations", ()),
            not_claimed=tuple(item.get("notClaimed", ())) + ("ROOT_CAUSE",),
        ))
        ordinal += 1

    for item in contradictions:
        if item.get("state") not in {"ESTABLISHED", "PARTIAL", "CONTRADICTED"}:
            continue
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="EVIDENCE_CONTRADICTION",
            title="Qualified evidence sources disagree",
            subject_refs=item.get("subjectRefs", ()),
            evidence_strength="STRONG" if item.get("state") == "ESTABLISHED" else "MODERATE",
            what_established=(str(item.get("claimScope") or item.get("class") or "evidence contradiction"),),
            expected={"evidenceAgreement": True},
            observed={"state": item.get("state"), "class": item.get("class")},
            divergence="EVIDENCE_CONTRADICTION",
            why_it_matters="Conflicting qualified evidence limits what can be asserted from any single source.",
            evidence_refs=item.get("evidenceRefs", ()),
            drill_down_refs=(item.get("contradictionId"),),
            snapshot_ref=snapshot_ref,
            limitations=item.get("limitations", ()),
            not_claimed=("EVIDENCE_TAMPERING", "ROOT_CAUSE"),
        ))
        ordinal += 1

    for item in evidence_frontiers:
        if item.get("state") not in {"OPEN", "TEST_DEFINED", "EVIDENCE_COLLECTED"}:
            continue
        rows.append(_story(
            story_id=f"{analysis_run_id}:story:{ordinal}",
            family="EVIDENCE_FRONTIER",
            title="Evidence frontier remains open",
            subject_refs=item.get("subjectRefs", ()),
            evidence_strength="MISSING",
            what_established=("proof boundary remains open",),
            expected=item.get("verificationRequirement"),
            observed={"missingFact": item.get("missingFact"), "state": item.get("state")},
            divergence="EVIDENCE_FRONTIER",
            why_it_matters=str(item.get("whyNeeded") or "Additional qualified evidence is required."),
            evidence_refs=item.get("currentEvidenceRefs", ()),
            drill_down_refs=(item.get("frontierId"),),
            snapshot_ref=snapshot_ref,
            not_claimed=("FINDING",),
            close_with=(item.get("verificationRequirement"),),
        ))
        ordinal += 1

    return tuple(rows)
