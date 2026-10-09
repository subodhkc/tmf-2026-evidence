"""Manual import of authoritative HAIEC assurance proof snapshots.

Imported HAIEC JSON is an ``AUTHORITATIVE EXTERNAL ASSURANCE PROOF
SNAPSHOT`` — never canonical runtime evidence. It is persisted under the
case's derived-output store (``reports/haiec-proof-<digest>.json``) so it
cannot enter event normalization, C7 counting, C9 drift measurement, C16
accounting, run reconstruction, or evidence deduplication. LogSense reads
it for judge presentation only; it never evaluates it.

Persistence is digest-keyed: re-importing the exact same bytes is
idempotent, and a later file with a similar name can never overwrite an
earlier artifact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logsense.workspace.cases import (
    list_case_output_names,
    load_case,
    load_case_output,
    save_case_output,
)

SCHEMA = "haiec-proof-import/0.1"
OUTPUT_PREFIX = "haiec-proof-"
MAX_IMPORT_BYTES = 2 * 1024 * 1024

CONTROL_TYPE = "HAIEC_CONTROL_TEST_RESULT"
MANIFEST_TYPE = "HAIEC_JUDGMENT_DAY_MANIFEST"
UNSUPPORTED_TYPE = "UNSUPPORTED"

# Supported TMF control identities. A judge may say "control 9" while the
# HAIEC export stores the governing code — the known alias pair is matched
# by exact equality only, never by name similarity.
SUPPORTED_CONTROL_ALIASES: dict[str, str] = {
    "C7": "AIA-LOG-001",
    "AIA-LOG-001": "C7",
    "C9": "AIA-ARC-006",
    "AIA-ARC-006": "C9",
    "C16": "ACN-COST-001",
    "ACN-COST-001": "C16",
}
SUPPORTED_CONTROL_IDS = frozenset(SUPPORTED_CONTROL_ALIASES)
VALID_RESULTS = frozenset({"SATISFIED", "NOT_SATISFIED", "NOT_EVALUATED"})

_MANIFEST_MARKERS = (
    "eventFreeze",
    "freezeState",
    "eventFreezeRef",
    "eventFreezeDigest",
    "scoredRuns",
    "controlTests",
    "controlTestResults",
    "artifactReadiness",
    "retestRefs",
    "governingControls",
    "judgmentDay",
    "judgementDay",
)
# Explicit canonical contract recognition (HAIEC PR #2073). Any additive
# 1.x version under the same family is accepted — unknown extra fields are
# preserved verbatim, never an error.
_MANIFEST_SCHEMA_PREFIX = "haiec-judgment-day-manifest/"
_RESULT_COLLECTION_KEYS = ("results", "controlTestResults", "controlTests")
_RESULT_REQUIRED_KEYS = ("controlId", "runId", "result")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _output_name(digest: str) -> str:
    return f"{OUTPUT_PREFIX}{digest[:16]}"


def control_id_candidates(control_id: str) -> set[str]:
    """Exact-match candidates for a control identity — the supplied value
    plus its known governing-code alias. No fuzzy matching."""
    value = str(control_id or "").strip()
    candidates = {value} if value else set()
    alias = SUPPORTED_CONTROL_ALIASES.get(value)
    if alias:
        candidates.add(alias)
    return candidates


def _looks_like_result(row: Any) -> bool:
    """Shape detection — a controlId + result present means this intends to
    be a Control Test result. Completeness (e.g. runId) is enforced by
    ``_validate_result``, which marks the row INCOMPLETE instead of letting
    it vanish into UNSUPPORTED."""
    return (
        isinstance(row, Mapping)
        and row.get("controlId") not in (None, "")
        and row.get("result") not in (None, "")
    )


def _result_candidates(raw: Any) -> list[Mapping[str, Any]]:
    """Collect control-test result candidates — a top-level result object
    or a manifest embedding a results collection."""
    found: list[Mapping[str, Any]] = []
    if isinstance(raw, Mapping):
        if any(raw.get(key) is not None for key in ("controlId", "result")):
            found.append(raw)
        for key in _RESULT_COLLECTION_KEYS:
            rows = raw.get(key)
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
                found.extend(row for row in rows if isinstance(row, Mapping))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        found.extend(row for row in raw if isinstance(row, Mapping))
    return [row for row in found if _looks_like_result(row)]


def _detect_source_type(raw: Any) -> str:
    if not isinstance(raw, Mapping):
        return UNSUPPORTED_TYPE
    if _looks_like_result(raw):
        return CONTROL_TYPE
    schema = str(raw.get("schemaVersion") or raw.get("$schema") or "")
    if schema.startswith(_MANIFEST_SCHEMA_PREFIX):
        return MANIFEST_TYPE
    keys = {str(key) for key in raw}
    if keys & set(_MANIFEST_MARKERS):
        return MANIFEST_TYPE
    if _result_candidates(raw):
        return MANIFEST_TYPE
    return UNSUPPORTED_TYPE


def _validate_result(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Enough authoritative identity to prevent accidental matching —
    supported controlId, non-empty runId, recognized result."""
    errors: list[str] = []
    control_id = str(row.get("controlId") or "")
    if control_id not in SUPPORTED_CONTROL_IDS:
        errors.append(f"UNSUPPORTED_CONTROL_ID:{control_id or 'MISSING'}")
    if not str(row.get("runId") or "").strip():
        errors.append("MISSING_RUN_ID")
    result = str(row.get("result") or "").upper()
    if result not in VALID_RESULTS:
        errors.append(f"UNRECOGNIZED_RESULT:{result or 'MISSING'}")
    if errors:
        return (
            "UNSUPPORTED" if any(e.startswith("UNSUPPORTED_") for e in errors) else "INCOMPLETE",
            errors,
        )
    return "VALID", []


