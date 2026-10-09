"""Expected-event manifest for Control 7 (AIA-LOG-001) measurement.

A manifest is a small versioned, machine-readable declaration of the event
sequence a competition run was expected to record. It is deliberately not an
ontology: each expected event carries an id, an ordinal, a human label
(``eventType``), optional actor/operation hints, a ``required`` flag, and an
explicit ``match`` block naming the canonical-event fields that must equal
the declared values.

``match`` keys resolve against canonical events deterministically:

- ``eventId``            -> canonical ``eventId``
- ``eventType``          -> ``eventClass``, ``nativeEventType``, or the
                            ``eventType``/``event_type`` attribute
- ``actorId``            -> ``actorRefs`` (typed prefix optional) or actor
                            attributes (``actor``/``agent``/``agent_id``/…)
- ``operation``          -> ``operation.nativeOperation`` or
                            ``operation``/``action`` attributes
- identifier kinds       -> ``correlationIds`` entries or attributes
                            (``traceId``, ``requestId``, ``sessionId``,
                            ``taskId``, ``actionCorrelationId``, …)
- any other key          -> canonical ``attributes[key]``

All non-null match fields must hold simultaneously (AND semantics). An empty
``match`` block matches nothing — the manifest fails closed rather than
absorbing arbitrary evidence.

A manifest may also declare a timing limit:

.. code-block:: json

    "timing": {
        "declaredGapLimitMs": 60000,
        "declaredGapComparator": "LTE",
        "thresholdSource": "COMPETITION_RULEBOOK",
        "thresholdVersionRef": "tmf-2026-rulebook/1.0"
    }

``declaredGapComparator`` is ``LT`` or ``LTE`` (canonical uppercase):

- ``LT``  — a gap satisfies the declared rule only when ``gapMs < limit``;
  equality (``gapMs == limit``) violates.
- ``LTE`` — a gap satisfies the declared rule when ``gapMs <= limit``;
  equality does not violate.

Manifests written before comparators existed omit the field; LogSense
preserves their historical ``<=`` behavior and marks the compatibility
default explicitly (``gapComparatorSource: LEGACY_DEFAULT``) rather than
silently pretending the comparator was declared.

LogSense uses the limit only to compute ``violatesDeclaredLimit`` facts. The
final SATISFIED / NOT SATISFIED verdict belongs to HAIEC, which evaluates
against its own frozen policy — the declared comparator is producer
provenance, not governing policy.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import yaml

EXPECTED_MANIFEST_SCHEMA = "competition-expected-events/0.1"
_SCHEMA_ALIASES = {EXPECTED_MANIFEST_SCHEMA, "0.1"}

_MANIFEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Identifier kinds whose values legitimately change between CALIBRATION /
# ASSESSED_PASS / ASSESSED_BREACH / RETEST executions of the same workflow.
# They may still be used in match rules when a scenario genuinely requires
# it — but auto-generation never embeds them and the UI warns that they
# reduce cross-run manifest reuse.
RUN_SCOPED_MATCH_FIELDS = frozenset(
    {
        "eventId",
        "runId",
        "scenarioRunId",
        "traceId",
        "requestId",
        "sessionId",
        "spanId",
        "actionCorrelationId",
        "correlationId",
        "modelCallId",
        "toolCallId",
        "taskId",
    }
)


class ExpectedManifestError(ValueError):
    """Raised for malformed expected-event manifests."""


GAP_COMPARATORS = ("LT", "LTE")


def _match_block(raw: Any, *, expected_id: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ExpectedManifestError(f"{expected_id}: match must be an object")
    block: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            raise ExpectedManifestError(f"{expected_id}: match contains an empty key")
        if isinstance(value, bool) or value is None:
            if value is None:
                continue
            raise ExpectedManifestError(f"{expected_id}: match[{name}] must be a scalar value")
        if isinstance(value, (Mapping, list, tuple, set)):
            raise ExpectedManifestError(f"{expected_id}: match[{name}] must be a scalar value")
        block[name] = str(value)
    return block


def normalize_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one expected-event manifest."""
    if not isinstance(payload, Mapping):
        raise ExpectedManifestError("expected-event manifest must be an object")
    schema = str(payload.get("schemaVersion") or "0.1")
    if schema not in _SCHEMA_ALIASES:
        raise ExpectedManifestError(f"unsupported manifest schemaVersion: {schema}")

    manifest_id = str(payload.get("manifestId") or "").strip()
    if not _MANIFEST_ID_RE.fullmatch(manifest_id):
        raise ExpectedManifestError(
            "manifestId is required and must use letters, numbers, '.', '_' or '-'"
        )

    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ExpectedManifestError("events must be a non-empty array")

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_ordinals: set[int] = set()
    for index, raw in enumerate(raw_events, start=1):
        if not isinstance(raw, Mapping):
            raise ExpectedManifestError(f"events[{index}] must be an object")
        expected_id = str(raw.get("expectedEventId") or f"E{index:02d}").strip()
        if not _EVENT_ID_RE.fullmatch(expected_id):
            raise ExpectedManifestError(f"events[{index}]: invalid expectedEventId {expected_id!r}")
        if expected_id in seen_ids:
            raise ExpectedManifestError(f"duplicate expectedEventId: {expected_id}")
        seen_ids.add(expected_id)
        try:
            ordinal = int(raw.get("ordinal", index))
        except (TypeError, ValueError) as exc:
            raise ExpectedManifestError(f"{expected_id}: ordinal must be an integer") from exc
        if ordinal in seen_ordinals:
            raise ExpectedManifestError(f"duplicate ordinal: {ordinal}")
        seen_ordinals.add(ordinal)
        events.append(
            {
                "expectedEventId": expected_id,
                "ordinal": ordinal,
                "eventType": str(raw["eventType"]) if raw.get("eventType") is not None else None,
                "actorId": str(raw["actorId"]) if raw.get("actorId") is not None else None,
                "operation": str(raw["operation"]) if raw.get("operation") is not None else None,
                "required": bool(raw.get("required", True)),
                "note": str(raw["note"]) if raw.get("note") is not None else None,
                "match": _match_block(raw.get("match"), expected_id=expected_id),
            }
        )
    events.sort(key=lambda item: (item["ordinal"], item["expectedEventId"]))

    timing = payload.get("timing")
    timing_out: dict[str, Any] | None = None
    if timing is not None:
        if not isinstance(timing, Mapping):
            raise ExpectedManifestError("timing must be an object")
        limit = timing.get("declaredGapLimitMs")
        if limit is not None:
            try:
                limit = float(limit)
            except (TypeError, ValueError) as exc:
                raise ExpectedManifestError("timing.declaredGapLimitMs must be numeric") from exc
            if limit < 0:
                raise ExpectedManifestError("timing.declaredGapLimitMs must be >= 0")
        comparator = timing.get("declaredGapComparator")
        if comparator is not None:
            comparator = str(comparator).strip().upper()
            if comparator not in GAP_COMPARATORS:
                raise ExpectedManifestError("timing.declaredGapComparator must be 'LT' or 'LTE'")
        timing_out = {
            "declaredGapLimitMs": limit,
            "declaredGapComparator": comparator,
            "thresholdSource": (
                str(timing["thresholdSource"])
                if timing.get("thresholdSource") is not None
                else None
            ),
            "thresholdVersionRef": (
                str(timing["thresholdVersionRef"])
                if timing.get("thresholdVersionRef") is not None
                else None
            ),
        }

    references = payload.get("references")
    if references is not None:
        if not isinstance(references, Mapping):
            raise ExpectedManifestError("references must be an object")
        references = {
            str(key): str(value) for key, value in references.items() if value is not None
        }
    limitations = payload.get("limitations")
    if limitations is not None and not isinstance(limitations, (list, tuple)):
        raise ExpectedManifestError("limitations must be an array")

    return {
        "schemaVersion": EXPECTED_MANIFEST_SCHEMA,
        "manifestId": manifest_id,
        "manifestVersion": (
            str(payload["manifestVersion"]) if payload.get("manifestVersion") is not None else None
        ),
        "manifestDigest": (
            str(payload["manifestDigest"]) if payload.get("manifestDigest") is not None else None
        ),
        "label": str(payload.get("label") or manifest_id),
        "runId": str(payload["runId"]) if payload.get("runId") is not None else None,
        "sourceBasis": (
            str(payload["sourceBasis"]) if payload.get("sourceBasis") is not None else None
        ),
        "createdAt": str(payload["createdAt"]) if payload.get("createdAt") is not None else None,
        "events": events,
        "timing": timing_out,
        "references": dict(references) if references else None,
        "limitations": sorted({str(item) for item in limitations}) if limitations else [],
        "notes": str(payload["notes"]) if payload.get("notes") is not None else None,
    }


