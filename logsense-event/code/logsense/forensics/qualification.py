from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


@dataclass(frozen=True)
class SourceQualificationRegistry:
    """Executable view of the frozen Phase 5.5 source-qualification pack."""

    pack_id: str
    version: str
    digest: str
    profiles: tuple[dict[str, Any], ...]

    @classmethod
    def load_default(cls) -> SourceQualificationRegistry:
        payload = json.loads(
            files("logsense.contracts")
            .joinpath("rules/source-qualification-profiles-v0.1.json")
            .read_text(encoding="utf-8")
        )
        return cls(
            pack_id=str(payload["packId"]),
            version=str(payload["version"]),
            digest=str(payload["digest"]),
            profiles=tuple(payload["profiles"]),
        )

    def profile_for_authority(self, authority_role: str) -> dict[str, Any]:
        matches = [p for p in self.profiles if p["sourceAuthorityRole"] == authority_role]
        if len(matches) != 1:
            raise KeyError(f"expected exactly one source qualification profile for {authority_role!r}")
        return matches[0]


def _requirement_failures(
    profile: Mapping[str, Any],
    source_descriptor: Mapping[str, Any],
    *,
    claim_class: str,
    subject_binding: str,
) -> list[str]:
    failures: list[str] = []
    if profile.get("requiresExactSubjectBinding") and subject_binding != "EXACT":
        failures.append("EXACT_SUBJECT_BINDING_REQUIRED")
    if profile.get("requiresCurrentness") and source_descriptor.get("currentness") != "CURRENT":
        failures.append("CURRENT_SOURCE_REQUIRED")
    required_integrity = tuple(profile.get("requiresIntegrityState", []))
    if required_integrity and source_descriptor.get("integrityState") not in required_integrity:
        failures.append("SOURCE_INTEGRITY_REQUIREMENT_NOT_MET")
    completeness_claims = set(profile.get("requiresCompletenessForClaims", []))
    if claim_class in completeness_claims and source_descriptor.get("completenessState") != "PROVEN_COMPLETE":
        failures.append("PROVEN_COMPLETENESS_REQUIRED")
    return failures


def qualify_source(
    source_descriptor: Mapping[str, Any],
    *,
    claim_class: str,
    analysis_run_id: str,
    qualification_id: str,
    subject_binding: str,
    evidence_refs: Sequence[str] = (),
    gap_refs: Sequence[str] = (),
    registry: SourceQualificationRegistry | None = None,
) -> dict[str, Any]:
    """Qualify one source for one claim class.

    The decision follows the frozen Phase 5.5 profile pack. Source role or
    authority alone is never treated as claim permission, and a missing
    requirement never upgrades evidence.
    """
    registry = registry or SourceQualificationRegistry.load_default()
    authority = str(source_descriptor.get("authorityRoleCandidate") or "UNKNOWN_SOURCE_AUTHORITY")
    profile = registry.profile_for_authority(authority)
    establish = set(profile.get("canEstablishClaimClasses", []))
    support = set(profile.get("canSupportClaimClasses", []))
    cannot = set(profile.get("cannotEstablishClaimClasses", []))
    failures = _requirement_failures(
        profile,
        source_descriptor,
        claim_class=claim_class,
        subject_binding=subject_binding,
    )

    limitations: list[str] = []
    if failures:
        limitations.extend(failures)

    if claim_class in establish and not failures:
        decision = "CAN_ESTABLISH"
    elif claim_class in support and not failures:
        decision = "CAN_SUPPORT"
    elif claim_class in establish and failures:
        # A profile with establishment authority cannot exercise it when a
        # claim-scoped requirement is missing. Do not silently downgrade that
        # failure into positive support unless the profile explicitly says so.
        decision = "CANNOT_ESTABLISH"
    elif claim_class in cannot:
        decision = "CANNOT_ESTABLISH"
    elif claim_class in support:
        decision = "UNKNOWN"
    else:
        decision = "UNKNOWN"

    return {
        "qualificationId": qualification_id,
        "analysisRunId": analysis_run_id,
        "sourceRef": str(source_descriptor["sourceId"]),
        "profileId": str(profile["profileId"]),
        "claimClass": claim_class,
        "decision": decision,
        "subjectBinding": subject_binding,
        "evidenceRefs": sorted({str(x) for x in evidence_refs}),
        "gapRefs": sorted({str(x) for x in gap_refs}),
        "basis": [authority],
        "limitations": limitations,
    }


def qualification_policy_digest(registry: SourceQualificationRegistry | None = None) -> str:
    return (registry or SourceQualificationRegistry.load_default()).digest
