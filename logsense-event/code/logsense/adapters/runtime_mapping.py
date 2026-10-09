from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from logsense.adapters.mapping_profiles import MappingProfileEntry, MappingProfileRegistry

_MAPPING_CATEGORIES = (
    "timeMappings",
    "fieldMappings",
    "entityMappings",
    "operationMappings",
    "statusMappings",
    "stateMappings",
    "correlationMappings",
    "relationMappings",
    "scenarioMappings",
    "transformRules",
)


@dataclass(frozen=True)
class MappingProposal:
    proposal_id: str
    template_profile_id: str
    template_artifact_sha256: str
    syntax_adapter_id: str
    semantic_profile_ids: tuple[str, ...]
    format_name: str
    source_paths: tuple[str, ...]
    structure_digest: str
    basis: tuple[str, ...]
    limitations: tuple[str, ...] = (
        "PROPOSAL_ONLY_NO_CANONICAL_PROMOTION",
        "EXPLICIT_USER_APPROVAL_REQUIRED",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposalId": self.proposal_id,
            "templateProfileId": self.template_profile_id,
            "templateArtifactSha256": self.template_artifact_sha256,
            "syntaxAdapterId": self.syntax_adapter_id,
            "semanticProfileIds": list(self.semantic_profile_ids),
            "format": self.format_name,
            "sourcePaths": list(self.source_paths),
            "structureDigest": self.structure_digest,
            "basis": list(self.basis),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MappingProposal:
        return cls(
            proposal_id=str(payload["proposalId"]),
            template_profile_id=str(payload["templateProfileId"]),
            template_artifact_sha256=str(payload["templateArtifactSha256"]),
            syntax_adapter_id=str(payload["syntaxAdapterId"]),
            semantic_profile_ids=tuple(str(x) for x in payload.get("semanticProfileIds", [])),
            format_name=str(payload["format"]),
            source_paths=tuple(str(x) for x in payload.get("sourcePaths", [])),
            structure_digest=str(payload["structureDigest"]),
            basis=tuple(str(x) for x in payload.get("basis", [])),
            limitations=tuple(str(x) for x in payload.get("limitations", [])),
        )


def _mapping_source_paths(entry: MappingProfileEntry) -> tuple[str, ...]:
    paths: set[str] = set()
    for category in _MAPPING_CATEGORIES:
        for item in entry.mapping_profile.get(category, []):
            source = item.get("sourcePath")
            if source:
                paths.add(str(source))
    return tuple(sorted(paths))


def _mapping_structure(entry: MappingProfileEntry) -> dict[str, Any]:
    profile = entry.mapping_profile
    return {
        "syntaxAdapterId": entry.syntax_adapter_id,
        "semanticProfileIds": sorted(entry.semantic_profile_ids),
        "format": profile.get("format"),
        "sourceAuthorityCandidate": profile.get("sourceAuthorityCandidate"),
        "mappings": {
            category: [
                {
                    key: item.get(key)
                    for key in ("sourcePath", "targetPath", "transform", "required")
                    if key in item
                }
                for item in profile.get(category, [])
            ]
            for category in _MAPPING_CATEGORIES
        },
    }


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _schema_field_paths(schema_profile: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item["path"])
            for item in schema_profile.get("fieldProfiles", [])
            if item.get("path") not in (None, "")
        )
    )