def load_manifest_text(text: str, *, format_hint: str | None = None) -> dict[str, Any]:
    """Parse a manifest from JSON or YAML text and normalize it."""
    hint = (format_hint or "").strip().lower().lstrip(".")
    try:
        if hint in {"yaml", "yml"}:
            payload = yaml.safe_load(text)
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExpectedManifestError(f"manifest text is not valid JSON/YAML: {exc}") from exc
    return normalize_manifest(payload or {})


def load_manifest_file(path: Any) -> dict[str, Any]:
    """Load a manifest from disk; format is chosen by file suffix."""
    from pathlib import Path

    target = Path(path)
    return load_manifest_text(target.read_text(encoding="utf-8"), format_hint=target.suffix)


def manifest_templates() -> list[dict[str, Any]]:
    """Built-in starting points for the visual manifest builder.

    Templates carry semantic match criteria only — never run-scoped
    identifiers, so one reviewed manifest can serve PASS / BREACH / RETEST
    runs. They are drafts until the operator saves them.
    """
    templates: list[dict[str, Any]] = [
        normalize_manifest(
            {
                "schemaVersion": EXPECTED_MANIFEST_SCHEMA,
                "manifestId": "generic-request-flow",
                "label": "Generic agent request flow",
                "events": [
                    {
                        "expectedEventId": "E01",
                        "ordinal": 1,
                        "eventType": "REQUEST_RECEIVED",
                        "required": True,
                        "match": {"eventType": "REQUEST_RECEIVED"},
                    },
                    {
                        "expectedEventId": "E02",
                        "ordinal": 2,
                        "eventType": "RESPONSE_SENT",
                        "required": True,
                        "match": {"eventType": "RESPONSE_SENT"},
                    },
                ],
                "notes": "Minimal skeleton — review and extend for the supplied scenario.",
            }
        )
    ]
    try:
        from logsense.competition.fixture_packs import load_fixture

        reference = dict(load_fixture("control7-healthy")["expectedManifest"])
        reference["manifestId"] = "control7-reference-flow"
        reference["label"] = "Control 7 reference flow (bundled fixture)"
        reference["runId"] = None  # templates are never bound to one run
        reference["notes"] = "Bundled deterministic reference sequence — review before reusing."
        templates.append(normalize_manifest(reference))
    # Bundled fixture reference is packaged with the app; skip defensively.
    except Exception:  # nosec B110
        pass  # pragma: no cover
    for template in templates:
        template["sourceBasis"] = "TEMPLATE"
    return templates
