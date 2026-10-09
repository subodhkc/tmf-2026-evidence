from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any


class UnsupportedMappingTransform(ValueError):
    pass


class MappingProfileMismatch(ValueError):
    pass


@dataclass(frozen=True)
class MappingProfileEntry:
    fixture_ref: str
    benchmark_id: str
    artifact_path: str
    artifact_id: str
    artifact_sha256: str
    syntax_adapter_id: str
    semantic_profile_ids: tuple[str, ...]
    mapping_profile: dict[str, Any]


@dataclass(frozen=True)
class MappedRecordDraft:
    mapping_profile_ref: str
    source_fingerprint: str
    values: dict[str, Any]
    limitations: tuple[str, ...] = ("NON_CANONICAL_MAPPING_DRAFT",)


class MappingProfileRegistry:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.registry_id = str(payload["registryId"])
        self.version = str(payload["version"])
        self.limitations = tuple(payload.get("limitations", []))
        entries=[]
        by_sha={}
        by_profile={}
        for item in payload["profiles"]:
            profile=item["mappingProfile"]
            entry=MappingProfileEntry(
                fixture_ref=item["fixtureRef"],
                benchmark_id=item["benchmarkId"],
                artifact_path=item["artifactPath"],
                artifact_id=item["artifactId"],
                artifact_sha256=item["artifactSha256"],
                syntax_adapter_id=item["syntaxAdapterId"],
                semantic_profile_ids=tuple(item["semanticProfileIds"]),
                mapping_profile=profile,
            )
            if profile["sourceFingerprint"] != entry.artifact_sha256:
                raise MappingProfileMismatch(f"source fingerprint mismatch for {entry.artifact_id}")
            if entry.artifact_sha256 in by_sha:
                raise MappingProfileMismatch(f"duplicate artifact fingerprint: {entry.artifact_sha256}")
            if profile["profileId"] in by_profile:
                raise MappingProfileMismatch(f"duplicate mapping profile: {profile['profileId']}")
            entries.append(entry)
            by_sha[entry.artifact_sha256]=entry
            by_profile[profile["profileId"]]=entry
        if int(payload.get("profileCount", -1)) != len(entries):
            raise MappingProfileMismatch("profileCount does not match registry contents")
        self._entries=tuple(entries)
        self._by_sha=by_sha
        self._by_profile=by_profile

    @property
    def entries(self) -> tuple[MappingProfileEntry, ...]:
        return self._entries

    def resolve_exact(self, *, artifact_sha256: str, syntax_adapter_id: str | None = None) -> MappingProfileEntry | None:
        entry=self._by_sha.get(artifact_sha256)
        if entry is None:
            return None
        if syntax_adapter_id is not None and entry.syntax_adapter_id != syntax_adapter_id:
            return None
        return entry

    def get(self, profile_id: str) -> MappingProfileEntry:
        try:
            return self._by_profile[profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown mapping profile: {profile_id}") from exc


def _rfc3339_normalize(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("RFC3339_NORMALIZE requires a string")
    raw=value.strip()
    if raw.endswith("Z"):
        datetime.fromisoformat(raw[:-1] + "+00:00")
        return raw
    dt=datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        raise ValueError("RFC3339_NORMALIZE requires timezone-aware input")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def apply_transform(transform: str, value: Any) -> Any:
    if transform == "IDENTITY":
        return value
    if transform == "RFC3339_NORMALIZE":
        return _rfc3339_normalize(value)
    raise UnsupportedMappingTransform(transform)


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts=path.split(".")
    cursor=target
    for part in parts[:-1]:
        existing=cursor.get(part)
        if existing is None:
            existing={}
            cursor[part]=existing
        if not isinstance(existing, dict):
            raise MappingProfileMismatch(f"target path collides at {part}")
        cursor=existing
    leaf=parts[-1]
    if leaf in cursor:
        current=cursor[leaf]
        if isinstance(current, list):
            current.append(value)
        else:
            cursor[leaf]=[current,value]
    else:
        cursor[leaf]=value


def apply_mapping_profile(entry: MappingProfileEntry, record: dict[str, Any]) -> MappedRecordDraft:
    profile=entry.mapping_profile
    out: dict[str, Any]={}
    categories=(
        "timeMappings", "fieldMappings", "entityMappings", "operationMappings",
        "statusMappings", "stateMappings", "correlationMappings", "relationMappings",
        "scenarioMappings", "transformRules",
    )
    for category in categories:
        for mapping in profile.get(category, []):
            source=mapping["sourcePath"]
            if source not in record or record[source] is None:
                if mapping.get("required", False):
                    raise MappingProfileMismatch(f"required source field missing: {source}")
                continue
            value=apply_transform(mapping["transform"], record[source])
            _set_path(out, mapping["targetPath"], value)
    return MappedRecordDraft(
        mapping_profile_ref=profile["profileId"],
        source_fingerprint=profile["sourceFingerprint"],
        values=out,
    )


def load_default_mapping_registry() -> MappingProfileRegistry:
    payload=files("logsense.contracts").joinpath("adapters/phase7-mapping-profile-registry-v0.1.json").read_text(encoding="utf-8")
    return MappingProfileRegistry(json.loads(payload))
