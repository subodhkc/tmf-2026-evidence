from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PHASE8_8_ASSERTION_TYPES = frozenset(['CLAIM_EVIDENCE_STATE', 'CLAIM_STRENGTH_MAX', 'EVIDENCE_CARD_INDEPENDENT_LINEAGE_COUNT', 'FRONTIER_STATE', 'FRONTIER_CLOSURE_STATE', 'SNAPSHOT_DIGEST_UNCHANGED', 'EXECUTION_ARCHETYPE_FACET', 'DAI_DIMENSION_RESULT', 'PRINCIPAL_CONTINUITY_STATE', 'DEFERRED_CHAIN_BOUNDARY', 'ARGUMENT_PROVENANCE_ORIGIN', 'ARGUMENT_IDENTITY_PRESERVED', 'MEDIATION_ORDERING', 'CONTEXT_INFLUENCE_STATE', 'EFFECT_ENVELOPE_STATE', 'RECOVERY_STATE', 'PERIMETER_COMPATIBILITY', 'STORY_FAMILY_PRESENT', 'STORY_FAMILY_ABSENT', 'INSIGHT_STATE', 'MUST_NOT_PROMOTE'])
ZERO_TOLERANCE_ASSERTION_TYPES = frozenset({"MUST_NOT_PROMOTE"})

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def verify_artifact(path: Path, expected_sha256: str, expected_size: int) -> list[str]:
    errors=[]
    if not path.exists():
        return ["MISSING_ARTIFACT"]
    data=path.read_bytes()
    if len(data)!=expected_size:
        errors.append("SIZE_MISMATCH")
    if hashlib.sha256(data).hexdigest()!=expected_sha256:
        errors.append("SHA256_MISMATCH")
    return errors

def validate_assertion_shape(assertion: dict) -> list[str]:
    errors=[]
    if assertion.get("type") not in PHASE8_8_ASSERTION_TYPES:
        errors.append("UNKNOWN_ASSERTION_TYPE")
    if not assertion.get("assertionId"):
        errors.append("MISSING_ASSERTION_ID")
    if not assertion.get("target"):
        errors.append("MISSING_ASSERTION_TARGET")
    if not isinstance(assertion.get("critical"), bool):
        errors.append("CRITICAL_MUST_BE_BOOLEAN")
    return errors

def validate_case_integrity(case_dir: Path) -> list[str]:
    errors: list[str]=[]
    case=load_json(case_dir/"case.json")
    for art in case.get("artifacts",[]):
        errors.extend(f"{art['path']}:{e}" for e in verify_artifact(case_dir/art["path"],art["sha256"],art["sizeBytes"]))
    assertions=load_json(case_dir/"expected"/"assertions.json")
    for a in assertions:
        errors.extend(f"{a.get('assertionId','?')}:{e}" for e in validate_assertion_shape(a))
    if not any(a.get("type")=="MUST_NOT_PROMOTE" and a.get("critical") for a in assertions):
        errors.append("MISSING_CRITICAL_MUST_NOT_PROMOTE")
    return errors
