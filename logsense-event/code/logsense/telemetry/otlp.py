from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from logsense.forensics.relations import evaluate_relation

_KIND_BY_NUMBER = {
    0: "UNSPECIFIED",
    1: "INTERNAL",
    2: "SERVER",
    3: "CLIENT",
    4: "PRODUCER",
    5: "CONSUMER",
}


@dataclass(frozen=True)
class OtlpParseResult:
    spans: tuple[dict[str, Any], ...]
    parse_failures: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class TracePathResult:
    edges: tuple[dict[str, Any], ...]
    relation_evaluations: tuple[dict[str, Any], ...]
    unresolved_parent_refs: tuple[dict[str, Any], ...]
    rejected_refs: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class OtlpLogsParseResult:
    log_records: tuple[dict[str, Any], ...]
    parse_failures: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class OtlpMetricsParseResult:
    metrics: tuple[dict[str, Any], ...]
    parse_failures: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    limitations: tuple[str, ...]


_METRIC_DATA_TYPES = ("gauge", "sum", "histogram", "exponentialHistogram", "summary")

OTLP_ENVELOPE_SIGNAL_KEYS: Mapping[str, str] = {
    "resourceSpans": "TRACES",
    "resourceLogs": "LOGS",
    "resourceMetrics": "METRICS",
}


def detect_otlp_envelope_signals(content: bytes) -> frozenset[str]:
    """Detect standard OTLP JSON export signal types by top-level envelope.

    Structural detection only -- the payload must decode as a single JSON object
    whose top level explicitly declares ``resourceSpans`` / ``resourceLogs`` /
    ``resourceMetrics``. Signal type is never inferred from field names such as
    ``traceId``/``spanId``, filenames, or content similarity. A document that
    legitimately carries multiple top-level signal keys reports all of them.
    """
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return frozenset()
    if not isinstance(payload, Mapping):
        return frozenset()
    return frozenset(
        signal for key, signal in OTLP_ENVELOPE_SIGNAL_KEYS.items() if key in payload
    )


def _any_value(value: Mapping[str, Any] | None) -> Any:
    if not value:
        return None
    for key in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        values = (value.get("arrayValue") or {}).get("values") or []
        return [_any_value(v) for v in values]
    if "kvlistValue" in value:
        pairs = (value.get("kvlistValue") or {}).get("values") or []
        return {
            str(item.get("key")): _any_value(item.get("value"))
            for item in pairs
            if item.get("key") is not None
        }
    return None