def _result_digest(detail: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(detail, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _window_ref(row: Mapping[str, Any]) -> str | None:
    window = row.get("window")
    if isinstance(window, Mapping):
        return str(window.get("windowRef") or window.get("ref") or "") or None
    if window:
        return str(window)
    return str(row.get("windowRef") or "") or None


def _project_results(raw: Any, *, source: Mapping[str, Any]) -> list[dict[str, Any]]:
    projections: list[dict[str, Any]] = []
    for row in _result_candidates(raw):
        state, errors = _validate_result(row)
        detail = dict(row)
        projections.append(
            {
                "controlId": str(row.get("controlId")),
                "runId": str(row.get("runId")),
                "result": str(row.get("result")).upper(),
                "windowRef": _window_ref(row),
                "validationState": state,
                "validationErrors": errors,
                "resultDigest": _result_digest(detail),
                "detail": detail,
                "importedFrom": {
                    "fileName": source.get("originalFileName"),
                    "sha256": source.get("sha256"),
                    "importedAt": source.get("importedAt"),
                },
            }
        )
    return projections


def _event_freeze_block(raw: Any) -> dict[str, Any] | None:
    """The verbatim eventFreeze object when a manifest carries one — the
    1.2 contract nests freeze identity/state/digest here. Never derived."""
    if isinstance(raw, Mapping):
        block = raw.get("eventFreeze") or raw.get("freeze")
        if isinstance(block, Mapping):
            return dict(block)
    return None


def _scored_set_identity(raw: Any) -> dict[str, Any] | None:
    """Scored-set/pin identity where the manifest supplies it — verbatim,
    never derived. Both the flat fields and the 1.2 eventFreeze block are
    read."""
    if not isinstance(raw, Mapping):
        return None
    freeze = raw.get("eventFreeze")
    freeze_map = freeze if isinstance(freeze, Mapping) else {}
    identity = {
        "selectionMode": raw.get("selectionMode"),
        "scoredSetPinId": raw.get("scoredSetPinId") or freeze_map.get("scoredSetPinId"),
        "scoredSetPinDigest": raw.get("scoredSetPinDigest"),
        "scoredSetDigest": raw.get("scoredSetDigest") or freeze_map.get("scoredSetDigest"),
    }
    return identity if any(v not in (None, "") for v in identity.values()) else None


def _event_freeze_state(raw: Any) -> str | None:
    """Project the Event Freeze identity/state only when a manifest
    explicitly carries it — never inferred. Nested block wins for state,
    flat keys are the 1.1 fallback."""
    if not isinstance(raw, Mapping):
        return None
    freeze = raw.get("eventFreeze") or raw.get("freeze")
    if isinstance(freeze, Mapping):
        nested = (
            freeze.get("state")
            or freeze.get("status")
            or freeze.get("eventFreezeState")
        )
        if nested:
            return str(nested)
    for key in ("freezeState", "eventFreezeState"):
        if raw.get(key):
            return str(raw[key])
    if isinstance(freeze, Mapping) or raw.get("eventFreezeRef") or raw.get("eventFreezeDigest"):
        return "PRESENT"
    return None


def import_haiec_proof(
    workspace_root: Path,
    case_id: str,
    *,
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    """Validate and persist one imported HAIEC proof snapshot.

    Returns the persisted (or pre-existing, on exact-duplicate) record.
    Digest-keyed output names make exact re-import idempotent and make it
    impossible for a similar file name to overwrite earlier proof.
    """
    load_case(workspace_root, case_id)
    name = str(file_name or "haiec-proof.json")
    record: dict[str, Any] = {
        "schemaVersion": SCHEMA,
        "classification": "AUTHORITATIVE EXTERNAL ASSURANCE PROOF SNAPSHOT",
        "notCanonicalRuntimeEvidence": True,
        "originalFileName": Path(name).name,
        "importedAt": _utc_now(),
        "caseId": case_id,
    }
    if len(content) > MAX_IMPORT_BYTES:
        record.update(
            {
                "sha256": _sha256(content),
                "sizeBytes": len(content),
                "detectedSourceType": UNSUPPORTED_TYPE,
                "validationState": "INVALID",
                "validationErrors": [f"FILE_TOO_LARGE:{len(content)}>{MAX_IMPORT_BYTES}"],
                "results": [],
            }
        )
        save_case_output(
            workspace_root, case_id, name=_output_name(record["sha256"]), payload=record
        )
        record["duplicate"] = False
        return record

    digest = _sha256(content)
    existing = load_case_output(workspace_root, case_id, name=_output_name(digest))
    if existing is not None and existing.get("sha256") == digest:
        existing = dict(existing)
        existing["duplicate"] = True
        return existing

    record.update({"sha256": digest, "sizeBytes": len(content)})
    errors: list[str] = []
    raw: Any = None
    raw_text: str | None = None
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("NOT_UTF8_JSON")
    if raw_text is not None:
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            errors.append(f"MALFORMED_JSON:{exc.msg}")
        else:
            if not isinstance(raw, (Mapping, list)) or (
                isinstance(raw, list) and not _result_candidates(raw)
            ):
                errors.append("TOP_LEVEL_NOT_OBJECT")
                raw = None

    source_type = _detect_source_type(raw) if raw is not None else UNSUPPORTED_TYPE
    if source_type == UNSUPPORTED_TYPE and not errors:
        errors.append("UNSUPPORTED_SHAPE")
    if raw_text is not None:
        record["rawText"] = raw_text

    record.update(
        {
            "detectedSourceType": source_type,
            "detectedSchema": (
                str(raw.get("schemaVersion") or raw.get("$schema"))
                if isinstance(raw, Mapping)
                else None
            ),
            "eventFreezeState": _event_freeze_state(raw),
            "eventFreeze": _event_freeze_block(raw),
            "scoredSetIdentity": _scored_set_identity(raw),
        }
    )
    results = _project_results(raw, source=record) if raw is not None else []
    record["results"] = results
    if source_type == UNSUPPORTED_TYPE:
        record["validationState"] = "UNSUPPORTED" if errors == ["UNSUPPORTED_SHAPE"] else "INVALID"
        record["validationErrors"] = errors
    elif errors:
        record["validationState"] = "INVALID" if not results else "INCOMPLETE"
        record["validationErrors"] = errors
    elif results and any(r["validationState"] != "VALID" for r in results):
        record["validationState"] = "INCOMPLETE"
        record["validationErrors"] = sorted({e for r in results for e in r["validationErrors"]})
    else:
        record["validationState"] = "VALID"
        record["validationErrors"] = []

    save_case_output(workspace_root, case_id, name=_output_name(digest), payload=record)
    record["duplicate"] = False
    return record


def list_imported_proofs(workspace_root: Path, case_id: str) -> list[dict[str, Any]]:
    """All imported HAIEC proof snapshots, digest-verified where raw bytes
    were preserved. A stored record whose raw text no longer matches its
    digest fails closed to INVALID."""
    load_case(workspace_root, case_id)
    proofs: list[dict[str, Any]] = []
    for name in list_case_output_names(workspace_root, case_id, prefix=OUTPUT_PREFIX):
        record = load_case_output(workspace_root, case_id, name=name)
        if not isinstance(record, Mapping):
            continue
        record = dict(record)
        raw_text = record.get("rawText")
        if raw_text is not None and _sha256(str(raw_text).encode("utf-8")) != record.get("sha256"):
            record["validationState"] = "INVALID"
            record["validationErrors"] = sorted(
                set(record.get("validationErrors") or ()) | {"STORED_DIGEST_MISMATCH"}
            )
            record["results"] = []
        record.pop("duplicate", None)
        proofs.append(record)
    return proofs


def all_control_test_results(proofs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Valid control-test result projections across all imported proofs."""
    rows: list[dict[str, Any]] = []
    for proof in proofs:
        for row in proof.get("results") or ():
            if isinstance(row, Mapping) and row.get("validationState") == "VALID":
                rows.append(dict(row))
    return rows


def find_control_test_result(
    proofs: Sequence[Mapping[str, Any]],
    *,
    control_id: str,
    run_id: str,
    window_ref: str | None = None,
) -> dict[str, Any]:
    """Exact-match lookup over imported authoritative results.

    Matching is exact controlId + runId (+ windowRef when supplied) — never
    display-name similarity, timestamp proximity, or the active run. An
    exact duplicate digest is idempotent; differing results for the same
    semantic query surface a conflict, never latest-wins.
    """
    wanted_controls = control_id_candidates(control_id)
    wanted_run = str(run_id or "").strip()
    matches: list[dict[str, Any]] = []
    for row in all_control_test_results(proofs):
        if str(row.get("controlId")) not in wanted_controls:
            continue
        if str(row.get("runId")) != wanted_run:
            continue
        if window_ref and str(row.get("windowRef") or "") != str(window_ref):
            continue
        matches.append(row)
    by_digest = {row["resultDigest"]: row for row in matches}
    distinct = list(by_digest.values())
    if not distinct:
        return {"state": "NOT_FOUND", "result": None, "matches": []}
    verdicts = {str(row.get("result")) for row in distinct}
    if len(distinct) > 1 and len(verdicts) > 1:
        return {
            "state": "CONFLICT",
            "result": None,
            "matches": distinct,
            "warning": "AUTHORITATIVE RESULT CONFLICT — OPERATOR REVIEW REQUIRED",
        }
    return {"state": "FOUND", "result": distinct[0], "matches": distinct}


def proof_chain_linkage(
    measurement: Mapping[str, Any] | None,
    haiec_result: Mapping[str, Any] | None,
) -> str:
    """Bounded side-by-side linkage state — LINKED only when an explicit
    binding identity agrees, CONFLICT when one disagrees. Exact same
    controlId+runId alone supports navigation, not proof-chain linkage."""
    if measurement is None or haiec_result is None:
        return "NOT ESTABLISHED"
    bindings = (
        ("bundleId", "bundleId"),
        ("measurementDigest", "haiecContentDigest"),
        ("measurementDigest", "resultInputDigest"),
    )
    agreed = False
    for left_key, right_key in bindings:
        left = measurement.get(left_key)
        right = haiec_result.get(right_key) or (haiec_result.get("detail") or {}).get(right_key)
        if left in (None, "") or right in (None, ""):
            continue
        if str(left) == str(right):
            agreed = True
        else:
            return "CONFLICT"
    if agreed:
        return "LINKED"
    return "PARTIAL"


def imported_proof_summary(proofs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Judge Console proof-state header counts."""
    results = all_control_test_results(proofs)
    return {
        "importedCount": len(proofs),
        "validResultCount": len(results),
        "invalidCount": sum(
            1
            for p in proofs
            if p.get("validationState") in {"INVALID", "UNSUPPORTED", "INCOMPLETE"}
        ),
        "eventFreezeImported": any(p.get("eventFreezeState") for p in proofs),
        "eventFreezeStates": sorted(
            {str(p["eventFreezeState"]) for p in proofs if p.get("eventFreezeState")}
        ),
    }
