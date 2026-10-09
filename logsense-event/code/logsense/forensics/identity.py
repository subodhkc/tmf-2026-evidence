from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceIndependenceAssessment:
    independent_lineage_count: int
    lineage_by_event: dict[str, str]
    duplicate_groups: tuple[tuple[str, ...], ...]
    limitations: tuple[str, ...]


def _scope_mismatch(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in ("provider", "environment", "domain"):
        a, b = left.get(key), right.get(key)
        if a not in (None, "") and b not in (None, "") and a != b:
            mismatches.append(key)
    return mismatches


def resolve_identity_pair(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    analysis_run_id: str,
    resolution_id: str,
    evidence_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Resolve two EntityRefs without fuzzy/name-only identity promotion.

    Native/external identifiers are authoritative for equality when available.
    Display/name equality is never sufficient to merge identities.
    """
    lkey, rkey = str(left["entityKey"]), str(right["entityKey"])
    lext, rext = left.get("externalId"), right.get("externalId")
    lname, rname = left.get("name"), right.get("name")
    basis: list[str] = []
    conflicts: list[str] = []
    limitations: list[str] = []
    resolved: str | None = None
    rule_id: str | None = None

    if lkey == rkey:
        state = "EXACT"
        resolved = lkey
        basis.append("SAME_ENTITY_KEY")
    elif lext not in (None, "") and rext not in (None, ""):
        if str(lext) == str(rext):
            mismatches = _scope_mismatch(left, right)
            if mismatches:
                state = "CONTRADICTED"
                conflicts = [lkey, rkey]
                basis.extend(["MATCHING_NATIVE_ID", "SCOPE_CONFLICT"])
                limitations.append("IDENTITY_SCOPE_CONTRADICTION")
            else:
                state = "EXACT"
                resolved = lkey
                rule_id = "IDR-001"
                basis.append("EXACT_NATIVE_ID")
        else:
            state = "CONTRADICTED"
            conflicts = [lkey, rkey]
            basis.append("DISTINCT_NATIVE_IDS")
            if lname not in (None, "") and lname == rname:
                basis.append("DISPLAY_NAME_COLLISION")
                limitations.append("DISPLAY_NAME_NOT_IDENTITY")
    elif lname not in (None, "") and lname == rname:
        state = "UNRESOLVED"
        basis.append("DISPLAY_NAME_ONLY")
        limitations.append("DISPLAY_NAME_NOT_IDENTITY")
    else:
        state = "UNRESOLVED"
        basis.append("INSUFFICIENT_IDENTITY_EVIDENCE")

    return {
        "resolutionId": resolution_id,
        "analysisRunId": analysis_run_id,
        "inputEntityRefs": [lkey, rkey],
        "resolvedEntityRef": resolved,
        "state": state,
        "ruleId": rule_id,
        "basis": basis,
        "evidenceRefs": list(evidence_refs),
        "conflictRefs": conflicts,
        "limitations": limitations,
    }


def _canonical_event_signature(event: Mapping[str, Any]) -> str:
    """Stable semantic signature used only to avoid false independence.

    It intentionally excludes sourceRef/raw serialization so forwarded/exported
    copies of the same logical record collapse to one lineage candidate.
    This does not prove that non-matching events are independent.
    """
    operation = event.get("operation") or {}
    result = event.get("result") or {}
    correlation = sorted(
        (str(x.get("kind")), str(x.get("value")))
        for x in (event.get("correlationIds") or [])
        if x.get("value") not in (None, "")
    )
    observations = sorted(
        (str(x.get("property")), str(x.get("value")), str(x.get("effectiveAt")))
        for x in (event.get("stateObservations") or [])
    )
    payload = {
        "eventClass": event.get("eventClass"),
        "eventTime": event.get("eventTime"),
        "actorRefs": sorted(str(x) for x in (event.get("actorRefs") or [])),
        "targetRefs": sorted(str(x) for x in (event.get("targetRefs") or [])),
        "operation": {
            "nativeOperation": operation.get("nativeOperation"),
            "normalizedEffect": operation.get("normalizedEffect"),
            "canonicalVerb": operation.get("canonicalVerb"),
        },
        "result": result.get("native") if isinstance(result, Mapping) else result,
        "correlation": correlation,
        "stateObservations": observations,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def assess_source_independence(
    events: Sequence[Mapping[str, Any]],
    source_descriptors: Mapping[str, Mapping[str, Any]] | None = None,
) -> SourceIndependenceAssessment:
    """Conservatively assess independent evidence lineages.

    Explicit lineageFamilyId/parent relations take precedence. Otherwise exact
    canonical-event equivalence collapses copies into one family. This prevents
    source-count inflation from SIEM exports/forwarded copies. Lack of a match
    is *not* treated as proof of independence.
    """
    descriptors = source_descriptors or {}
    family_by_event: dict[str, str] = {}
    signature_groups: dict[str, list[str]] = {}
    explicit_families: set[str] = set()
    limitations: set[str] = {"SOURCE_COUNT_NOT_EQUAL_TO_SOURCE_INDEPENDENCE"}

    for event in events:
        event_id = str(event["eventId"])
        source_ref = str(event.get("sourceRef") or "")
        desc = descriptors.get(source_ref, {})
        family = desc.get("lineageFamilyId")
        relation = desc.get("lineageRelation")
        parent = desc.get("lineageParentRef")
        if relation in {"MIRROR", "DERIVED", "AGGREGATED", "FORWARDED", "EXPORTED_COPY"} and parent:
            family = str(parent)
        if family:
            key = f"explicit:{family}"
            family_by_event[event_id] = key
            explicit_families.add(key)
            continue
        sig = _canonical_event_signature(event)
        signature_groups.setdefault(sig, []).append(event_id)

    duplicate_groups: list[tuple[str, ...]] = []
    inferred_families: set[str] = set()
    for sig, event_ids in sorted(signature_groups.items()):
        key = f"equivalent:{sig}"
        for event_id in event_ids:
            family_by_event[event_id] = key
        inferred_families.add(key)
        if len(event_ids) > 1:
            duplicate_groups.append(tuple(sorted(event_ids)))

    if signature_groups:
        limitations.add("UNMATCHED_SEMANTIC_RECORDS_NOT_PROVEN_INDEPENDENT")
    return SourceIndependenceAssessment(
        independent_lineage_count=len(explicit_families | inferred_families),
        lineage_by_event=family_by_event,
        duplicate_groups=tuple(duplicate_groups),
        limitations=tuple(sorted(limitations)),
    )
