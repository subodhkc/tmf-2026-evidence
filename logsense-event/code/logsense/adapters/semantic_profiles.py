from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

_FROZEN_SYNTAX_COMPATIBILITY_OVERRIDES = {
    ("sem.application-log.v1", "syntax.csv.v1"),
    ("sem.agent-action.v1", "syntax.kvlog.v1"),
}


@dataclass(frozen=True)
class SemanticProfileSelection:
    profile_ids: tuple[str, ...]
    basis: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def is_unresolved(self) -> bool:
        return not self.profile_ids


class SemanticProfileRegistry:
    """Deterministic Phase 7 semantic-profile registry.

    Selection classifies record *shape* into preapproved profiles only. It does
    not apply mappings or emit canonical forensic facts.
    """

    def __init__(self, registry: dict[str, Any]) -> None:
        self.version = str(registry["version"])
        self.limitations = tuple(registry.get("limitations", []))
        self._profiles: dict[str, dict[str, Any]] = {
            p["profileId"]: p for p in registry["profiles"]
        }
        if len(self._profiles) != len(registry["profiles"]):
            raise ValueError("duplicate semantic profile IDs")

    @property
    def profiles(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._profiles[k] for k in sorted(self._profiles))

    def get(self, profile_id: str) -> dict[str, Any]:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown semantic profile: {profile_id}") from exc

    def select(
        self,
        *,
        syntax_adapter_id: str,
        schema_profile: dict[str, Any],
        file_name: str | None = None,  # noqa: ARG002  # retained for signature compatibility
    ) -> SemanticProfileSelection:
        fields = {f["path"] for f in schema_profile.get("fieldProfiles", [])}
        fmt = str(schema_profile.get("format", ""))
        selected: list[str] = []
        basis: list[str] = []
        limitations: list[str] = ["PROFILE_SELECTION_ONLY_NO_CANONICAL_MAPPING"]

        def add(profile_id: str, why: str) -> None:
            if profile_id not in self._profiles:
                return
            profile = self.get(profile_id)
            declared = syntax_adapter_id in profile.get("syntaxAdapterIds", [])
            override = (profile_id, syntax_adapter_id) in _FROZEN_SYNTAX_COMPATIBILITY_OVERRIDES
            if not declared and not override:
                return
            if profile_id not in selected:
                selected.append(profile_id)
                basis.append(why)
                if override:
                    limitations.append(f"FROZEN_PROFILE_SYNTAX_OVERRIDE:{profile_id}:{syntax_adapter_id}")

        # Event-specific telecom extensions are higher-specificity than
        # generic Phase 7 profiles. Recognition is still only a profile
        # candidate; mapping/canonical promotion remains a separate owner.
        alarm_id_fields = {"alarm_id", "alarmId", "notification_id", "notificationId"}
        alarm_context_fields = {
            "severity", "perceived_severity", "perceivedSeverity",
            "probable_cause", "probableCause", "alarm_state", "alarmState",
        }
        if fields & alarm_id_fields and fields & alarm_context_fields:
            add("sem.telecom-alarm.v1", "FIELDS:telecom-alarm")

        metric_name_fields = {"kpi_name", "kpiName", "metric", "metric_name", "metricName"}
        metric_value_fields = {"value", "kpi_value", "kpiValue", "metric_value", "metricValue"}
        telecom_resource_fields = {
            "cell_id", "cellId", "nrcell_id", "nrCellId",
            "slice_id", "sliceId", "snssai", "s_nssai",
            "network_function_id", "networkFunctionId", "nf_id", "nfId",
            "service_id", "serviceId",
        }
        if fields & metric_name_fields and fields & metric_value_fields and fields & telecom_resource_fields:
            add("sem.telecom-kpi.v1", "FIELDS:telecom-kpi")

        topology_pairs = (
            ({"cell_id", "cellId", "nrcell_id", "nrCellId"}, {"site_id", "siteId"}),
            ({"cell_id", "cellId", "nrcell_id", "nrCellId"}, {"tracking_area", "trackingArea", "tac"}),
            ({"slice_id", "sliceId", "snssai", "s_nssai"}, {"subnet_id", "subnetId"}),
            ({"ue_id", "ueId", "imsi", "supi"}, {"cell_id", "cellId", "nrcell_id", "nrCellId"}),
            ({"session_id", "sessionId", "pdu_session_id", "pduSessionId"}, {"slice_id", "sliceId", "snssai", "s_nssai"}),
        )
        if any(fields & left and fields & right for left, right in topology_pairs):
            add("sem.telecom-topology.v1", "FIELDS:telecom-topology")

        property_fields = {"property", "parameter", "attribute", "parameter_name", "parameterName"}
        old_fields = {"old_value", "oldValue", "before", "previous_value", "previousValue"}
        new_fields = {"new_value", "newValue", "after", "current_value", "currentValue"}
        if (
            fields & telecom_resource_fields
            and fields & property_fields
            and fields & old_fields
            and fields & new_fields
        ):
            add("sem.telecom-config-change.v1", "FIELDS:telecom-config-change")

        if any(profile_id.startswith("sem.telecom-") for profile_id in selected):
            return SemanticProfileSelection(
                profile_ids=tuple(selected),
                basis=tuple(basis),
                limitations=tuple(limitations + ["TELECOM_PROFILE_RECOGNITION_ONLY"]),
            )

        # High-specificity shapes first.
        if {"sourceAgent", "targetAgent", "taskId"} <= fields:
            add("sem.a2a-task.v1", "FIELDS:sourceAgent+targetAgent+taskId")
        if {"delegationId", "sourceAgent", "targetAgent"} <= fields:
            add("sem.delegation.v1", "FIELDS:delegationId+sourceAgent+targetAgent")
        if {"agent_clock", "reference_clock", "offset_ms"} <= fields:
            add("sem.clock-sync.v1", "FIELDS:agent_clock+reference_clock+offset_ms")
        if "forwarded_from" in fields:
            add("sem.forwarded-copy.v1", "FIELD:forwarded_from")
        if "tool_calls" in fields or "turn_id" in fields:
            add("sem.model-trace.v1", "FIELDS:model-trace")
        if {"role", "message"} <= fields:
            add("sem.conversation.v1", "FIELDS:role+message")
        if "tools" in fields:
            add("sem.tool-inventory.v1", "FIELD:tools")
        if "tool" in fields and "result" in fields:
            add("sem.tool-trace.v1", "FIELDS:tool+result")
        if "slice_id" in fields and "display_name" in fields:
            add("sem.inventory.v1", "FIELDS:slice_id+display_name")
        if {"principal", "resource", "result"} <= fields and fmt == "csv":
            add("sem.db-audit.v1", "FIELDS:principal+resource+result")
        if "tenant_scope" in fields or ("principal" in fields and "allowed" in fields):
            add("sem.iam-effective.v1", "FIELDS:effective-IAM")
        if fields and all(f.startswith("tenant-") for f in fields):
            add("sem.tenant-map.v1", "FIELDS:tenant-map")

        # A file can legitimately carry both guardrail and platform execution
        # records (GFB-010); preserve both candidate profiles.
        if "decision" in fields:
            add("sem.guardrail.v1", "FIELD:decision")
        if "execution" in fields or "platform" in fields or ("state" in fields and fmt == "jsonl"):
            add("sem.platform-execution.v1", "FIELDS:platform-execution")

        if fmt == "csv" and ("tilt_deg" in fields or "allocation" in fields):
            add("sem.state.v1", "FIELDS:state-snapshot")

        policy_markers = {"policy_id", "policy", "max_delta_deg", "max_amount", "authorized_resource", "enforcement"}
        if fields & policy_markers:
            add("sem.policy.v1", "FIELDS:policy-snapshot")

        # API and application-log shapes are intentionally separate. App copies
        # use agent/requestId; service transactions use actor/request_id or body.
        if "body" in fields or ({"actor", "request_id"} <= fields):
            add("sem.api-transaction.v1", "FIELDS:api-transaction")
        if "status" in fields and (
            syntax_adapter_id == "syntax.kvlog.v1"
            or ({"agent", "requestId"} <= fields and fmt == "csv")
        ):
            add("sem.application-log.v1", "FIELDS:application-log")

        # Agent action is the broad operational trace profile, selected only
        # after more-specific profiles have had a chance to claim the shape.
        agent_shape = (
            "action" in fields
            or "actionCorrelationId" in fields
            or ({"principal", "tenant"} <= fields)
            or "target_id" in fields
            or (syntax_adapter_id == "syntax.kvlog.v1" and "result" in fields and "tool" not in fields)
            or ({"agent_id", "operation"} <= fields and "decision" not in fields)
        )
        if agent_shape and not selected:
            add("sem.agent-action.v1", "FIELDS:agent-action")

        # Guardrail/platform dual profile is permitted; otherwise do not stack
        # a generic profile on top of a more-specific semantic owner.
        return SemanticProfileSelection(
            profile_ids=tuple(selected),
            basis=tuple(basis),
            limitations=tuple(limitations),
        )


def load_default_semantic_registry() -> SemanticProfileRegistry:
    payload = files("logsense.contracts").joinpath("adapters/semantic-profile-registry-v0.1.json").read_text(encoding="utf-8")
    return SemanticProfileRegistry(json.loads(payload))

def load_event_semantic_registry() -> SemanticProfileRegistry:
    """Load frozen Phase 7 profiles plus versioned telecom extensions."""
    base_payload = files("logsense.contracts").joinpath(
        "adapters/semantic-profile-registry-v0.1.json"
    ).read_text(encoding="utf-8")
    telecom_payload = files("logsense.contracts").joinpath(
        "adapters/telecom-semantic-profile-registry-v0.1.json"
    ).read_text(encoding="utf-8")
    base = json.loads(base_payload)
    telecom = json.loads(telecom_payload)
    merged = {
        "version": f"{base['version']}+telecom-{telecom['version']}",
        "profiles": [*base["profiles"], *telecom["profiles"]],
        "limitations": [
            *base.get("limitations", []),
            *telecom.get("limitations", []),
        ],
    }
    return SemanticProfileRegistry(merged)
