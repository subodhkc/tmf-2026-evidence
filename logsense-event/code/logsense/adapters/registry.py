from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SyntaxAdapter:
    adapter_id: str
    adapter_version: str
    formats: tuple[str, ...]
    media_types: tuple[str, ...]
    file_extensions: tuple[str, ...]
    source_roles: tuple[str, ...]
    parse_mode: str
    can_auto_detect: bool
    preserves_raw_artifact: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class AdapterSelection:
    adapter: SyntaxAdapter
    rule_id: str
    basis: str
    limitations: tuple[str, ...]

    @property
    def is_opaque(self) -> bool:
        return self.adapter.adapter_id == "syntax.opaque.v1"

    def qualification_record(self, producer_identity: str = "logsense:syntax-registry") -> dict[str, Any]:
        state = "OPAQUE_PRESERVATION" if self.is_opaque else "CONDITIONALLY_QUALIFIED"
        supported = ["RAW_ARTIFACT_PRESERVATION"]
        if not self.is_opaque:
            supported.append("SYNTAX_ROUTING")
        return {
            "adapterId": self.adapter.adapter_id,
            "adapterVersion": self.adapter.adapter_version,
            "formatFamily": self.adapter.formats[0] if self.adapter.formats else "opaque",
            "schemaProfiles": [],
            "semanticProfiles": [],
            "qualificationState": state,
            "qualificationBasis": [self.basis],
            "validatedFixtureRefs": [],
            "producerIdentity": producer_identity,
            "supportedFields": supported,
            "unsupportedFields": ["FORENSIC_SEMANTICS", "CANONICAL_RELATIONS", "CAUSE_STATE"],
            "knownLimitations": sorted(set(self.adapter.limitations + self.limitations)),
            "deterministicMapping": True,
            "mayEmitRelationCandidates": False,
            "canonicalPromotionAllowed": False,
            "lastValidatedAgainstContractVersion": "phase7",
        }


class AdapterRegistry:
    def __init__(self, adapters: list[SyntaxAdapter], detection_rules: list[dict[str, Any]]) -> None:
        self._adapters = {a.adapter_id: a for a in adapters}
        self._rules = tuple(sorted(detection_rules, key=lambda r: (-int(r["priority"]), r["ruleId"])))
        if "syntax.opaque.v1" not in self._adapters:
            raise ValueError("opaque adapter is required")
        referenced = {r["syntaxAdapterId"] for r in self._rules}
        unknown = referenced - set(self._adapters)
        if unknown:
            raise ValueError(f"detection rules reference unknown adapters: {sorted(unknown)}")

    @property
    def adapters(self) -> tuple[SyntaxAdapter, ...]:
        return tuple(sorted(self._adapters.values(), key=lambda a: a.adapter_id))

    @property
    def detection_rules(self) -> tuple[dict[str, Any], ...]:
        return self._rules

    def select(self, file_name: str, media_type: str | None = None) -> AdapterSelection:
        ext = Path(file_name).suffix.lower()
        for rule in self._rules:
            extensions = tuple(x.lower() for x in rule.get("extensions", []))
            media_types = tuple(x.lower() for x in rule.get("mediaTypes", []))
            extension_match = bool(extensions and ext in extensions)
            media_match = bool(media_type and media_types and media_type.lower() in media_types)
            catch_all = not extensions and not media_types and not rule.get("contentMatchers")
            if extension_match or media_match or catch_all:
                basis = f"DETECTION_RULE:{rule['ruleId']}"
                return AdapterSelection(
                    adapter=self._adapters[rule["syntaxAdapterId"]],
                    rule_id=rule["ruleId"],
                    basis=basis,
                    limitations=tuple(rule.get("limitations", [])),
                )
        raise RuntimeError("adapter registry has no applicable rule")


def _load_json(relative_path: str) -> Any:
    text = files("logsense.contracts").joinpath(relative_path).read_text(encoding="utf-8")
    return json.loads(text)


def load_default_registry() -> AdapterRegistry:
    registry = _load_json("adapters/syntax-adapters-v0.1.json")
    rules = _load_json("adapters/adapter-detection-rules-v0.1.json")
    adapters = [
        SyntaxAdapter(
            adapter_id=item["adapterId"],
            adapter_version=item["adapterVersion"],
            formats=tuple(item.get("formats", [])),
            media_types=tuple(item.get("mediaTypes", [])),
            file_extensions=tuple(item.get("fileExtensions", [])),
            source_roles=tuple(item.get("sourceRoles", [])),
            parse_mode=item["parseMode"],
            can_auto_detect=bool(item.get("canAutoDetect", False)),
            preserves_raw_artifact=bool(item.get("preservesRawArtifact", False)),
            limitations=tuple(item.get("limitations", [])),
        )
        for item in registry["adapters"]
    ]
    return AdapterRegistry(adapters=adapters, detection_rules=rules)