def _attrs(items: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    return {
        str(item["key"]): _any_value(item.get("value"))
        for item in (items or [])
        if item.get("key") is not None
    }


def _kind(raw: Any) -> str:
    if isinstance(raw, str):
        normalized = raw.removeprefix("SPAN_KIND_").upper()
        return normalized if normalized in set(_KIND_BY_NUMBER.values()) else "UNSPECIFIED"
    try:
        return _KIND_BY_NUMBER.get(int(raw), "UNSPECIFIED")
    except (TypeError, ValueError):
        return "UNSPECIFIED"


def _protocol_family(attributes: Mapping[str, Any]) -> str:
    keys = set(attributes)
    if any(k.startswith("http.") or k in {"url.full", "url.scheme"} for k in keys):
        return "HTTP"
    if any(k.startswith("rpc.") for k in keys):
        return "RPC"
    if any(k.startswith("messaging.") for k in keys):
        return "MESSAGING"
    return "UNKNOWN"


def _decode_top_level(content: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = content.decode("utf-8", errors="replace")
    stripped = text.strip()
    if not stripped:
        return [], [{
            "record": 1,
            "reasonCode": "OTLP_EMPTY_INPUT",
            "message": "No OTLP JSON content was provided.",
        }]

    try:
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            raise ValueError("top-level OTLP JSON value must be an object")
        return [obj], []
    except (json.JSONDecodeError, ValueError):
        records: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for line_no, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("OTLP JSONL record must be an object")
                records.append(obj)
            except (json.JSONDecodeError, ValueError) as exc:
                failures.append({
                    "record": line_no,
                    "reasonCode": "OTLP_JSON_RECORD_INVALID",
                    "message": str(exc),
                })
        return records, failures


def parse_otlp_trace_payload(
    content: bytes,
    *,
    artifact_ref: str,
    source_ref: str,
    otlp_spec_version: str | None = None,
    semantic_conventions_version: str | None = None,
) -> OtlpParseResult:
    """Parse OTLP JSON/JSONL trace payloads without inventing trace semantics.

    The parser preserves exact trace, span and parent identities plus resource
    and span attributes. It never uses timestamps as a join key and never
    creates service-call or causal relations in the parsing stage.
    """
    records, failures = _decode_top_level(content)
    spans: list[dict[str, Any]] = []
    ordinal = 1
    limitations: set[str] = {
        "TRACE_IDENTITY_NE_CAUSAL_ATTRIBUTION",
        "SPAN_PARENTAGE_NE_BUSINESS_IMPACT",
        "RAW_TIMESTAMP_ORDER_NE_CAUSAL_ORDER",
    }
    if otlp_spec_version is None:
        limitations.add("OTLP_SPEC_VERSION_NOT_RECORDED")
    if semantic_conventions_version is None:
        limitations.add("SEMANTIC_CONVENTIONS_VERSION_NOT_RECORDED")

    for record_index, record in enumerate(records, start=1):
        resource_spans = record.get("resourceSpans")
        if not isinstance(resource_spans, list):
            failures.append({
                "record": record_index,
                "reasonCode": "OTLP_TRACES_TOP_LEVEL_MISSING",
                "message": "Expected resourceSpans array.",
            })
            continue

        for resource_index, resource_span in enumerate(resource_spans, start=1):
            if not isinstance(resource_span, Mapping):
                failures.append({
                    "record": record_index,
                    "reasonCode": "OTLP_TRACES_RESOURCE_INVALID",
                    "message": f"Non-object resourceSpans entry at index {resource_index}.",
                })
                continue
            resource = resource_span.get("resource") or {}
            resource_attrs = _attrs(resource.get("attributes"))
            service_name = resource_attrs.get("service.name")
            service_instance = resource_attrs.get("service.instance.id")

            for scope_index, scope_spans in enumerate(resource_span.get("scopeSpans") or [], start=1):
                if not isinstance(scope_spans, Mapping):
                    failures.append({
                        "record": record_index,
                        "reasonCode": "OTLP_TRACES_SCOPE_INVALID",
                        "message": (
                            f"Non-object scopeSpans entry at resource {resource_index}, "
                            f"scope {scope_index}."
                        ),
                    })
                    continue
                scope = scope_spans.get("scope") or {}
                scope_name = scope.get("name")
                scope_version = scope.get("version")
                for span_index, span in enumerate(scope_spans.get("spans") or [], start=1):
                    if not isinstance(span, Mapping):
                        failures.append({
                            "record": record_index,
                            "reasonCode": "OTLP_SPAN_INVALID",
                            "message": (
                                f"Non-object span at resource {resource_index}, "
                                f"scope {scope_index}, span {span_index}."
                            ),
                        })
                        continue
                    trace_id = str(span.get("traceId") or "")
                    span_id = str(span.get("spanId") or "")
                    if not trace_id or not span_id:
                        failures.append({
                            "record": record_index,
                            "reasonCode": "OTLP_SPAN_IDENTITY_MISSING",
                            "message": (
                                f"Missing traceId/spanId at resource {resource_index}, "
                                f"scope {scope_index}, span {span_index}."
                            ),
                        })
                        continue
                    attributes = _attrs(span.get("attributes"))
                    evidence_ref = (
                        f"otlp:{artifact_ref}:{record_index}:"
                        f"{resource_index}:{scope_index}:{span_index}"
                    )
                    spans.append({
                        "observationId": f"{source_ref}:span:{ordinal}",
                        "sourceRef": source_ref,
                        "artifactRef": artifact_ref,
                        "evidenceRef": evidence_ref,
                        "traceId": trace_id,
                        "spanId": span_id,
                        "parentSpanId": str(span.get("parentSpanId") or "") or None,
                        "name": str(span.get("name") or ""),
                        "kind": _kind(span.get("kind")),
                        "startTimeUnixNano": str(span.get("startTimeUnixNano") or "") or None,
                        "endTimeUnixNano": str(span.get("endTimeUnixNano") or "") or None,
                        "status": dict(span.get("status") or {}),
                        "attributes": attributes,
                        "resourceAttributes": resource_attrs,
                        "serviceName": (
                            str(service_name) if service_name not in (None, "") else None
                        ),
                        "serviceInstanceId": (
                            str(service_instance)
                            if service_instance not in (None, "")
                            else None
                        ),
                        "scopeName": str(scope_name) if scope_name not in (None, "") else None,
                        "scopeVersion": (
                            str(scope_version) if scope_version not in (None, "") else None
                        ),
                        "protocolFamily": _protocol_family(attributes),
                        "links": list(span.get("links") or []),
                        "limitations": [],
                    })
                    ordinal += 1

    return OtlpParseResult(
        spans=tuple(spans),
        parse_failures=tuple(failures),
        provenance={
            "format": "OTLP_JSON",
            "otlpSpecVersion": otlp_spec_version,
            "semanticConventionsVersion": semantic_conventions_version,
            "sourceRef": source_ref,
            "artifactRef": artifact_ref,
        },
        limitations=tuple(sorted(limitations)),
    )


def _relation_for_pair(parent: Mapping[str, Any], child: Mapping[str, Any]) -> str | None:
    pair = (str(parent.get("kind")), str(child.get("kind")))
    if pair == ("CLIENT", "SERVER"):
        return "CALLS"
    if pair == ("PRODUCER", "CONSUMER"):
        return "DELIVERS_TO"
    return None


def reconstruct_trace_paths(
    spans: Sequence[Mapping[str, Any]],
    *,
    analysis_run_id: str,
) -> TracePathResult:
    """Reconstruct exact parent-child continuity and qualified runtime paths.

    Exact traceId plus parentSpanId matching establishes span continuity only.
    A canonical runtime relation is emitted only for recognized remote span-kind
    pairs when both sides carry service identity.
    """
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for span in spans:
        key = (str(span.get("traceId") or ""), str(span.get("spanId") or ""))
        by_key.setdefault(key, []).append(span)

    duplicate_keys = {key for key, rows in by_key.items() if len(rows) > 1}
    edges: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    limitations: set[str] = {
        "TRACE_IDENTITY_NE_CAUSAL_ATTRIBUTION",
        "TRACE_PATH_NE_BUSINESS_IMPACT",
        "SPAN_LINK_NE_PARENT_CHILD",
    }
    edge_ordinal = relation_ordinal = 1

    for child in sorted(
        spans,
        key=lambda x: (str(x.get("traceId")), str(x.get("spanId"))),
    ):
        parent_id = child.get("parentSpanId")
        if not parent_id:
            continue
        key = (str(child.get("traceId") or ""), str(parent_id))
        if key in duplicate_keys:
            rejected.append({
                "childSpanRef": str(child.get("observationId")),
                "parentTraceId": key[0],
                "parentSpanId": key[1],
                "reasonCode": "DUPLICATE_PARENT_SPAN_ID",
            })
            limitations.add("DUPLICATE_SPAN_ID_PREVENTS_PARENT_BINDING")
            continue

        candidates = by_key.get(key, [])
        if len(candidates) != 1:
            unresolved.append({
                "childSpanRef": str(child.get("observationId")),
                "parentTraceId": key[0],
                "parentSpanId": key[1],
                "reasonCode": "PARENT_SPAN_NOT_PRESENT",
            })
            continue

        parent = candidates[0]
        edge_id = f"{analysis_run_id}:trace-edge:{edge_ordinal}"
        edge_ordinal += 1
        parent_service = parent.get("serviceName")
        child_service = child.get("serviceName")
        kind_relation = _relation_for_pair(parent, child)
        edge: dict[str, Any] = {
            "edgeId": edge_id,
            "analysisRunId": analysis_run_id,
            "traceId": str(child["traceId"]),
            "parentSpanRef": str(parent["observationId"]),
            "childSpanRef": str(child["observationId"]),
            "parentSpanId": str(parent["spanId"]),
            "childSpanId": str(child["spanId"]),
            "parentService": parent_service,
            "childService": child_service,
            "parentKind": str(parent.get("kind")),
            "childKind": str(child.get("kind")),
            "protocolFamily": (
                child.get("protocolFamily")
                if child.get("protocolFamily") != "UNKNOWN"
                else parent.get("protocolFamily")
            ),
            "evidenceRefs": [
                str(parent["evidenceRef"]),
                str(child["evidenceRef"]),
            ],
            "continuityState": "ESTABLISHED",
            "relationEvaluationRef": None,
            "limitations": ["PARENT_CHILD_CONTINUITY_NE_ROOT_CAUSE"],
        }

        if (
            kind_relation
            and parent_service
            and child_service
            and parent_service != child_service
        ):
            relation = evaluate_relation(
                evaluation_id=f"{analysis_run_id}:trace-relation:{relation_ordinal}",
                analysis_run_id=analysis_run_id,
                relation_type=kind_relation,
                source_ref=f"SERVICE:{parent_service}",
                target_ref=f"SERVICE:{child_service}",
                source_identity_state="PARTIAL",
                target_identity_state="PARTIAL",
                admission_basis="RUNTIME_INVOCATION_RECORD",
                evidence_refs=edge["evidenceRefs"],
                satisfied_conditions=[
                    "EVIDENCE_REFS_PRESENT",
                    "DIRECTION_PRESERVED",
                    "SCENARIO_SCOPE_COMPATIBLE",
                ],
                hard_negatives_checked=[
                    "CORRELATION_FACT != CAUSAL_RELATION",
                    "TIMESTAMP_PROXIMITY != RELATION",
                    "TRACE_PATH != BUSINESS_IMPACT",
                ],
                limitations=["OTLP_PARENT_CHILD_RUNTIME_PATH_ONLY"],
            )
            relations.append(relation.evaluation)
            edge["relationEvaluationRef"] = relation.evaluation["evaluationId"]
            relation_ordinal += 1
        elif kind_relation and (not parent_service or not child_service):
            edge["limitations"].append("SERVICE_IDENTITY_MISSING_RELATION_NOT_PROMOTED")
        elif kind_relation and parent_service == child_service:
            edge["limitations"].append(
                "INTRA_SERVICE_PARENT_CHILD_NOT_PROMOTED_TO_REMOTE_RELATION"
            )
        else:
            edge["limitations"].append("SPAN_KIND_PAIR_NOT_REMOTE_PATH_PROOF")

        edges.append(edge)

    return TracePathResult(
        edges=tuple(edges),
        relation_evaluations=tuple(relations),
        unresolved_parent_refs=tuple(unresolved),
        rejected_refs=tuple(rejected),
        limitations=tuple(sorted(limitations)),
    )


def _resource_scope(resource_scope: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Shared resource/scope extraction — identical shape across signal types."""
    resource = resource_scope.get("resource") or {}
    resource_attrs = _attrs(resource.get("attributes"))
    return resource_attrs, resource_scope


def parse_otlp_logs_payload(
    content: bytes,
    *,
    artifact_ref: str,
    source_ref: str,
    otlp_spec_version: str | None = None,
    semantic_conventions_version: str | None = None,
) -> OtlpLogsParseResult:
    """Parse OTLP JSON/JSONL logs payloads (resourceLogs → scopeLogs → logRecords).

    Preserves trace/span identity, severity, body (scalar and structured),
    attributes, and BOTH event time (``timeUnixNano``) and observed time
    (``observedTimeUnixNano``) as distinct fields. The parser never invents
    a timestamp, never treats ingest/observed time as event time, and never
    establishes run membership — attribute-carried IDs are preserved
    correlation facts only.
    """
    records, failures = _decode_top_level(content)
    log_records: list[dict[str, Any]] = []
    ordinal = 1
    limitations: set[str] = {
        "EVENT_TIME_NE_OBSERVED_TIME_NE_INGEST_TIME",
        "OTLP_ATTRIBUTE_CARRIED_ID_NE_RUN_MEMBERSHIP",
        "OTLP_LOG_NE_VERDICT",
    }
    if otlp_spec_version is None:
        limitations.add("OTLP_SPEC_VERSION_NOT_RECORDED")
    if semantic_conventions_version is None:
        limitations.add("SEMANTIC_CONVENTIONS_VERSION_NOT_RECORDED")

    for record_index, record in enumerate(records, start=1):
        resource_logs = record.get("resourceLogs")
        if not isinstance(resource_logs, list):
            failures.append({
                "record": record_index,
                "reasonCode": "OTLP_LOGS_TOP_LEVEL_MISSING",
                "message": "Expected resourceLogs array.",
            })
            continue

        for resource_index, resource_log in enumerate(resource_logs, start=1):
            if not isinstance(resource_log, Mapping):
                failures.append({
                    "record": record_index,
                    "reasonCode": "OTLP_LOGS_RESOURCE_INVALID",
                    "message": f"Non-object resourceLogs entry at index {resource_index}.",
                })
                continue
            resource_attrs, _ = _resource_scope(resource_log)
            service_name = resource_attrs.get("service.name")
            service_instance = resource_attrs.get("service.instance.id")

            for scope_index, scope_log in enumerate(resource_log.get("scopeLogs") or [], start=1):
                if not isinstance(scope_log, Mapping):
                    failures.append({
                        "record": record_index,
                        "reasonCode": "OTLP_LOGS_SCOPE_INVALID",
                        "message": (
                            f"Non-object scopeLogs entry at resource {resource_index}, "
                            f"scope {scope_index}."
                        ),
                    })
                    continue
                scope = scope_log.get("scope") or {}
                scope_name = scope.get("name")
                scope_version = scope.get("version")
                for log_index, log in enumerate(scope_log.get("logRecords") or [], start=1):
                    if not isinstance(log, Mapping):
                        failures.append({
                            "record": record_index,
                            "reasonCode": "OTLP_LOG_RECORD_INVALID",
                            "message": (
                                f"Non-object log record at resource {resource_index}, "
                                f"scope {scope_index}, record {log_index}."
                            ),
                        })
                        continue
                    event_time = str(log.get("timeUnixNano") or "") or None
                    observed_time = str(log.get("observedTimeUnixNano") or "") or None
                    record_limitations: list[str] = []
                    if event_time is None:
                        record_limitations.append("EVENT_TIME_ABSENT_RETAINED")
                        limitations.add("EVENT_TIME_ABSENT_ON_SOME_RECORDS")
                    evidence_ref = (
                        f"otlp-log:{artifact_ref}:{record_index}:"
                        f"{resource_index}:{scope_index}:{log_index}"
                    )
                    log_records.append({
                        "observationId": f"{source_ref}:log:{ordinal}",
                        "sourceRef": source_ref,
                        "artifactRef": artifact_ref,
                        "evidenceRef": evidence_ref,
                        "timeUnixNano": event_time,
                        "observedTimeUnixNano": observed_time,
                        "severityNumber": log.get("severityNumber"),
                        "severityText": (
                            str(log.get("severityText"))
                            if log.get("severityText") not in (None, "")
                            else None
                        ),
                        "body": _any_value(log.get("body")),
                        "attributes": _attrs(log.get("attributes")),
                        "droppedAttributesCount": log.get("droppedAttributesCount"),
                        "flags": log.get("flags"),
                        "traceId": str(log.get("traceId") or "") or None,
                        "spanId": str(log.get("spanId") or "") or None,
                        "resourceAttributes": resource_attrs,
                        "serviceName": (
                            str(service_name) if service_name not in (None, "") else None
                        ),
                        "serviceInstanceId": (
                            str(service_instance)
                            if service_instance not in (None, "")
                            else None
                        ),
                        "scopeName": str(scope_name) if scope_name not in (None, "") else None,
                        "scopeVersion": (
                            str(scope_version) if scope_version not in (None, "") else None
                        ),
                        "limitations": record_limitations,
                    })
                    ordinal += 1

    return OtlpLogsParseResult(
        log_records=tuple(log_records),
        parse_failures=tuple(failures),
        provenance={
            "format": "OTLP_LOGS_JSON",
            "otlpSpecVersion": otlp_spec_version,
            "semanticConventionsVersion": semantic_conventions_version,
            "sourceRef": source_ref,
            "artifactRef": artifact_ref,
        },
        limitations=tuple(sorted(limitations)),
    )


def _metric_data_points(metric: Mapping[str, Any]) -> tuple[str | None, list[Mapping[str, Any]], Mapping[str, Any]]:
    """Locate the metric data type and its datapoint array. Structured
    types (histogram/exponentialHistogram/summary) keep their raw payload —
    a histogram never collapses into a scalar KPI."""
    for kind in _METRIC_DATA_TYPES:
        block = metric.get(kind)
        if isinstance(block, Mapping):
            points = block.get("dataPoints")
            return kind, [p for p in points if isinstance(p, Mapping)] if isinstance(points, list) else [], block
    return None, [], {}


def parse_otlp_metrics_payload(
    content: bytes,
    *,
    artifact_ref: str,
    source_ref: str,
    otlp_spec_version: str | None = None,
    semantic_conventions_version: str | None = None,
) -> OtlpMetricsParseResult:
    """Parse OTLP JSON/JSONL metrics payloads (resourceMetrics → scopeMetrics → metrics).

    Preserves metric identity (name/description/unit), data type, datapoint
    attributes, and both start and event timestamps per datapoint. Gauge/Sum
    numeric values are preserved exactly; histogram/summary structures are
    preserved verbatim — no metric is promoted to a KPI and no datapoint is
    forced into a scalar. Whether any metric may support the declared C9 KPI
    is a Source Setup / approved-mapping decision, never a parser decision.
    """
    records, failures = _decode_top_level(content)
    metrics: list[dict[str, Any]] = []
    ordinal = 1
    limitations: set[str] = {
        "EVENT_TIME_NE_OBSERVED_TIME_NE_INGEST_TIME",
        "OTLP_METRIC_NE_C9_KPI",
        "OTLP_ATTRIBUTE_CARRIED_ID_NE_RUN_MEMBERSHIP",
        "HISTOGRAM_STRUCTURE_PRESERVED_NE_SCALAR_KPI",
        "OTLP_METRIC_NE_VERDICT",
    }
    if otlp_spec_version is None:
        limitations.add("OTLP_SPEC_VERSION_NOT_RECORDED")
    if semantic_conventions_version is None:
        limitations.add("SEMANTIC_CONVENTIONS_VERSION_NOT_RECORDED")

    for record_index, record in enumerate(records, start=1):
        resource_metrics = record.get("resourceMetrics")
        if not isinstance(resource_metrics, list):
            failures.append({
                "record": record_index,
                "reasonCode": "OTLP_METRICS_TOP_LEVEL_MISSING",
                "message": "Expected resourceMetrics array.",
            })
            continue

        for resource_index, resource_metric in enumerate(resource_metrics, start=1):
            if not isinstance(resource_metric, Mapping):
                failures.append({
                    "record": record_index,
                    "reasonCode": "OTLP_METRICS_RESOURCE_INVALID",
                    "message": f"Non-object resourceMetrics entry at index {resource_index}.",
                })
                continue
            resource_attrs, _ = _resource_scope(resource_metric)
            service_name = resource_attrs.get("service.name")
            service_instance = resource_attrs.get("service.instance.id")

            for scope_index, scope_metric in enumerate(resource_metric.get("scopeMetrics") or [], start=1):
                if not isinstance(scope_metric, Mapping):
                    failures.append({
                        "record": record_index,
                        "reasonCode": "OTLP_METRICS_SCOPE_INVALID",
                        "message": (
                            f"Non-object scopeMetrics entry at resource {resource_index}, "
                            f"scope {scope_index}."
                        ),
                    })
                    continue
                scope = scope_metric.get("scope") or {}
                scope_name = scope.get("name")
                scope_version = scope.get("version")
                for metric_index, metric in enumerate(scope_metric.get("metrics") or [], start=1):
                    if not isinstance(metric, Mapping):
                        failures.append({
                            "record": record_index,
                            "reasonCode": "OTLP_METRIC_RECORD_INVALID",
                            "message": (
                                f"Non-object metric at resource {resource_index}, "
                                f"scope {scope_index}, metric {metric_index}."
                            ),
                        })
                        continue
                    kind, points, raw_data = _metric_data_points(metric)
                    metric_limitations: list[str] = []
                    if kind is None:
                        metric_limitations.append("METRIC_DATA_TYPE_UNRECOGNIZED")
                        limitations.add("UNRECOGNIZED_METRIC_DATA_TYPE_PRESENT")
                    datapoints: list[dict[str, Any]] = []
                    for dp_index, point in enumerate(points, start=1):
                        dp_limitations: list[str] = []
                        event_time = str(point.get("timeUnixNano") or "") or None
                        if event_time is None:
                            dp_limitations.append("EVENT_TIME_ABSENT_RETAINED")
                            limitations.add("EVENT_TIME_ABSENT_ON_SOME_DATAPOINTS")
                        datapoints.append({
                            "timeUnixNano": event_time,
                            "startTimeUnixNano": str(point.get("startTimeUnixNano") or "") or None,
                            "attributes": _attrs(point.get("attributes")),
                            "asInt": point.get("asInt"),
                            "asDouble": point.get("asDouble"),
                            "count": point.get("count"),
                            "sum": point.get("sum"),
                            "quantileValues": point.get("quantileValues"),
                            "exemplars": point.get("exemplars"),
                            "flags": point.get("flags"),
                            "raw": dict(point),
                            "limitations": dp_limitations,
                            "index": dp_index,
                        })
                    evidence_ref = (
                        f"otlp-metric:{artifact_ref}:{record_index}:"
                        f"{resource_index}:{scope_index}:{metric_index}"
                    )
                    metrics.append({
                        "observationId": f"{source_ref}:metric:{ordinal}",
                        "sourceRef": source_ref,
                        "artifactRef": artifact_ref,
                        "evidenceRef": evidence_ref,
                        "metricName": str(metric.get("name") or ""),
                        "description": (
                            str(metric.get("description"))
                            if metric.get("description") not in (None, "")
                            else None
                        ),
                        "unit": str(metric.get("unit") or "") or None,
                        "dataType": kind,
                        "dataPoints": datapoints,
                        "metadata": metric.get("metadata"),
                        "resourceAttributes": resource_attrs,
                        "serviceName": (
                            str(service_name) if service_name not in (None, "") else None
                        ),
                        "serviceInstanceId": (
                            str(service_instance)
                            if service_instance not in (None, "")
                            else None
                        ),
                        "scopeName": str(scope_name) if scope_name not in (None, "") else None,
                        "scopeVersion": (
                            str(scope_version) if scope_version not in (None, "") else None
                        ),
                        "rawData": dict(raw_data),
                        "limitations": metric_limitations,
                    })
                    ordinal += 1

    return OtlpMetricsParseResult(
        metrics=tuple(metrics),
        parse_failures=tuple(failures),
        provenance={
            "format": "OTLP_METRICS_JSON",
            "otlpSpecVersion": otlp_spec_version,
            "semanticConventionsVersion": semantic_conventions_version,
            "sourceRef": source_ref,
            "artifactRef": artifact_ref,
        },
        limitations=tuple(sorted(limitations)),
    )
