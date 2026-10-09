from __future__ import annotations

import csv
import io
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import yaml

from logsense.adapters.registry import load_default_registry

_TIME_FIELDS = ("timestamp", "ts")
_IDENTITY_FIELDS = {
    "actor", "agent", "agent_id", "cell_id", "principal", "resource", "slice_id",
    "sourceAgent", "targetAgent", "target",
}
_CORRELATION_FIELDS = {
    "actionCorrelationId", "contextId", "correlation", "requestId", "request_id", "taskId", "turn_id",
}
_SEMANTIC_FIELDS = ("operation", "action", "tool", "tilt_deg", "status", "result", "decision", "platform", "allocation")
_KV_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>[^\s]+)")
_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\b")


@dataclass(frozen=True)
class ParseFailure:
    parse_failure_id: str
    analysis_run_id: str
    artifact_ref: str
    adapter_id: str | None
    record_ref: str | None
    reason_code: str
    message: str
    recoverable: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "parseFailureId": self.parse_failure_id,
            "analysisRunId": self.analysis_run_id,
            "artifactRef": self.artifact_ref,
            "adapterId": self.adapter_id,
            "recordRef": self.record_ref,
            "reasonCode": self.reason_code,
            "message": self.message,
            "recoverable": self.recoverable,
            "evidenceRefs": [self.artifact_ref],
            "limitations": [],
        }


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def _sample(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _records_csv(text: str, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, Any]] = []
    failures: list[ParseFailure] = []
    count = 0
    if reader.fieldnames is None:
        return [], [ParseFailure(f"failure:{artifact_id}:1", "analysis:profile", artifact_id, "syntax.csv.v1", "1", "CSV_HEADER_MISSING", "CSV header is missing")], 1
    expected = len(reader.fieldnames)
    for idx, row in enumerate(reader, start=1):
        count += 1
        # csv.DictReader stores excess fields under None and missing columns as None.
        malformed = None in row or any(row.get(k) is None for k in reader.fieldnames)
        if malformed:
            failures.append(ParseFailure(f"failure:{artifact_id}:{idx}", "analysis:profile", artifact_id, "syntax.csv.v1", str(idx), "CSV_COLUMN_MISMATCH", f"Expected {expected} columns"))
            continue
        records.append(OrderedDict((k, row[k]) for k in reader.fieldnames))
    return records, failures, count


