from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SUPPORTED_CONTRACT_VERSIONS = ("phase7", "8.7")

class UnsupportedContractVersion(ValueError):
    pass

def _load_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        files("logsense.contracts").joinpath(name).read_text(encoding="utf-8")
    )
    return data

def schema_names(version: str) -> tuple[str, ...]:
    if version == "phase7":
        core = _load_json("phase7_core_owner_manifest.json")["selectedSchemas"]
        rules = _load_json("phase7_semantic_rules_manifest.json")["schemaCanonicalJsonSha256"]
        return tuple(sorted(set(core) | set(rules)))
    if version == "8.7":
        return tuple(sorted(_load_json("phase8_7_contract_manifest.json")["schemas"]))
    raise UnsupportedContractVersion(version)

def load_schema(name: str, version: str = "8.7") -> dict:
    names = schema_names(version)
    if name not in names:
        raise KeyError(f"schema {name!r} is not registered for contract version {version!r}")
    return _load_json(f"schemas/{name}")

def load_hard_negative_registry(version: str = "8.7") -> dict:
    if version != "8.7":
        raise UnsupportedContractVersion(version)
    manifest = _load_json("phase8_7_contract_manifest.json")
    return _load_json(f"rules/{manifest['hardNegativeRegistry']}")