def propose_schema_compatible_mappings(
    registry: MappingProfileRegistry,
    *,
    schema_profile: Mapping[str, Any],
    syntax_adapter_id: str,
    semantic_profile_ids: Sequence[str],
) -> tuple[MappingProposal, ...]:
    """Return conservative reusable mapping templates for an unknown artifact.

    Compatibility requires the same syntax adapter, exact semantic-profile set,
    same parsed format, and presence of every source field used by the template.
    Duplicate benchmark mappings with the same structural mapping collapse to a
    single proposal. This function never approves or applies a mapping.
    """
    fields = set(_schema_field_paths(schema_profile))
    fmt = str(schema_profile.get("format") or "")
    semantic_key = tuple(sorted(str(x) for x in semantic_profile_ids))
    grouped: dict[str, list[MappingProfileEntry]] = {}

    for entry in registry.entries:
        if entry.syntax_adapter_id != syntax_adapter_id:
            continue
        if tuple(sorted(entry.semantic_profile_ids)) != semantic_key:
            continue
        if str(entry.mapping_profile.get("format") or "") != fmt:
            continue
        source_paths = _mapping_source_paths(entry)
        if not set(source_paths) <= fields:
            continue
        structure_digest = _digest(_mapping_structure(entry))
        grouped.setdefault(structure_digest, []).append(entry)

    proposals: list[MappingProposal] = []
    field_digest = _digest({"format": fmt, "fieldPaths": sorted(fields)})
    for structure_digest, entries in sorted(grouped.items()):
        representative = sorted(entries, key=lambda x: x.mapping_profile["profileId"])[0]
        proposal_id = "mapping-proposal:" + _digest({
            "syntaxAdapterId": syntax_adapter_id,
            "semanticProfileIds": list(semantic_key),
            "schemaFieldDigest": field_digest,
            "structureDigest": structure_digest,
        })[:24]
        proposals.append(
            MappingProposal(
                proposal_id=proposal_id,
                template_profile_id=str(representative.mapping_profile["profileId"]),
                template_artifact_sha256=representative.artifact_sha256,
                syntax_adapter_id=syntax_adapter_id,
                semantic_profile_ids=semantic_key,
                format_name=fmt,
                source_paths=_mapping_source_paths(representative),
                structure_digest=structure_digest,
                basis=(
                    "SYNTAX_ADAPTER_EXACT",
                    "SEMANTIC_PROFILE_SET_EXACT",
                    "FORMAT_EXACT",
                    "ALL_TEMPLATE_SOURCE_FIELDS_PRESENT",
                ),
            )
        )
    return tuple(proposals)


def bind_approved_mapping(
    registry: MappingProfileRegistry,
    proposal: MappingProposal,
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_sha256: str,
    approved_at: str,
) -> MappingProfileEntry:
    """Bind one explicitly approved proposal to one artifact fingerprint."""
    template = registry.get(proposal.template_profile_id)
    structure_digest = _digest(_mapping_structure(template))
    if structure_digest != proposal.structure_digest:
        raise ValueError("mapping proposal no longer matches template structure")
    if template.syntax_adapter_id != proposal.syntax_adapter_id:
        raise ValueError("mapping proposal syntax adapter mismatch")
    if tuple(sorted(template.semantic_profile_ids)) != tuple(sorted(proposal.semantic_profile_ids)):
        raise ValueError("mapping proposal semantic profile mismatch")

    profile = json.loads(json.dumps(template.mapping_profile))
    profile["profileId"] = f"runtime:{artifact_sha256[:16]}:{template.mapping_profile['profileId']}"
    profile["name"] = f"Runtime approved binding for {artifact_path}"
    profile["sourceFingerprint"] = artifact_sha256
    profile["acceptedProposalIds"] = sorted(
        set(profile.get("acceptedProposalIds", [])) | {proposal.proposal_id}
    )
    profile["limitations"] = sorted(
        set(profile.get("limitations", []))
        | {
            "SCHEMA_COMPATIBLE_EXPLICIT_USER_APPROVAL",
            "BOUND_TO_RUNTIME_ARTIFACT_FINGERPRINT",
        }
    )
    profile["createdAt"] = approved_at
    profile["approvedAt"] = approved_at
    profile["approvalMode"] = "USER"
    digest_input = dict(profile)
    digest_input["profileDigest"] = None
    profile["profileDigest"] = _digest(digest_input)

    return MappingProfileEntry(
        fixture_ref=f"runtime:{artifact_id}",
        benchmark_id="RUNTIME",
        artifact_path=artifact_path,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        syntax_adapter_id=template.syntax_adapter_id,
        semantic_profile_ids=template.semantic_profile_ids,
        mapping_profile=profile,
    )


def approved_mapping_matches_proposals(
    entry: MappingProfileEntry,
    proposals: Sequence[MappingProposal],
) -> bool:
    accepted = set(entry.mapping_profile.get("acceptedProposalIds", []))
    current = {proposal.proposal_id for proposal in proposals}
    return bool(accepted & current)