def _records_json(text: str, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [ParseFailure(f"failure:{artifact_id}:1", "analysis:profile", artifact_id, "syntax.json.v1", "1", "JSON_DECODE_ERROR", str(exc))], 1
    if isinstance(obj, dict):
        return [obj], [], 1
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return list(obj), [], len(obj)
    return [], [ParseFailure(f"failure:{artifact_id}:1", "analysis:profile", artifact_id, "syntax.json.v1", "1", "JSON_RECORD_SHAPE_UNSUPPORTED", "Expected object or array of objects")], 1


def _records_jsonl(text: str, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    records: list[dict[str, Any]] = []
    failures: list[ParseFailure] = []
    count = 0
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        count += 1
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("record is not an object")
            records.append(obj)
        except (json.JSONDecodeError, ValueError) as exc:
            failures.append(ParseFailure(f"failure:{artifact_id}:{line_no}", "analysis:profile", artifact_id, "syntax.jsonl.v1", str(line_no), "JSONL_RECORD_INVALID", str(exc)))
    return records, failures, count


def _records_yaml(text: str, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    try:
        obj = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [], [ParseFailure(f"failure:{artifact_id}:1", "analysis:profile", artifact_id, "syntax.yaml.v1", "1", "YAML_DECODE_ERROR", str(exc))], 1
    if isinstance(obj, dict):
        return [obj], [], 1
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return list(obj), [], len(obj)
    return [], [ParseFailure(f"failure:{artifact_id}:1", "analysis:profile", artifact_id, "syntax.yaml.v1", "1", "YAML_RECORD_SHAPE_UNSUPPORTED", "Expected object or array of objects")], 1


def _records_kvlog(text: str, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    records: list[dict[str, Any]] = []
    failures: list[ParseFailure] = []
    count = 0
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        count += 1
        record: OrderedDict[str, Any] = OrderedDict()
        ts = _TS_RE.search(raw)
        if ts:
            record["timestamp"] = ts.group("ts")
        record["raw"] = raw
        for match in _KV_RE.finditer(raw):
            record[match.group("key")] = match.group("value")
        # Phase 7 also defines one deterministic free-text request form:
        # <timestamp> <operation> request <requestId> <status>.
        if len(record) == (2 if "timestamp" in record else 1):
            remainder = raw[ts.end():].strip() if ts else raw.strip()
            parts = remainder.split()
            if len(parts) == 4 and parts[1].lower() == "request":
                record["requestId"] = parts[2]
                record["operation"] = parts[0]
                record["status"] = parts[3]
        if len(record) == 1 and "raw" in record:
            failures.append(ParseFailure(f"failure:{artifact_id}:{line_no}", "analysis:profile", artifact_id, "syntax.kvlog.v1", str(line_no), "KVLOG_NO_FIELDS", "No deterministic key=value fields found"))
            continue
        records.append(record)
    return records, failures, count


def parse_records(format_name: str, content: bytes, artifact_id: str) -> tuple[list[dict[str, Any]], list[ParseFailure], int]:
    text = content.decode("utf-8", errors="replace")
    if format_name == "csv":
        return _records_csv(text, artifact_id)
    if format_name == "json":
        return _records_json(text, artifact_id)
    if format_name in {"jsonl", "ndjson"}:
        return _records_jsonl(text, artifact_id)
    if format_name in {"yaml", "yml"}:
        return _records_yaml(text, artifact_id)
    if format_name in {"log", "txt"}:
        return _records_kvlog(text, artifact_id)
    return [], [], 0


def schema_profile(*, artifact_id: str, format_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_fields: list[str] = []
    seen_fields: set[str] = set()
    for rec in records:
        for key in rec:
            if key not in seen_fields:
                seen_fields.add(key)
                ordered_fields.append(key)

    field_profiles = []
    total = len(records)
    for key in ordered_fields:
        present = [rec[key] for rec in records if key in rec and rec[key] is not None]
        types = []
        for value in present:
            t = _value_type(value)
            if t not in types:
                types.append(t)
        samples = [_sample(v) for v in present[:3]]
        cardinality = len({_sample(v) for v in present})
        null_rate = (total - len(present)) / total if total else 0.0
        field_profiles.append({
            "path": key,
            "dataTypes": types,
            "nullRate": null_rate,
            "cardinality": cardinality,
            "sampleValuesRedacted": samples,
        })

    candidate_keys = [k for k in ordered_fields if k in _IDENTITY_FIELDS or k in _CORRELATION_FIELDS]
    candidate_keys.sort()
    time_fields = [k for k in ordered_fields if k in _TIME_FIELDS]
    identities = [{"path": k, "basis": "FIELD_HEURISTIC"} for k in ordered_fields if k in _IDENTITY_FIELDS]
    correlations = [{"path": k, "basis": "FIELD_HEURISTIC"} for k in ordered_fields if k in _CORRELATION_FIELDS]
    semantics = [{"path": k, "basis": "FIELD_HEURISTIC"} for k in _SEMANTIC_FIELDS if k in seen_fields]
    sample_refs = [f"raw:{artifact_id}:1"] if total else []
    case_and_name = artifact_id.removeprefix("artifact:")
    return {
        "profileId": f"schema:{case_and_name}",
        "artifactId": artifact_id,
        "format": format_name,
        "recordCount": total,
        "fieldProfiles": field_profiles,
        "candidateKeys": candidate_keys,
        "timeProfile": {"candidateFields": time_fields, "hasSourceTime": bool(time_fields)},
        "identityCandidates": identities,
        "correlationCandidates": correlations,
        "semanticCandidates": semantics,
        "qualityFindings": [],
        "sampleRefs": sample_refs,
        "generatedBy": "STANDARD_ADAPTER",
        "version": "0.1.0",
    }


def profile_artifact(*, artifact_id: str, format_name: str, content: bytes, file_name: str | None = None) -> dict[str, Any]:
    records, failures, record_count = parse_records(format_name, content, artifact_id)
    profile = schema_profile(artifact_id=artifact_id, format_name=format_name, records=records)
    profile["recordCount"] = len(records)
    if format_name == "opaque":
        state = "OPAQUE_UNPARSED"
    else:
        state = "PARSED" if not failures else ("PARTIAL" if records else "FAILED")
    selected = load_default_registry().select(file_name or f"artifact.{format_name}")
    ingest_result = {
        "ingestResultId": f"ingest:{artifact_id}",
        "artifactId": artifact_id,
        "state": state,
        "adapterId": selected.adapter.adapter_id,
        "adapterVersion": selected.adapter.adapter_version,
        "recordCount": record_count,
        "parsedRecordCount": len(records),
        "failedRecordCount": len(failures),
        "schemaProfileRef": profile["profileId"] if format_name != "opaque" else None,
        "sourceRoleCandidates": [],
        "failureRefs": [f.parse_failure_id for f in failures],
        "limitations": list(selected.limitations),
    }
    return {
        "records": records,
        "parseFailures": [f.as_dict() for f in failures],
        "schemaProfile": profile,
        "ingestResult": ingest_result,
        "recordCount": record_count,
        "parsedRecordCount": len(records),
        "failedRecordCount": len(failures),
        "state": state,
    }
