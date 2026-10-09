from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from logsense.adapters.registry import load_default_registry


def project_adapter_qualification_records(analysis: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Project Phase 8.7 AdapterQualificationRecord views from runtime adapter facts.

    The analysis spine already records the selected syntax adapter and profile refs.
    This function reuses the frozen adapter registry to expose qualification limits;
    it never grants canonical promotion or forensic semantic authority.
    """
    registry = load_default_registry()
    adapters = {adapter.adapter_id: adapter for adapter in registry.adapters}
    rows: list[dict[str, Any]] = []

    for artifact in analysis.get("artifactResults") or ():
        adapter_id = str(artifact.get("syntaxAdapterId") or "")
        adapter = adapters.get(adapter_id)
        artifact_id = str(artifact.get("artifactId") or "")
        schema_profile = artifact.get("schemaProfileRef")
        semantic_profiles = [str(x) for x in artifact.get("semanticProfileIds") or () if str(x)]
        artifact_limits = [str(x) for x in artifact.get("limitations") or () if str(x)]

        if adapter is None:
            rows.append({
                "artifactId": artifact_id,
                "path": artifact.get("path"),
                "adapterId": adapter_id or None,
                "adapterVersion": None,
                "formatFamily": artifact.get("format"),
                "schemaProfiles": [str(schema_profile)] if schema_profile else [],
                "semanticProfiles": sorted(set(semantic_profiles)),
                "qualificationState": "NOT_ASSESSED",
                "qualificationBasis": [],
                "validatedFixtureRefs": [],
                "producerIdentity": "logsense:analysis-spine",
                "supportedFields": [],
                "unsupportedFields": ["FORENSIC_SEMANTICS", "CANONICAL_RELATIONS", "CAUSE_STATE"],
                "knownLimitations": sorted(set(artifact_limits + ["UNKNOWN_ADAPTER_ID"])),
                "deterministicMapping": False,
                "mayEmitRelationCandidates": False,
                "canonicalPromotionAllowed": False,
                "lastValidatedAgainstContractVersion": None,
            })
            continue

        opaque = adapter.adapter_id == "syntax.opaque.v1"
        supported = ["RAW_ARTIFACT_PRESERVATION"]
        if not opaque:
            supported.append("SYNTAX_ROUTING")
        limitations = set(adapter.limitations)
        limitations.update(artifact_limits)
        limitations.add("DETECTION_RULE_BASIS_NOT_EXPOSED_BY_ANALYSIS_RESULT")

        rows.append({
            "artifactId": artifact_id,
            "path": artifact.get("path"),
            "adapterId": adapter.adapter_id,
            "adapterVersion": adapter.adapter_version,
            "formatFamily": adapter.formats[0] if adapter.formats else "opaque",
            "schemaProfiles": [str(schema_profile)] if schema_profile else [],
            "semanticProfiles": sorted(set(semantic_profiles)),
            "qualificationState": "OPAQUE_PRESERVATION" if opaque else "CONDITIONALLY_QUALIFIED",
            "qualificationBasis": ["ANALYSIS_RUNTIME_SELECTED_ADAPTER"],
            "validatedFixtureRefs": [],
            "producerIdentity": "logsense:analysis-spine",
            "supportedFields": supported,
            "unsupportedFields": ["FORENSIC_SEMANTICS", "CANONICAL_RELATIONS", "CAUSE_STATE"],
            "knownLimitations": sorted(limitations),
            "deterministicMapping": True,
            "mayEmitRelationCandidates": False,
            "canonicalPromotionAllowed": False,
            "lastValidatedAgainstContractVersion": "phase7",
        })

    return tuple(sorted(rows, key=lambda row: (str(row.get("path") or ""), str(row.get("artifactId") or ""))))
