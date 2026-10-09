"""Competition Evidence Bundle — the versioned HAIEC handoff structure.

The bundle packages the deterministic competition outputs for one declared
run: the run declaration, its resolution, the expected-event manifest, and
per-control measurements. The top-level shape is stable so later controls
(AIA-ARC-006 drift, ACN-COST-001 spend) slot into ``measurements`` without
changing the architecture.

Deliberately absent: model-generated conclusions, governance verdicts, and
secrets. LogSense produces measurements; HAIEC owns SATISFIED/NOT SATISFIED.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from logsense.competition.control7 import CONTROL7_CODE
from logsense.competition.control9 import CONTROL9_CODE
from logsense.competition.control16 import CONTROL16_CODE
from logsense.competition.run_activity import resolve_run_activity

COMPETITION_BUNDLE_SCHEMA = "competition-evidence-bundle/0.1"
SHARED_CONTRACT_VERSION = "logsense-haiec-shared-competition-data/1.0"


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_competition_bundle(
    *,
    case_id: str,
    run_declaration: Mapping[str, Any],
    run_resolution: Mapping[str, Any],
    expected_manifest: Mapping[str, Any] | None,
    measurements: Mapping[str, Mapping[str, Any]],
    analysis: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    primary_measurement_code: str | None = None,
    run_activity: Mapping[str, Any] | None = None,
    canonical_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the deterministic competition bundle for one run.

    Shared-contract fields (LogSense ↔ HAIEC Shared Competition Data
    Contract v1.0) are additive on top of the stable 0.1 shape — existing
    consumers keep working.

    ``primary_measurement_code`` selects which measurement block supplies
    the singular top-level envelope fields (``measurementType``,
    ``measurementState``, snapshot/evidence binding, manifest identity).
    Sibling blocks remain nested under ``measurements`` — the envelope
    must always describe the control actually being exported.

    ``run_activity`` is the shared ``competition-run-activity/0.1``
    provenance block. When omitted it is recomputed from
    ``canonical_events`` + ``run_resolution``; without an evidence snapshot
    it fails closed to ``NOT_ESTABLISHED``. Top-level ``runStartedAt``
    mirrors the block only when ``startState == "ESTABLISHED"`` — it is
    never derived from observed-activity bounds.
    """
    if run_activity is None:
        run_activity = resolve_run_activity(canonical_events, run_resolution)
    activity = dict(run_activity)
    measurement_blocks: dict[str, Any] = {}
    evidence_refs: set[str] = set(run_resolution.get("eventRefs") or ())
    excluded: dict[str, Any] = {}
    for code, measurement in sorted(measurements.items()):
        measurement_blocks[str(code)] = dict(measurement)
        for ref in measurement.get("evidenceRefs") or ():
            evidence_refs.add(str(ref))
        for key, refs in (measurement.get("excludedEvidence") or {}).items():
            if key == "qualifiedEventRefs":
                continue  # bound evidence, not an exclusion
            excluded.setdefault(key, set()).update(str(ref) for ref in refs)

    limitations: set[str] = set()
    for source in (
        run_declaration,
        run_resolution,
        expected_manifest or {},
        activity,
        *measurements.values(),
    ):
        for item in source.get("limitations") or ():
            limitations.add(str(item))
    # The manifest limitation only applies to the C7 measurement surface —
    # a bundle measured solely under another control never had a manifest.
    if expected_manifest is None and CONTROL7_CODE in measurements:
        limitations.add("EXPECTED_EVENT_MANIFEST_ABSENT")

    gaps: list[str] = []
    for code, measurement in measurement_blocks.items():
        for item in measurement.get("missingEvents") or ():
            gaps.append(f"{code}:EXPECTED_EVENT_UNOBSERVED:{item.get('expectedEventId')}")
        for ref in measurement.get("unexpectedEvents") or ():
            gaps.append(f"{code}:UNEXPECTED_OBSERVED_EVENT:{ref.get('observedEventRef')}")

    provenance = {
        "truthOwner": "DETERMINISTIC_LOGSENSE_CORE",
        "verdictOwner": "HAIEC",
        "runDeclarationProvenance": run_declaration.get("provenance") or "USER_DECLARED",
        "aiContentIncluded": False,
        "caseId": case_id,
        "analysisRunId": (analysis or report or {}).get("analysisRunId"),
        "reportDigest": (report or {}).get("reportDigest"),
        "manifestDigest": _digest(expected_manifest) if expected_manifest is not None else None,
        "measurementDigests": {code: _digest(block) for code, block in measurement_blocks.items()},
    }

    # shared-contract identity — bound only when the measurement recorded it.
    # Top-level identity fields mirror the *primary* measurement block — the
    # control actually being exported — never silently a sibling.
    primary_key: str | None
    if primary_measurement_code and str(primary_measurement_code) in measurement_blocks:
        primary_key = str(primary_measurement_code)
    elif CONTROL7_CODE in measurement_blocks:
        primary_key = CONTROL7_CODE
    else:
        primary_key = next(iter(measurement_blocks), None)
    primary = measurement_blocks.get(primary_key) or {} if primary_key else {}
    is_c7_primary = primary_key == CONTROL7_CODE
    run_id = str(run_resolution.get("runId") or run_declaration.get("runId") or "")
    run_resolution_ref = run_declaration.get("runResolutionRef") or (
        f"competition-resolution:{run_id}" if run_id else None
    )
    governance_refs = primary.get("references") or (
        (expected_manifest or {}).get("references") if is_c7_primary else None
    )

    bundle: dict[str, Any] = {
        "schemaVersion": COMPETITION_BUNDLE_SCHEMA,
        "contractVersion": SHARED_CONTRACT_VERSION,
        "createdAt": primary.get("createdAt"),
        "caseId": case_id,
        "runId": run_id or None,
        "runRole": run_declaration.get("runRole") or primary.get("runRole"),
        "scenarioLabel": run_declaration.get("scenarioLabel") or primary.get("scenarioLabel"),
        "analysisRunId": (analysis or report or {}).get("analysisRunId"),
        "evidenceSetRef": primary.get("evidenceSetRef") or (analysis or {}).get("evidenceSetId"),
        "artifactDigests": primary.get("artifactDigests"),
        "mappingProfileRefs": primary.get("mappingProfileRefs"),
        "activeSnapshotRef": primary.get("activeSnapshotRef"),
        "runResolutionRef": run_resolution_ref,
        # C7-only manifest identity: absent on a non-C7-primary bundle even
        # when a C7 sibling block is carried for convenience.
        "expectedManifestRef": primary.get("expectedManifestRef"),
        "expectedManifestVersion": primary.get("expectedManifestVersion"),
        "expectedManifestDigest": primary.get("expectedManifestDigest")
        or (provenance["manifestDigest"] if is_c7_primary else None),
        "measurementType": primary.get("measurementType") or primary.get("controlCode"),
        "measurementSchemaVersion": (
            primary.get("measurementSchemaVersion") or primary.get("schemaVersion")
        ),
        "measurementState": primary.get("measurementState"),
        "governanceRefs": dict(governance_refs) if governance_refs else None,
        "excludedEvidence": {k: sorted(v) for k, v in excluded.items()} or None,
        "verdict": None,
        "verdictOwner": "HAIEC",
        "run": dict(run_resolution),
        # Shared run-activity provenance — one common truth across C7/C9/C16.
        # Top-level runStartedAt mirrors ONLY an ESTABLISHED start; it is
        # null for NOT_ESTABLISHED/CONFLICTING and is never sourced from
        # earliestObservedActivityAt.
        "runActivity": activity,
        "runStartedAt": (
            activity.get("runStartedAt")
            if activity.get("startState") == "ESTABLISHED"
            else None
        ),
        "expectedEventManifest": dict(expected_manifest) if expected_manifest is not None else None,
        "measurements": measurement_blocks,
        "controlsPlanned": [
            code for code in ("AIA-ARC-006", "ACN-COST-001") if code not in measurement_blocks
        ],
        "evidenceRefs": sorted(evidence_refs),
        "sourceQualification": [
            "CANONICAL_EVENTS_ONLY",
            "IDENTIFIER_BASED_RUN_BINDING",
            "NO_TIMESTAMP_PROXIMITY_INFERENCE",
        ],
        "gaps": sorted(set(gaps)),
        "limitations": sorted(limitations),
        "provenance": provenance,
    }
    # Content-addressed identity — the same bundle content always yields the
    # same ID; any changed input produces a distinguishable bundle.
    bundle["bundleId"] = "ls-bundle:" + _digest(bundle)[:24]
    return bundle


