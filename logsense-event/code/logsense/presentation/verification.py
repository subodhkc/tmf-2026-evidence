from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from logsense.presentation.workbench import status_view


def verification_preparation_view(prepared: Mapping[str, Any]) -> dict[str, Any]:
    """Render-safe projection of a prepared verification run."""
    evidence_set = prepared.get("evidenceSet") or {}
    prior = prepared.get("priorSnapshot") or {}
    new = prepared.get("newSnapshot") or {}
    comparison = prepared.get("comparison") or {}
    return {
        "evidenceSetId": evidence_set.get("evidenceSetId"),
        "datasetDigest": evidence_set.get("datasetDigest"),
        "priorSnapshotRef": prior.get("snapshotId"),
        "priorSnapshotDigest": prior.get("digest"),
        "newSnapshotRef": new.get("snapshotId"),
        "newSnapshotDigest": new.get("digest"),
        "availableEvidenceRefs": list(prepared.get("availableEvidenceRefs") or ()),
        "snapshotChanged": bool(comparison.get("snapshotChanged")),
        "refDeltas": comparison.get("refDeltas") or {},
        "limitations": list(prepared.get("semanticLimitations") or ()),
    }


def verification_closure_view(result: Mapping[str, Any]) -> dict[str, Any]:
    """Render-safe projection of finalized frontier verification."""
    closure = result.get("closure") or {}
    comparison = result.get("comparison") or {}
    return {
        "frontierId": closure.get("frontierId"),
        "closureState": status_view(closure.get("closureState")),
        "closureReason": closure.get("closureReason"),
        "testRunRef": closure.get("testRunRef"),
        "verificationTarget": closure.get("verificationTarget"),
        "evidenceRefs": list(closure.get("evidenceRefs") or ()),
        "priorSnapshotRef": closure.get("priorSnapshotRef"),
        "newSnapshotRef": closure.get("newSnapshotRef"),
        "predicateScope": closure.get("predicateScope"),
        "rootCauseClaimed": bool(closure.get("rootCauseClaimed")),
        "capabilityAbsentClaimed": bool(closure.get("capabilityAbsentClaimed")),
        "semanticLimitations": list(closure.get("semanticLimitations") or ()),
        "snapshotChanged": bool(comparison.get("snapshotChanged")),
        "refDeltas": comparison.get("refDeltas") or {},
    }
