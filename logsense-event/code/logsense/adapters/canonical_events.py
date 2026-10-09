from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from logsense.adapters.mapping_profiles import (
    MappingProfileEntry,
    MappingProfileMismatch,
    MappingProfileRegistry,
    apply_mapping_profile,
    load_default_mapping_registry,
)
from logsense.adapters.profiling import profile_artifact
from logsense.adapters.semantic_profiles import (
    SemanticProfileRegistry,
    load_default_semantic_registry,
)
from logsense.adapters.source_descriptors import SourceDescriptorProjector
from logsense.competition.run_activity import (
    RUN_ACTIVITY_SEMANTIC_ATTRIBUTE,
    RUN_ACTIVITY_SEMANTICS,
)

# Mapping-profile categories that may carry a declared ``semantic`` marker.
# Same list as ``apply_mapping_profile`` iterates — a marker applies only
# when the entry's sourcePath is actually present on the record.
_SEMANTIC_CATEGORIES = (
    "timeMappings", "fieldMappings", "entityMappings", "operationMappings",
    "statusMappings", "stateMappings", "correlationMappings", "relationMappings",
    "scenarioMappings", "transformRules",
)


@dataclass(frozen=True)
class CanonicalProjection:
    events: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


def _canonical_record_hash(record: dict[str, Any]) -> str:
    payload=json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()