def bundle_for_control7(
    *,
    case_id: str,
    run_declaration: Mapping[str, Any],
    run_resolution: Mapping[str, Any],
    expected_manifest: Mapping[str, Any],
    measurement: Mapping[str, Any],
    analysis: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    existing_measurements: Mapping[str, Mapping[str, Any]] | None = None,
    run_activity: Mapping[str, Any] | None = None,
    canonical_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for the bundle — C7 block plus any other
    snapshot-current measurement blocks already persisted for the run."""
    blocks: dict[str, Mapping[str, Any]] = dict(existing_measurements or {})
    blocks[CONTROL7_CODE] = measurement
    return build_competition_bundle(
        case_id=case_id,
        run_declaration=run_declaration,
        run_resolution=run_resolution,
        expected_manifest=expected_manifest,
        measurements=blocks,
        analysis=analysis,
        report=report,
        primary_measurement_code=CONTROL7_CODE,
        run_activity=run_activity,
        canonical_events=canonical_events,
    )


def bundle_for_control16(
    *,
    case_id: str,
    run_declaration: Mapping[str, Any],
    run_resolution: Mapping[str, Any],
    measurement: Mapping[str, Any],
    expected_manifest: Mapping[str, Any] | None = None,
    analysis: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    existing_measurements: Mapping[str, Mapping[str, Any]] | None = None,
    run_activity: Mapping[str, Any] | None = None,
    canonical_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bundle for an ACN-COST-001 reconciliation over the shared envelope.

    Any already-persisted measurement blocks for the same run (e.g. C7) are
    carried alongside so the bundle remains the single handoff surface.
    """
    blocks: dict[str, Mapping[str, Any]] = dict(existing_measurements or {})
    blocks[CONTROL16_CODE] = measurement
    return build_competition_bundle(
        case_id=case_id,
        run_declaration=run_declaration,
        run_resolution=run_resolution,
        expected_manifest=expected_manifest,
        measurements=blocks,
        analysis=analysis,
        report=report,
        primary_measurement_code=CONTROL16_CODE,
        run_activity=run_activity,
        canonical_events=canonical_events,
    )


def bundle_for_control9(
    *,
    case_id: str,
    run_declaration: Mapping[str, Any],
    run_resolution: Mapping[str, Any],
    measurement: Mapping[str, Any],
    expected_manifest: Mapping[str, Any] | None = None,
    analysis: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    existing_measurements: Mapping[str, Mapping[str, Any]] | None = None,
    run_activity: Mapping[str, Any] | None = None,
    canonical_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bundle for an AIA-ARC-006 drift measurement over the shared envelope.

    Any already-persisted measurement blocks for the same run (C7/C16) are
    carried alongside so the bundle remains the single handoff surface. C7
    manifest identity never leaks into the C9 primary envelope.
    """
    blocks: dict[str, Mapping[str, Any]] = dict(existing_measurements or {})
    blocks[CONTROL9_CODE] = measurement
    return build_competition_bundle(
        case_id=case_id,
        run_declaration=run_declaration,
        run_resolution=run_resolution,
        expected_manifest=expected_manifest,
        measurements=blocks,
        analysis=analysis,
        report=report,
        primary_measurement_code=CONTROL9_CODE,
        run_activity=run_activity,
        canonical_events=canonical_events,
    )
