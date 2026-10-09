from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from logsense.adapters.registry import AdapterRegistry, load_default_registry
from logsense.adapters.semantic_profiles import (
    SemanticProfileRegistry,
    load_default_semantic_registry,
)

# These are Phase 7 *candidate* capability ceilings used by SourceDescriptor.
# They are intentionally weaker than claim-scoped SourceQualificationResult.
_AUTHORITY_CAPABILITY_CEILINGS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "AUTHORITATIVE_CONTROL_BOUNDARY": (
        ("AUTHORIZATION_DECISION", "POLICY_AUTHORIZED", "EFFECTIVE_GRANT"),
        ("INDEPENDENT_STATE_CONFIRMATION",),
    ),
    "PLATFORM_INSTRUMENTATION": (
        ("PLATFORM_EXECUTION", "STATE_OBSERVATION", "TIMING_OBSERVATION"),
        ("POLICY_AUTHORIZED_UNLESS_EXPLICIT_CONTROL_SOURCE",),
    ),
    "SERVICE_NATIVE_RECORD": (
        ("SERVICE_RESPONSE", "AUDIT_EVENT"),
        ("POLICY_AUTHORIZED", "INDEPENDENT_EXTERNAL_STATE"),
    ),
    "APPLICATION_TELEMETRY": (
        ("REQUEST_EMITTED", "TRACE_EVENT", "MODEL_OR_TOOL_EVENT"),
        ("ACTION_APPLIED", "ACTION_CONFIRMED", "POLICY_AUTHORIZED"),
    ),
    "EXTERNAL_IMPORTED_RECORD": (
        ("IMPORTED_RECORD",),
        ("INDEPENDENT_CORROBORATION_WITHOUT_LINEAGE_QUALIFICATION",),
    ),
    "DECLARED_CONFIGURATION": (
        ("CONFIG_DECLARATION", "POLICY_DECLARATION", "TOPOLOGY_DECLARATION"),
        ("RUNTIME_EXECUTION", "ACTION_APPLIED", "ACTION_CONFIRMED"),
    ),
    "SELF_REPORTED": (
        ("SELF_REPORTED_RECORD",),
        ("INDEPENDENT_CORROBORATION", "ACTION_APPLIED", "POLICY_AUTHORIZED"),
    ),
    "UNKNOWN_SOURCE_AUTHORITY": (
        (),
        ("CANONICAL_PROMOTION_WITHOUT_SOURCE_QUALIFICATION",),
    ),
}


@dataclass(frozen=True)
class LogicalSourceProjection:
    descriptors: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


class SourceDescriptorProjector:
    """Project logical source descriptors from frozen semantic-profile facts.

    This stage creates source-role and authority *candidates* only. It does not
    perform claim-scoped source qualification and does not emit canonical
    events, entities, relations, action state, or cause state.
    """

    def __init__(
        self,
        *,
        semantic_registry: SemanticProfileRegistry | None = None,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self.semantic_registry = semantic_registry or load_default_semantic_registry()
        self.adapter_registry = adapter_registry or load_default_registry()
        self._adapter_versions = {
            adapter.adapter_id: adapter.adapter_version for adapter in self.adapter_registry.adapters
        }

    def project(
        self,
        *,
        artifact_id: str,
        artifact_path: str,
        syntax_adapter_id: str,
        semantic_profile_ids: Iterable[str],
        integrity_state: str = "VERIFIED",
        completeness_state: str = "UNKNOWN",
        currentness: str = "UNKNOWN",
        lineage_parent_ref: str | None = None,
        lineage_relation: str = "ORIGINAL",
        environment: str | None = None,
        producer: str | None = None,
    ) -> LogicalSourceProjection:
        if syntax_adapter_id not in self._adapter_versions:
            raise KeyError(f"unknown syntax adapter: {syntax_adapter_id}")
        profile_ids = tuple(semantic_profile_ids)
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("duplicate semantic profile IDs are not allowed")

        descriptors: list[dict[str, Any]] = []
        limitations: list[str] = ["SOURCE_AUTHORITY_IS_CANDIDATE_UNTIL_SOURCE_QUALIFICATION"]

        for profile_id in profile_ids:
            profile = self.semantic_registry.get(profile_id)
            roles = tuple(profile.get("sourceRoles", []))
            if not roles:
                raise ValueError(f"semantic profile has no source roles: {profile_id}")
            authority = str(profile["sourceAuthorityCandidate"])
            try:
                can_establish, cannot_establish = _AUTHORITY_CAPABILITY_CEILINGS[authority]
            except KeyError as exc:
                raise ValueError(f"unsupported authority candidate: {authority}") from exc

            descriptor = {
                "sourceId": f"source:{artifact_id}:{profile_id}",
                "sourceSystem": artifact_path,
                "sourceKind": roles[0],
                "authorityRoleCandidate": authority,
                "authorityBasis": f"semantic-profile:{profile_id}",
                "authorityLimitations": list(profile.get("limitations", [])),
                "lineageFamilyId": f"lineage:{artifact_id}",
                "lineageParentRef": lineage_parent_ref,
                "lineageRelation": lineage_relation,
                "environment": environment,
                "producer": producer,
                "adapterId": syntax_adapter_id,
                "adapterVersion": self._adapter_versions[syntax_adapter_id],
                "declaredCanEstablish": list(can_establish),
                "declaredCannotEstablish": list(cannot_establish),
                "integrityState": integrity_state,
                "completenessState": completeness_state,
                "currentness": currentness,
                "limitations": ["SOURCE_AUTHORITY_IS_CANDIDATE_UNTIL_SOURCE_QUALIFICATION"],
            }
            descriptors.append(descriptor)

        return LogicalSourceProjection(
            descriptors=tuple(descriptors),
            limitations=tuple(limitations),
        )