def _normalize_event_time(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    raw=value.strip()
    if "." not in raw:
        return raw
    try:
        dt=datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return raw
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def _profile_for_record(profile_ids: tuple[str, ...], record: dict[str, Any]) -> str:
    if len(profile_ids)==1:
        return profile_ids[0]
    # Frozen Phase 7 dual-profile record family: one artifact contains guardrail
    # decisions and platform execution results. Choose by explicit record field.
    if "decision" in record and "sem.guardrail.v1" in profile_ids:
        return "sem.guardrail.v1"
    if "platform" in record and "sem.platform-execution.v1" in profile_ids:
        return "sem.platform-execution.v1"
    return profile_ids[0]


def _event_class(profile: dict[str, Any], record: dict[str, Any]) -> str:
    rules=profile.get("eventClassRules", [])
    for rule in rules:
        when=rule.get("when")
        if when and any(record.get(k)!=v for k,v in when.items()):
            continue
        return str(rule["eventClass"])
    return "UNKNOWN_EVENT"


def _entity_type(profile: dict[str, Any], source_path: str) -> str | None:
    for rule in profile.get("entityRules", []):
        if source_path in rule.get("idPaths", []):
            return str(rule["entityType"])
    # Frozen low-risk defaults for application-log mappings whose semantic
    # profile intentionally carries no entity rules.
    if source_path in {"agent", "agent_id", "actor"}:
        return "AI_AGENT"
    if source_path in {"principal"}:
        return "SERVICE_PRINCIPAL"
    if source_path in {"target", "resource", "cell_id", "target_id"}:
        return "RESOURCE"
    return None


def _typed_refs(entry: MappingProfileEntry, profile: dict[str, Any], record: dict[str, Any], target_path: str) -> list[str]:
    refs=[]
    for m in entry.mapping_profile.get("entityMappings", []):
        if m.get("targetPath") != target_path:
            continue
        source=m["sourcePath"]
        value=record.get(source)
        if value in (None, ""):
            continue
        typ=_entity_type(profile, source)
        if typ is None:
            continue
        ref=f"{typ}:{value}"
        if ref not in refs:
            refs.append(ref)
    return refs


def _correlation_ids(draft: dict[str, Any], profile: dict[str, Any], record: dict[str, Any]) -> list[dict[str, str]]:
    raw=draft.get("correlationIds") or {}
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        pairs.extend((str(k),str(v)) for k,v in raw.items() if v not in (None,""))
    # Phase 7 model-trace canonicalization explicitly promotes turn_id even
    # though the mapping profile itself is sparse. Other profile correlation
    # rules remain candidates until PR-05 correlation adjudication.
    if not pairs and profile.get("profileId")=="sem.model-trace.v1" and record.get("turn_id") not in (None,""):
        pairs.append(("correlationId",str(record["turn_id"])))
    return [{"kind":k,"value":v,"source":"PRODUCER_GENERATED","validationState":"UNVALIDATED"} for k,v in pairs]


def _native_record_id(correlation_ids: list[dict[str, str]]) -> str | None:
    return correlation_ids[0]["value"] if correlation_ids else None


def _raw_ref(*, artifact_id: str, record_index: int, format_name: str, record: dict[str, Any]) -> dict[str, Any]:
    corr=[]
    # raw ref identity is intentionally local; correlation validation is later.
    for k in ("actionCorrelationId","request_id","requestId","taskId","contextId","turn_id","correlation"):
        if record.get(k) not in (None, ""):
            corr.append(str(record[k]))
            break
    csv_mode=format_name=="csv"
    line_mode=format_name in {"jsonl","ndjson","log","txt"}
    return {
        "recordRef": f"raw:{artifact_id}:{record_index}",
        "artifactId": artifact_id,
        "nativeRecordId": corr[0] if corr else None,
        "lineStart": record_index if line_mode else None,
        "lineEnd": record_index if line_mode else None,
        "rowNumber": record_index + 1 if csv_mode else None,
        "jsonPointer": f"/{record_index-1}" if format_name in {"json","yaml","yml"} else None,
        "byteOffset": None,
        "nativeHash": _canonical_record_hash(record),
        "rawPreviewRedacted": None,
    }


def _state_observations(profile_id: str, record: dict[str, Any], event_time: str | None) -> list[dict[str, Any]]:
    if profile_id != "sem.state.v1":
        return []
    identity={"timestamp","ts","cell_id","slice_id","resource"}
    candidates=[k for k in record if k not in identity]
    if not candidates:
        return []
    prop=candidates[0]
    native=record[prop]
    value=str(native)
    obs: dict[str, Any] = {
        "property":prop,
        "value":value,
        "stateFacet":"OPERATIONAL_OBSERVED_STATE",
        "nativeValue":value,
        "effectiveAt":event_time,
    }
    if prop=="tilt_deg":
        try:
            numeric=float(native)
            obs["measurement"]={
                "value":str(numeric),"unit":"ANGLE_DEGREE","quantityType":"ANGLE",
                "nativeValue":value,"normalizationBasis":None,
            }
        except (TypeError,ValueError):
            pass
    return [obs]


def _mapped_result(draft: dict[str, Any], record: dict[str, Any], profile_id: str) -> dict[str, Any] | None:
    result=draft.get("result")
    if isinstance(result,dict):
        # MappingProfile may stack decision + platform into a list; select the
        # record-specific field without upgrading its lifecycle meaning.
        native=result.get("native")
        if isinstance(native,list):
            if profile_id=="sem.guardrail.v1" and record.get("decision") is not None:
                native=record["decision"]
            elif profile_id=="sem.platform-execution.v1" and record.get("platform") is not None:
                native=record["platform"]
            else:
                native=native[0] if native else None
        return {"native":str(native)} if native is not None else None
    # Some semantic profiles define native result fields but their mapping pack
    # is intentionally sparse. Preserve only explicit values.
    for key in ("result","status","outcome"):
        if key in record and profile_id in {"sem.tool-trace.v1","sem.db-audit.v1","sem.model-trace.v1","sem.application-log.v1"}:
            return {"native":str(record[key])}
    return None


def project_canonical_events(
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_sha256: str,
    format_name: str,
    syntax_adapter_id: str,
    content: bytes,
    ingested_at: str,
    mapping_registry: MappingProfileRegistry | None = None,
    semantic_registry: SemanticProfileRegistry | None = None,
    mapping_entry: MappingProfileEntry | None = None,
) -> CanonicalProjection:
    """Project evidence-bound CanonicalEvents from a preapproved exact mapping.

    Unknown fingerprints remain unprojected. Missing source timestamps remain
    null. This function never uses wall-clock time, random IDs, AI, or causal
    inference.
    """
    mapping_registry=mapping_registry or load_default_mapping_registry()
    semantic_registry=semantic_registry or load_default_semantic_registry()
    entry = mapping_entry or mapping_registry.resolve_exact(
        artifact_sha256=artifact_sha256,
        syntax_adapter_id=syntax_adapter_id,
    )
    if entry is None:
        return CanonicalProjection(events=(),limitations=("NO_PREAPPROVED_EXACT_MAPPING",))
    if entry.artifact_sha256 != artifact_sha256:
        raise MappingProfileMismatch("mapping entry fingerprint does not match artifact")
    if entry.syntax_adapter_id != syntax_adapter_id:
        raise MappingProfileMismatch("mapping entry syntax adapter does not match artifact")

    parsed=profile_artifact(artifact_id=artifact_id,format_name=format_name,content=content,file_name=artifact_path)
    profile_ids=entry.semantic_profile_ids
    descriptors=SourceDescriptorProjector(semantic_registry=semantic_registry).project(
        artifact_id=artifact_id,artifact_path=artifact_path,syntax_adapter_id=syntax_adapter_id,semantic_profile_ids=profile_ids
    ).descriptors
    source_by_profile={d["sourceId"].rsplit(":",1)[-1]:d["sourceId"] for d in descriptors}
    # profile IDs contain dots; direct zip is safer than parsing source IDs.
    source_by_profile={pid:d["sourceId"] for pid,d in zip(profile_ids,descriptors,strict=False)}

    events=[]
    case_and_name=artifact_id.removeprefix("artifact:")
    for idx,record in enumerate(parsed["records"],start=1):
        pid=_profile_for_record(profile_ids,record)
        profile=semantic_registry.get(pid)
        draft=apply_mapping_profile(entry,record).values
        event_time=_normalize_event_time(draft.get("eventTime"))
        native_ts=None
        for m in entry.mapping_profile.get("timeMappings",[]):
            if record.get(m["sourcePath"]) not in (None,""):
                native_ts=str(record[m["sourcePath"]])
                break
        corr=_correlation_ids(draft,profile,record)
        op=draft.get("operation")
        if isinstance(op,dict) and op.get("nativeOperation") is not None:
            op=dict(op)
            op["mappingStatus"]="UNKNOWN_MAPPING"
        else:
            op=None
        attributes={k:v for k,v in record.items() if k!="raw"}
        attributes["semanticProfileId"]=pid
        attributes["sourceAuthorityCandidate"]=profile["sourceAuthorityCandidate"]
        # Run-activity semantics declared on the approved mapping profile —
        # e.g. a timeMappings entry {"semantic": "RUN_START"} marks the
        # record as an explicit assessed-run lifecycle fact. Marker applies
        # only when the mapped source field is actually present.
        run_semantics=sorted(
            {
                str(mapping["semantic"])
                for category in _SEMANTIC_CATEGORIES
                for mapping in entry.mapping_profile.get(category, [])
                if isinstance(mapping, dict)
                and str(mapping.get("semantic") or "") in RUN_ACTIVITY_SEMANTICS
                and record.get(mapping.get("sourcePath")) not in (None, "")
            }
        )
        if run_semantics:
            attributes[RUN_ACTIVITY_SEMANTIC_ATTRIBUTE]=run_semantics
        event={
            "eventId":f"event:{case_and_name}:{idx}",
            "eventClass":_event_class(profile,record),
            "eventClassAssignment":"MAPPED",
            "nativeEventType":None,
            "eventTime":event_time,
            "observedAt":None,
            "receivedAt":None,
            "ingestedAt":ingested_at,
            "timeQuality":"SOURCE_EXACT" if event_time else "MISSING",
            "orderingBasis":"EVENT_TIME" if event_time else "UNKNOWN",
            "sourceRef":source_by_profile[pid],
            "rawRecordRefs":[_raw_ref(artifact_id=artifact_id,record_index=idx,format_name=format_name,record=record)],
            "actorRefs":_typed_refs(entry,profile,record,"actorRefs"),
            "operation":op,
            "targetRefs":_typed_refs(entry,profile,record,"targetRefs"),
            "result":_mapped_result(draft,record,pid),
            "stateObservations":_state_observations(pid,record,event_time),
            "correlationIds":corr,
            "declaredRelationRefs":[],
            "attributes":attributes,
            "mappingProfileRef":entry.mapping_profile["profileId"],
            "mappingBasis":[f"semantic-profile:{pid}"],
            "limitations":[],
            "clockDomainRef":None,
            "temporalNormalizationRef":None,
            "nativeTimestamp":native_ts,
            "scenarioRef":None,
        }
        events.append(event)
    binding_limit = (
        "EXPLICIT_RUNTIME_MAPPING_BINDING"
        if entry.mapping_profile.get("approvalMode") == "USER"
        else "PREAPPROVED_EXACT_MAPPING_ONLY"
    )
    return CanonicalProjection(events=tuple(events),limitations=(binding_limit,))
