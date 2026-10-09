from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from logsense.analysis.spine import ArtifactEvidence


class EvidenceSetContractError(ValueError):
    """Raised when an EvidenceSet cannot be built without ambiguity."""


def _dataset_digest(artifacts: Sequence[ArtifactEvidence]) -> str:
    rows = [
        {
            "artifactRef": str(a.artifact_id),
            "path": str(a.path),
            "sha256": hashlib.sha256(a.content).hexdigest(),
        }
        for a in artifacts
    ]
    payload = json.dumps(sorted(rows, key=lambda x: (x["artifactRef"], x["path"], x["sha256"])), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_evidence_set(
    artifacts: Sequence[ArtifactEvidence],
    *,
    evidence_set_id: str,
    case_id: str,
    label: str,
    role: str,
    imported_at: str,
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the frozen EvidenceSet read contract from admitted artifacts.

    The dataset digest is derived only from artifact identity, path, and bytes.
    Timestamps and labels therefore cannot silently change dataset identity.
    """
    if not artifacts:
        raise EvidenceSetContractError("EvidenceSet requires at least one artifact")
    if not evidence_set_id or not case_id or not imported_at:
        raise EvidenceSetContractError("evidenceSetId, caseId, and importedAt are required")
    refs = [str(a.artifact_id) for a in artifacts]
    if any(not ref for ref in refs):
        raise EvidenceSetContractError("every artifact requires artifact_id")
    if len(set(refs)) != len(refs):
        raise EvidenceSetContractError("artifactRefs must be unique within an EvidenceSet")
    return {
        "evidenceSetId": str(evidence_set_id),
        "caseId": str(case_id),
        "label": str(label),
        "role": str(role).upper(),
        "importedAt": str(imported_at),
        "artifactRefs": sorted(refs),
        "datasetDigest": _dataset_digest(artifacts),
        "limitations": sorted({str(x) for x in limitations if str(x)}),
    }
