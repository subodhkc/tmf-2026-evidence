from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from logsense.adapters.mapping_profiles import MappingProfileEntry, load_default_mapping_registry
from logsense.adapters.profiling import profile_artifact
from logsense.adapters.qualification_records import project_adapter_qualification_records
from logsense.adapters.runtime_mapping import MappingProposal, bind_approved_mapping
from logsense.ai.tools import InvestigatorToolbox
from logsense.analysis.spine import ArtifactEvidence, analyze_artifacts
from logsense.competition.bundle import (
    bundle_for_control7,
    bundle_for_control9,
    bundle_for_control16,
)
from logsense.competition.control7 import CONTROL7_CODE, measure_event_recording
from logsense.competition.control9 import (
    CONTROL9_CODE,
    aggregate_live_windows,
    builtin_metric_profiles,
    compatibility_gate,
    measure_drift,
    normalize_control9_baseline,
    normalize_metric_profile,
    project_kpi_observations,
)
from logsense.competition.control16 import CONTROL16_CODE, reconcile_run_usage
from logsense.competition.event_pack import build_judge_pack
from logsense.competition.event_readiness import (
    control_feasibility,
    gap_register,
    judgment_day_readiness,
    run_id_map,
    run_register,
    source_inventory,
)
from logsense.competition.expected_events import (
    RUN_SCOPED_MATCH_FIELDS,
    normalize_manifest,
)
from logsense.competition.expected_events import (
    manifest_templates as expected_manifest_templates,
)
from logsense.competition.fixture_packs import load_fixture
from logsense.competition.guidance import (
    ai_guidance_context as _ai_guidance_context,
)
from logsense.competition.guidance import (
    capability_truth,
)
from logsense.competition.run import normalize_run_declaration, resolve_competition_run
from logsense.competition.run_activity import (
    is_run_lifecycle_event,
    resolve_run_activity,
)
from logsense.competition.run_discovery import discover_run_candidates
from logsense.competition.source_registry import (
    capability_matrix,
    control_source_feasibility,
    enforcement_point_discovery,
    first_hour_dashboard,
    source_registry,
)
from logsense.forensics.reporting import build_report_from_analysis
from logsense.forensics.temporal import sequence_continuity
from logsense.forensics.verification_workflow import (
    finalize_frontier_verification,
    prepare_frontier_verification,
)
from logsense.pipeline.intake import commit_evidence, preview_evidence
from logsense.user_config import resolve_workspace_root
from logsense.workspace.analysis_snapshots import (
    active_snapshot_id,
    list_analysis_snapshots,
    load_analysis_snapshot,
    save_analysis_snapshot,
    set_active_snapshot,
)
from logsense.workspace.cases import (
    case_artifact_rows,
    commit_evidence_to_case,
    create_case,
    evidence_inventory,
    list_case_output_names,
    list_cases,
    list_manifests,
    load_case,
    load_case_output,
    read_case_artifact,
    save_case_output,
)


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class IntegrationRequestError(ValueError):
    """Raised when a transport supplies an invalid integration request."""


def integration_capability_manifest() -> dict[str, Any]:
    """Transport-neutral capabilities exposed by API/MCP adapters."""
    return {
        "schemaVersion": "1.0",
        "service": "logsense-local-integration",
        "truthOwner": "DETERMINISTIC_LOGSENSE_CORE",
        "canonicalMutationAllowed": False,
        "operations": [
            {"name": "create_case", "mode": "ORCHESTRATION_MUTATION"},
            {"name": "list_cases", "mode": "READ_ONLY"},
            {"name": "import_evidence", "mode": "ORCHESTRATION_MUTATION"},
            {"name": "analyze", "mode": "ORCHESTRATION_MUTATION"},
            {"name": "get_snapshot", "mode": "READ_ONLY"},
            {"name": "get_findings", "mode": "READ_ONLY"},
            {"name": "prepare_verification", "mode": "ORCHESTRATION_MUTATION"},
            {"name": "finalize_verification", "mode": "ORCHESTRATION_MUTATION"},
            {"name": "build_report", "mode": "READ_ONLY"},
            {"name": "export_report_json", "mode": "ORCHESTRATION_EXPORT"},
            {"name": "invoke_investigator_tool", "mode": "READ_ONLY"},
        ],
        "forbiddenDirectWrites": [
            "FORENSIC_CLAIM",
            "RELATION_STATE",
            "CAUSE_STATE",
            "BASELINE",
            "APPROVED_MAPPING",
            "FRONTIER_CLOSURE_OUTCOME",
        ],
        "notes": [
            "API_AND_MCP_CALL_SAME_SERVICE_FACADE",
            "NO_DUPLICATE_NORMALIZATION",
            "EVIDENCE_IMPORT_USES_CANONICAL_PREVIEW_COMMIT_PIPELINE",
            "VERIFICATION_USES_CANONICAL_PREPARE_FINALIZE_WORKFLOW",
            "TRANSPORT_OUTPUT_DOES_NOT_ESTABLISH_FORENSIC_TRUTH",
        ],
    }


def _required_text(request: Mapping[str, Any], key: str) -> str:
    value = str(request.get(key) or "").strip()
    if not value:
        raise IntegrationRequestError(f"{key} is required")
    return value


def _decode_base64(value: Any, *, label: str) -> bytes:
    encoded = str(value or "")
    if not encoded:
        raise IntegrationRequestError(f"{label} contentBase64 is required")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise IntegrationRequestError(f"{label} contentBase64 is invalid") from exc


def _decode_artifact(row: Mapping[str, Any]) -> ArtifactEvidence:
    return ArtifactEvidence(
        artifact_id=_required_text(row, "artifactId"),
        path=_required_text(row, "path"),
        content=_decode_base64(row.get("contentBase64"), label="artifact"),
        ingested_at=_required_text(row, "ingestedAt"),
        media_type=str(row["mediaType"]) if row.get("mediaType") is not None else None,
        currentness=str(row.get("currentness") or "UNKNOWN"),
        completeness_state=str(row.get("completenessState") or "UNKNOWN"),
        environment=str(row["environment"]) if row.get("environment") is not None else None,
        producer=str(row["producer"]) if row.get("producer") is not None else None,
    )


def _artifact_rows(request: Mapping[str, Any], key: str = "artifacts") -> list[ArtifactEvidence]:
    rows = request.get(key)
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)) or not rows:
        raise IntegrationRequestError(f"{key} must be a non-empty array")
    artifacts: list[ArtifactEvidence] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise IntegrationRequestError(f"each {key} entry must be an object")
        artifacts.append(_decode_artifact(row))
    return artifacts


class IntegrationService:
    """One transport-neutral facade over canonical LogSense services.

    FastAPI, MCP, CLI/UI integrations should call this class instead of
    implementing normalization, forensic state, report logic, or AI truth.
    """

    def __init__(self, *, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = resolve_workspace_root(workspace_root)

    def capabilities(self) -> dict[str, Any]:
        return integration_capability_manifest()

    def create_case(
        self, *, case_id: str, title: str | None = None, created_at: str | None = None
    ) -> dict[str, Any]:
        row = create_case(self.workspace_root, case_id=case_id, title=title, created_at=created_at)
        return {
            "caseId": row.case_id,
            "title": row.title,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
            "schemaVersion": row.schema_version,
        }

    def list_cases(self) -> list[dict[str, Any]]:
        return [
            {
                "caseId": row.case_id,
                "title": row.title,
                "createdAt": row.created_at,
                "updatedAt": row.updated_at,
                "schemaVersion": row.schema_version,
            }
            for row in list_cases(self.workspace_root)
        ]

    def import_evidence(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Stage transport bytes then use the same canonical intake/commit path as the UI."""
        case_id = _required_text(request, "caseId")
        rows = request.get("files")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)) or not rows:
            raise IntegrationRequestError("files must be a non-empty array")
        with tempfile.TemporaryDirectory(prefix="logsense-integration-") as temp_root:
            root = Path(temp_root)
            paths: list[Path] = []
            used_names: set[str] = set()
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, Mapping):
                    raise IntegrationRequestError("each file must be an object")
                filename = Path(_required_text(row, "name")).name
                if filename in {"", ".", ".."}:
                    raise IntegrationRequestError("file name is invalid")
                safe_name = filename if filename not in used_names else f"{index}-{filename}"
                used_names.add(safe_name)
                target = root / safe_name
                target.write_bytes(_decode_base64(row.get("contentBase64"), label="file"))
                paths.append(target)
            manifest = preview_evidence(paths)
            committed = commit_evidence(manifest)
            return commit_evidence_to_case(
                self.workspace_root,
                case_id=case_id,
                committed=committed,
                committed_at=(
                    str(request["committedAt"]) if request.get("committedAt") is not None else None
                ),
            )

    def analyze(self, request: Mapping[str, Any]) -> dict[str, Any]:
        artifacts = _artifact_rows(request)
        expected_roles = request.get("expectedSourceRoles") or ()
        if not isinstance(expected_roles, Sequence) or isinstance(
            expected_roles, (str, bytes, bytearray)
        ):
            raise IntegrationRequestError("expectedSourceRoles must be an array")
        return analyze_artifacts(
            artifacts,
            case_id=_required_text(request, "caseId"),
            evidence_set_id=_required_text(request, "evidenceSetId"),
            analysis_run_id=_required_text(request, "analysisRunId"),
            created_at=_required_text(request, "createdAt"),
            expected_source_roles=tuple(str(item) for item in expected_roles),
        )

    def case_artifacts(self, case_id: str) -> list[ArtifactEvidence]:
        """Rehydrate committed immutable artifacts for deterministic re-analysis."""
        artifacts: list[ArtifactEvidence] = []
        for row in case_artifact_rows(self.workspace_root, case_id):
            artifacts.append(
                ArtifactEvidence(
                    artifact_id=str(row["artifact_id"]),
                    path=str(row["logical_path"]),
                    content=read_case_artifact(self.workspace_root, case_id, row),
                    ingested_at=str(row["committed_at"]),
                    media_type=str(row["media_type"]) if row.get("media_type") else None,
                )
            )
        return artifacts

    def analyze_case(
        self,
        *,
        case_id: str,
        evidence_set_id: str | None = None,
        analysis_run_id: str | None = None,
        created_at: str | None = None,
        expected_source_roles: Sequence[str] = (),
        approved_mappings: Mapping[str, MappingProfileEntry] | None = None,
        save: bool = True,
    ) -> dict[str, Any]:
        """Run the canonical spine over the case's committed evidence.

        The UI/API/CLI all reach deterministic truth through this path; callers
        never handle raw artifact bytes or internal JSON documents. Run
        identifiers default to content-derived values so re-analyzing unchanged
        evidence is reproducible. When ``approved_mappings`` is not supplied,
        persisted case mapping approvals (recorded via
        ``approve_case_mapping``) are loaded automatically.
        """
        load_case(self.workspace_root, case_id)
        artifacts = self.case_artifacts(case_id)
        if not artifacts:
            raise IntegrationRequestError(
                f"case '{case_id}' has no committed evidence; add evidence before running analysis"
            )
        if approved_mappings is None:
            approved_mappings = self.load_case_mapping_approvals(case_id)
        seed = "".join(sorted(artifact.artifact_id for artifact in artifacts))
        digest = hashlib.sha256(seed.encode()).hexdigest()[:16]
        analysis = analyze_artifacts(
            artifacts,
            case_id=case_id,
            evidence_set_id=evidence_set_id or f"{case_id}:evidence:{digest}",
            analysis_run_id=analysis_run_id or f"{case_id}:run:{digest}",
            created_at=created_at or _utc_now(),
            expected_source_roles=tuple(str(role) for role in expected_source_roles),
            approved_mappings=approved_mappings,
        )
        report = self.build_report(analysis, rendered_at=created_at)
        if save:
            save_analysis_snapshot(
                self.workspace_root,
                case_id,
                analysis=analysis,
                report=report,
                mapping_profile_refs=[
                    str(entry.mapping_profile["profileId"])
                    for entry in (approved_mappings or {}).values()
                    if isinstance(entry.mapping_profile, Mapping)
                    and entry.mapping_profile.get("profileId")
                ],
            )
            # Legacy flat outputs kept in sync for transport compatibility;
            # the snapshot store is authoritative.
            save_case_output(self.workspace_root, case_id, name="analysis", payload=analysis)
            save_case_output(self.workspace_root, case_id, name="report", payload=report)
        return {"analysis": analysis, "report": report}

    def load_case_results(self, case_id: str) -> dict[str, Any] | None:
        """Return the case's active analysis/report pair, or None.

        Resolves through the immutable snapshot store when snapshots exist;
        falls back to legacy flat outputs for cases analyzed before the
        snapshot store shipped.
        """
        load_case(self.workspace_root, case_id)
        snapshot_ref = active_snapshot_id(self.workspace_root, case_id)
        if snapshot_ref:
            record = load_analysis_snapshot(self.workspace_root, case_id, snapshot_ref)
            if record is not None:
                return {"analysis": record.get("analysis"), "report": record.get("report")}
        analysis = load_case_output(self.workspace_root, case_id, name="analysis")
        if analysis is None:
            return None
        report = load_case_output(self.workspace_root, case_id, name="report")
        return {"analysis": analysis, "report": report}

    # ---- immutable analysis snapshots (R5-03) --------------------------------

    @staticmethod
    def _analysis_stale_reasons(
        analysis: Mapping[str, Any],
        artifact_rows: Sequence[Mapping[str, Any]],
        approvals: Mapping[str, MappingProfileEntry],
    ) -> list[str]:
        """Content-based staleness — never timestamp-fragile comparisons."""
        saved_rows = {str(r["artifactId"]): r for r in analysis.get("artifactResults") or ()}
        committed = {str(r["artifact_id"]): str(r["sha256"]) for r in artifact_rows}
        reasons: list[str] = []
        if set(saved_rows) != set(committed):
            reasons.append("EVIDENCE_COMMITTED_AFTER_ANALYSIS")
        elif any(saved_rows[aid].get("sha256") != committed[aid] for aid in saved_rows):
            reasons.append("EVIDENCE_CHANGED_AFTER_ANALYSIS")
        if any(
            aid not in saved_rows
            or "EXPLICIT_RUNTIME_MAPPING_BINDING" not in (saved_rows[aid].get("limitations") or ())
            for aid in approvals
        ):
            reasons.append("MAPPING_APPROVED_AFTER_ANALYSIS")
        return reasons

    def analysis_snapshot_state(self, case_id: str) -> dict[str, Any]:
        """Centralized snapshot state for the case's active analysis.

        States: NONE (no analysis), CURRENT, STALE_EVIDENCE_CHANGED,
        STALE_MAPPING_CHANGED. ``provenance`` distinguishes real snapshot
        records from legacy flat outputs (LEGACY_ACTIVE_OUTPUT) — legacy
        outputs never gain fabricated provenance fields.
        """
        load_case(self.workspace_root, case_id)
        snapshot_ref = active_snapshot_id(self.workspace_root, case_id)
        results = self.load_case_results(case_id)
        if not results or not isinstance(results.get("analysis"), Mapping):
            return {
                "state": "NONE",
                "snapshotId": snapshot_ref,
                "provenance": "NONE",
                "staleReasons": [],
            }
        analysis = results["analysis"]
        reasons = self._analysis_stale_reasons(
            analysis,
            list(case_artifact_rows(self.workspace_root, case_id)),
            self.load_case_mapping_approvals(case_id),
        )
        if reasons and any(r.startswith("EVIDENCE_") for r in reasons):
            state = "STALE_EVIDENCE_CHANGED"
        elif reasons:
            state = "STALE_MAPPING_CHANGED"
        else:
            state = "CURRENT"
        return {
            "state": state,
            "snapshotId": snapshot_ref,
            "snapshotLabel": (
                (self._snapshot_metadata(case_id, snapshot_ref) or {}).get("snapshotLabel")
                if snapshot_ref
                else None
            ),
            "analysisRunId": analysis.get("analysisRunId"),
            "createdAt": (analysis.get("snapshot") or {}).get("createdAt"),
            "provenance": "SNAPSHOT" if snapshot_ref else "LEGACY_ACTIVE_OUTPUT",
            "staleReasons": reasons,
        }

    def _snapshot_metadata(self, case_id: str, snapshot_id: str | None) -> dict[str, Any] | None:
        if not snapshot_id:
            return None
        return next(
            (
                row
                for row in self.list_analysis_snapshots(case_id)
                if row["snapshotId"] == snapshot_id
            ),
            None,
        )

    def list_analysis_snapshots(self, case_id: str) -> list[dict[str, Any]]:
        """Snapshot history metadata, oldest first; each row marked active or not."""
        load_case(self.workspace_root, case_id)
        active = active_snapshot_id(self.workspace_root, case_id)
        rows = []
        for row in list_analysis_snapshots(self.workspace_root, case_id):
            row["active"] = row["snapshotId"] == active
            rows.append(row)
        return rows

    def set_active_snapshot(self, *, case_id: str, snapshot_id: str) -> dict[str, Any]:
        """Repoint the active snapshot and resync the compat flat outputs.

        The snapshot itself is immutable; activating a historical snapshot
        never rewrites it and never fabricates provenance.
        """
        load_case(self.workspace_root, case_id)
        try:
            record = set_active_snapshot(self.workspace_root, case_id, snapshot_id)
        except KeyError as exc:
            raise IntegrationRequestError(str(exc)) from exc
        save_case_output(self.workspace_root, case_id, name="analysis", payload=record["analysis"])
        save_case_output(
            self.workspace_root,
            case_id,
            name="report",
            payload=cast("dict[str, Any]", record.get("report")) or {},
        )
        metadata = {k: v for k, v in record.items() if k not in {"analysis", "report"}}
        return metadata

    # ---- collection health (R5-03) --------------------------------------------

    def collection_health(self, case_id: str) -> dict[str, Any]:
        """Local forensic collection-health projection.

        Answers: what evidence was received, how successfully it parsed, and
        which limitations bound coverage. Never a PASS/FAIL verdict — unknown
        dimensions stay NOT_MEASURED / NOT_ASSESSED.
        """
        load_case(self.workspace_root, case_id)
        artifact_rows = list(case_artifact_rows(self.workspace_root, case_id))
        if not artifact_rows:
            return {
                "schemaVersion": "collection-health/0.1",
                "caseId": case_id,
                "state": "NO_EVIDENCE",
                "artifacts": 0,
                "sources": [],
                "totals": {},
                "observedTime": None,
                "limitations": ["NO_EVIDENCE_COMMITTED"],
            }
        results = self.load_case_results(case_id)
        analysis = (results or {}).get("analysis") or {}
        if not analysis:
            return {
                "schemaVersion": "collection-health/0.1",
                "caseId": case_id,
                "state": "ANALYSIS_REQUIRED",
                "artifacts": len(artifact_rows),
                "sources": [
                    {
                        "artifactId": str(row["artifact_id"]),
                        "path": str(row["logical_path"]),
                        "adapterId": row.get("adapter_id"),
                        "profileState": "NOT_ASSESSED",
                    }
                    for row in artifact_rows
                ],
                "totals": {},
                "observedTime": None,
                "limitations": ["RUN_DETERMINISTIC_ANALYSIS_FOR_COLLECTION_HEALTH"],
            }

        descriptor_by_id = {str(d["sourceId"]): d for d in analysis.get("sourceDescriptors") or ()}

        def _source_id_for(row: Mapping[str, Any]) -> str:
            seed = f"{row.get('path')}\0{row.get('sha256')}".encode()
            return f"source:{hashlib.sha256(seed).hexdigest()[:24]}"

        sources: list[dict[str, Any]] = []
        for row in analysis.get("artifactResults") or ():
            descriptor = descriptor_by_id.get(_source_id_for(row))
            sources.append(
                {
                    "artifactId": row.get("artifactId"),
                    "path": row.get("path"),
                    "producer": (descriptor or {}).get("producer"),
                    "acquisition": "LOCAL_EVIDENCE_INTAKE",
                    "adapterId": row.get("syntaxAdapterId"),
                    "semanticProfileIds": list(row.get("semanticProfileIds") or ()),
                    "profileState": row.get("profileState"),
                    "recordCount": row.get("recordCount"),
                    "parsedRecordCount": row.get("parsedRecordCount"),
                    "failedRecordCount": row.get("failedRecordCount"),
                    "canonicalEventCount": row.get("canonicalEventCount"),
                    "integrityState": (descriptor or {}).get("integrityState", "NOT_ASSESSED"),
                    "limitations": sorted(set(row.get("limitations") or ())),
                }
            )

        totals = {
            "recordCount": sum(int(r.get("recordCount") or 0) for r in sources),
            "parsedRecordCount": sum(int(r.get("parsedRecordCount") or 0) for r in sources),
            "failedRecordCount": sum(int(r.get("failedRecordCount") or 0) for r in sources),
            "canonicalEventCount": len(analysis.get("canonicalEvents") or ()),
            "quarantinedRecordCount": "NOT_MEASURED",
        }
        coverage = dict(analysis.get("sourceCoverage") or {})
        independence = dict(analysis.get("sourceIndependence") or {})
        duplicate_groups = independence.get("duplicateGroups") or []

        time_states = [
            str(n.get("state"))
            for n in analysis.get("temporalNormalizations") or ()
            if n.get("state")
        ]
        if not time_states:
            time_quality = "NOT_MEASURED"
        elif all(s in {"EXACT", "NORMALIZED", "ALIGNED"} for s in time_states):
            time_quality = "NORMALIZED"
        elif all(s in {"MISSING", "UNKNOWN"} for s in time_states):
            time_quality = "UNKNOWN"
        else:
            time_quality = "PARTIAL"

        # Per-source sequence continuity where the source carried a seq field.
        continuity_by_source: dict[str, str] = {}
        events_by_source: dict[str, list[Mapping[str, Any]]] = {}
        for event in analysis.get("canonicalEvents") or ():
            source_ref = str(event.get("sourceRef") or "")
            if source_ref:
                events_by_source.setdefault(source_ref, []).append(event)
        for source_ref, events in sorted(events_by_source.items()):
            attrs = [e.get("attributes") or {} for e in events]
            continuity = sequence_continuity(
                attrs,
                continuity_id=f"{analysis.get('analysisRunId')}:health:{source_ref}",
                analysis_run_id=str(analysis.get("analysisRunId")),
                source_ref=source_ref,
                evidence_refs=[str(e.get("eventId")) for e in events],
            )
            continuity_by_source[source_ref] = str(continuity["state"])
        if not continuity_by_source:
            continuity_state = "NOT_MEASURED"
        elif all(s == "PROVEN_CONTIGUOUS" for s in continuity_by_source.values()):
            continuity_state = "PROVEN_CONTIGUOUS"
        elif any(s == "CONTRADICTED" for s in continuity_by_source.values()):
            continuity_state = "CONTRADICTED"
        elif any(s == "GAP_DETECTED" for s in continuity_by_source.values()):
            continuity_state = "GAP_DETECTED"
        else:
            continuity_state = "PARTIAL"

        limitations: list[str] = []
        for row in sources:
            limitations.extend(str(x) for x in row["limitations"])
        limitations.extend(str(x) for x in coverage.get("limitations") or ())
        limitations.extend(str(x) for x in independence.get("limitations") or ())

        return {
            "schemaVersion": "collection-health/0.1",
            "caseId": case_id,
            "state": "REPORTED",
            "artifacts": len(artifact_rows),
            "parsedSources": sum(1 for r in sources if r["profileState"] in {"PARSED", "PARTIAL"}),
            "preservedOnlySources": sum(
                1 for r in sources if r["profileState"] in {"OPAQUE_UNPARSED", "FAILED"}
            ),
            "sources": sources,
            "totals": totals,
            "duplicateGroups": (
                len(duplicate_groups) if "duplicateGroups" in independence else "NOT_MEASURED"
            ),
            "observedTime": coverage.get("timeCoverage"),
            "timeQuality": time_quality,
            "continuityState": continuity_state,
            "continuityBySource": continuity_by_source,
            "coverageState": coverage.get("completenessState", "NOT_ASSESSED"),
            "sourceIndependence": {
                "independentLineageCount": independence.get(
                    "independentLineageCount", "NOT_MEASURED"
                ),
                "duplicateGroups": duplicate_groups,
                "limitations": list(independence.get("limitations") or ()),
            },
            "limitations": sorted(set(limitations)),
        }

    # ---- run discovery / confirmation / active run (R5-03) ----------------------

    RUN_ROLES = ("CALIBRATION", "ASSESSED_PASS", "ASSESSED_BREACH", "RETEST", "OTHER")

    def discover_case_run_candidates(self, case_id: str) -> dict[str, Any]:
        """Discover candidate executions from explicit event identifiers.

        Read-only: candidates are proposals — nothing is declared or bound
        until the operator confirms a run.
        """
        analysis = self._required_analysis(case_id)
        existing = self.list_competition_runs(case_id)
        declared_kinds = sorted(
            {kind for run in existing for kind in run.get("declaredIdentifiers") or {}}
        )
        result = discover_run_candidates(
            list(analysis.get("canonicalEvents") or ()),
            declared_kinds=declared_kinds,
            existing_declarations=existing,
        )
        result["caseId"] = case_id
        result["analysisRunId"] = analysis.get("analysisRunId")
        result["snapshotState"] = self.analysis_snapshot_state(case_id)["state"]
        return result

    def confirm_competition_run(
        self,
        *,
        case_id: str,
        run_role: str,
        declaration: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        scenario_label: str | None = None,
    ) -> dict[str, Any]:
        """Confirm a discovered candidate or existing declaration as a case run.

        ``run_role`` is descriptive workflow metadata (CALIBRATION /
        ASSESSED_PASS / ASSESSED_BREACH / RETEST / OTHER) — never a control
        verdict. The confirmation binds the run to the *active* snapshot at
        confirmation time.
        """
        load_case(self.workspace_root, case_id)
        role = str(run_role or "").strip().upper()
        if role not in self.RUN_ROLES:
            raise IntegrationRequestError(
                f"runRole must be one of {', '.join(self.RUN_ROLES)} (got {run_role!r})"
            )
        snapshot = self.analysis_snapshot_state(case_id)
        if snapshot["state"] == "NONE":
            raise IntegrationRequestError(
                "run deterministic analysis before confirming a run — "
                "confirmations bind to an analysis snapshot"
            )
        if declaration is None:
            if run_id is None:
                raise IntegrationRequestError("confirm requires a declaration or runId")
            stored = self.load_competition_run(case_id, run_id)
            if stored is None:
                raise IntegrationRequestError(f"competition run not declared: {run_id}")
            normalized = dict(stored)
        else:
            normalized = (
                dict(declaration)
                if declaration.get("schemaVersion") == "competition-run-declaration/0.1"
                else normalize_run_declaration(declaration)
            )
        confirmed_run_id = str(normalized["runId"])
        # Persist the declaration first so the canonical resolver path can load it.
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-run", confirmed_run_id),
            payload=normalized,
        )
        resolution = self.resolve_case_run(case_id=case_id, run_id=confirmed_run_id)
        normalized["runRole"] = role
        normalized["scenarioLabel"] = scenario_label or None
        normalized["confirmedAt"] = _utc_now()
        normalized["analysisRunId"] = snapshot.get("analysisRunId")
        normalized["snapshotRef"] = snapshot.get("snapshotId")
        normalized["runResolutionRef"] = f"competition-resolution:{confirmed_run_id}"
        normalized["qualifiedEventRefs"] = list(resolution["qualifiedEventRefs"])
        normalized["ambiguousEvidenceRefs"] = list(resolution["ambiguousEvidenceRefs"])
        normalized["unresolvedEvidenceRefs"] = list(resolution["unresolvedEvidenceRefs"])
        normalized["resolutionState"] = resolution["resolutionState"]
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-run", confirmed_run_id),
            payload=normalized,
        )
        return {"run": normalized, "resolution": resolution}

    def set_active_run(self, *, case_id: str, run_id: str | None) -> dict[str, Any]:
        """Select (or clear) the case's global active competition run."""
        load_case(self.workspace_root, case_id)
        if run_id is None:
            save_case_output(
                self.workspace_root, case_id, name="active-run", payload={"runId": None}
            )
            return {"state": "NOT_SELECTED", "runId": None}
        record = self.load_competition_run(case_id, run_id)
        if record is None:
            raise IntegrationRequestError(f"competition run not declared or confirmed: {run_id}")
        save_case_output(
            self.workspace_root,
            case_id,
            name="active-run",
            payload={"runId": str(record["runId"]), "selectedAt": _utc_now()},
        )
        return self.active_run(case_id)

    def active_run(self, case_id: str) -> dict[str, Any]:
        """The case's globally selected competition run, or NOT_SELECTED."""
        load_case(self.workspace_root, case_id)
        payload = load_case_output(self.workspace_root, case_id, name="active-run")
        run_id = str((payload or {}).get("runId") or "")
        if not run_id:
            return {"state": "NOT_SELECTED", "runId": None}
        record = self.load_competition_run(case_id, run_id)
        if record is None:
            return {"state": "NOT_SELECTED", "runId": None}
        resolution = self.load_competition_resolution(case_id, run_id) or {}
        return {
            "state": "SELECTED",
            "runId": run_id,
            "label": record.get("label") or run_id,
            "runRole": record.get("runRole"),
            "scenarioLabel": record.get("scenarioLabel"),
            "snapshotRef": record.get("snapshotRef"),
            "resolutionState": record.get("resolutionState") or resolution.get("resolutionState"),
            "qualifiedEventCount": len(record.get("qualifiedEventRefs") or ()),
            "ambiguousCount": len(record.get("ambiguousEvidenceRefs") or ()),
            "unresolvedCount": len(record.get("unresolvedEvidenceRefs") or ()),
        }

    def export_checkpoint(self, case_id: str) -> dict[str, Any]:
        """Lightweight recovery/orientation checkpoint — identities only,
        never duplicated raw evidence."""
        load_case(self.workspace_root, case_id)
        snapshot = self.analysis_snapshot_state(case_id)
        active = self.active_run(case_id)
        health = self.collection_health(case_id)
        results = self.load_case_results(case_id) or {}
        analysis = results.get("analysis") or {}
        approvals = self.load_case_mapping_approvals(case_id)
        return {
            "schemaVersion": "competition-checkpoint/0.1",
            "caseId": case_id,
            "createdAt": _utc_now(),
            "activeSnapshotRef": snapshot.get("snapshotId"),
            "snapshotLabel": snapshot.get("snapshotLabel"),
            "snapshotState": snapshot["state"],
            "analysisRunId": snapshot.get("analysisRunId"),
            "evidenceSetRef": analysis.get("evidenceSetId"),
            "artifactDigests": sorted(
                str(r["sha256"]) for r in analysis.get("artifactResults") or () if r.get("sha256")
            ),
            "mappingProfileRefs": sorted(
                str(entry.mapping_profile["profileId"])
                for entry in approvals.values()
                if isinstance(entry.mapping_profile, Mapping)
                and entry.mapping_profile.get("profileId")
            ),
            "activeRunId": active.get("runId"),
            "runRole": active.get("runRole"),
            "collectionHealth": {
                "state": health["state"],
                "artifacts": health.get("artifacts"),
                "failedRecordCount": (health.get("totals") or {}).get("failedRecordCount"),
                "coverageState": health.get("coverageState"),
            },
            "openGaps": len(analysis.get("evidenceFrontier") or ()),
            "confirmedRuns": [
                {
                    "runId": r.get("runId"),
                    "runRole": r.get("runRole"),
                    "resolutionState": r.get("resolutionState"),
                }
                for r in self.list_competition_runs(case_id)
            ],
            "limitations": [
                "CHECKPOINT_CARRIES_IDENTITIES_NOT_EVIDENCE",
                "RESTORE_REQUIRES_THE_UNDERLYING_CASE_WORKSPACE",
            ],
        }

    def get_snapshot(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = analysis.get("snapshot")
        if not isinstance(snapshot, Mapping):
            raise IntegrationRequestError("analysis does not contain a snapshot")
        return deepcopy(dict(snapshot))

    def get_findings(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "caseId": analysis.get("caseId"),
            "analysisRunId": analysis.get("analysisRunId"),
            "gaps": deepcopy(list(analysis.get("gaps") or ())),
            "contradictions": deepcopy(list(analysis.get("contradictions") or ())),
            "causeEvaluations": deepcopy(list(analysis.get("causeEvaluations") or ())),
            "evidenceFrontier": deepcopy(list(analysis.get("evidenceFrontier") or ())),
            "canonicalMutationAllowed": False,
        }

    def prepare_verification(self, request: Mapping[str, Any]) -> dict[str, Any]:
        prior = request.get("priorSnapshot")
        if not isinstance(prior, Mapping):
            raise IntegrationRequestError("priorSnapshot must be an object")
        analysis_kwargs = request.get("analysisKwargs")
        if analysis_kwargs is not None and not isinstance(analysis_kwargs, Mapping):
            raise IntegrationRequestError("analysisKwargs must be an object")
        limitations = request.get("evidenceSetLimitations") or ()
        if not isinstance(limitations, Sequence) or isinstance(
            limitations, (str, bytes, bytearray)
        ):
            raise IntegrationRequestError("evidenceSetLimitations must be an array")
        return prepare_frontier_verification(
            prior_snapshot=prior,
            verification_artifacts=_artifact_rows(request, "artifacts"),
            evidence_set_id=_required_text(request, "evidenceSetId"),
            analysis_run_id=_required_text(request, "analysisRunId"),
            created_at=_required_text(request, "createdAt"),
            evidence_set_label=str(request.get("evidenceSetLabel") or "Verification"),
            evidence_set_role=str(request.get("evidenceSetRole") or "VERIFICATION"),
            evidence_set_limitations=tuple(str(item) for item in limitations),
            analysis_kwargs=analysis_kwargs,
        )

    def finalize_verification(self, request: Mapping[str, Any]) -> dict[str, Any]:
        prepared = request.get("prepared")
        frontier = request.get("frontier")
        forensic_test = request.get("forensicTest")
        if not isinstance(prepared, Mapping):
            raise IntegrationRequestError("prepared must be an object")
        if not isinstance(frontier, Mapping):
            raise IntegrationRequestError("frontier must be an object")
        if not isinstance(forensic_test, Mapping):
            raise IntegrationRequestError("forensicTest must be an object")
        predicate = request.get("documentedNonExecutionPredicate")
        if predicate is not None and not isinstance(predicate, Mapping):
            raise IntegrationRequestError("documentedNonExecutionPredicate must be an object")
        return finalize_frontier_verification(
            prepared,
            frontier=frontier,
            forensic_test=forensic_test,
            closed_at=_required_text(request, "closedAt"),
            closure_basis=str(request.get("closureBasis") or "TEST_RESULT"),
            closure_reason=(
                str(request["closureReason"]) if request.get("closureReason") is not None else None
            ),
            documented_non_execution_predicate=predicate,
        )

    def build_report(
        self, analysis: Mapping[str, Any], *, rendered_at: str | None = None
    ) -> dict[str, Any]:
        return build_report_from_analysis(analysis, rendered_at=rendered_at)

    def export_report_json(self, analysis: Mapping[str, Any]) -> str:
        report = self.build_report(analysis)
        return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def invoke_investigator_tool(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        analysis: Mapping[str, Any] | None = None,
        report: Mapping[str, Any] | None = None,
        competition: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        toolbox = InvestigatorToolbox(analysis=analysis, report=report, competition=competition)
        return toolbox.invoke(tool_name, **dict(arguments or {}))

    # ---- runtime mapping approvals -------------------------------------------

    @staticmethod
    def _approval_entry_payload(
        entry: MappingProfileEntry, *, approval_source: str
    ) -> dict[str, Any]:
        return {
            "fixtureRef": entry.fixture_ref,
            "benchmarkId": entry.benchmark_id,
            "artifactPath": entry.artifact_path,
            "artifactId": entry.artifact_id,
            "artifactSha256": entry.artifact_sha256,
            "syntaxAdapterId": entry.syntax_adapter_id,
            "semanticProfileIds": list(entry.semantic_profile_ids),
            "mappingProfile": entry.mapping_profile,
            "approvalSource": approval_source,
        }

    @staticmethod
    def _approval_entry(payload: Mapping[str, Any]) -> MappingProfileEntry:
        return MappingProfileEntry(
            fixture_ref=str(payload["fixtureRef"]),
            benchmark_id=str(payload["benchmarkId"]),
            artifact_path=str(payload["artifactPath"]),
            artifact_id=str(payload["artifactId"]),
            artifact_sha256=str(payload["artifactSha256"]),
            syntax_adapter_id=str(payload["syntaxAdapterId"]),
            semantic_profile_ids=tuple(str(x) for x in payload["semanticProfileIds"]),
            mapping_profile=dict(payload["mappingProfile"]),
        )

    def load_case_mapping_approvals(self, case_id: str) -> dict[str, MappingProfileEntry]:
        """Load persisted USER-approved runtime mappings for the case."""
        payload = load_case_output(self.workspace_root, case_id, name="mapping-approvals")
        entries: dict[str, MappingProfileEntry] = {}
        for row in (payload or {}).get("approvals") or ():
            entry = self._approval_entry(row)
            entries[entry.artifact_id] = entry
        return entries

    def approve_case_mapping(
        self,
        *,
        case_id: str,
        artifact_id: str,
        proposal_id: str,
        approval_source: str = "USER_UI",
        _preview_analysis: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record one explicit USER approval binding a proposal to an artifact.

        The binding only takes effect on the next ``analyze_case`` run — the
        canonical spine still verifies fingerprint/adapter/proposal match.
        """
        load_case(self.workspace_root, case_id)
        analysis = dict(
            _preview_analysis or self.analyze_case(case_id=case_id, save=False)["analysis"]
        )
        proposals = analysis.get("mappingProposals") or ()
        row = next(
            (
                item
                for item in proposals
                if str(item.get("artifactId")) == artifact_id
                and str(item.get("proposalId")) == proposal_id
            ),
            None,
        )
        if row is None:
            raise IntegrationRequestError(
                f"no mapping proposal '{proposal_id}' for artifact '{artifact_id}'"
            )
        artifact_rows = {
            str(item["artifact_id"]): item
            for item in case_artifact_rows(self.workspace_root, case_id)
        }
        artifact_row = artifact_rows.get(artifact_id)
        if artifact_row is None:
            raise IntegrationRequestError(f"unknown case artifact: {artifact_id}")
        proposal = MappingProposal.from_dict(row)
        entry = bind_approved_mapping(
            load_default_mapping_registry(),
            proposal,
            artifact_id=artifact_id,
            artifact_path=str(artifact_row["logical_path"]),
            artifact_sha256=str(artifact_row["sha256"]),
            approved_at=_utc_now(),
        )
        existing = (
            load_case_output(self.workspace_root, case_id, name="mapping-approvals") or {}
        ).get("approvals") or []
        approvals = [item for item in existing if str(item.get("artifactId")) != artifact_id]
        approvals.append(self._approval_entry_payload(entry, approval_source=approval_source))
        save_case_output(
            self.workspace_root,
            case_id,
            name="mapping-approvals",
            payload={"schemaVersion": "case-mapping-approvals/0.1", "approvals": approvals},
        )
        return {"approved": self._approval_entry_payload(entry, approval_source=approval_source)}

    # ---- competition runs / manifests / measurements ---------------------------

    @staticmethod
    def _output_name(prefix: str, ident: str) -> str:
        name = f"{prefix}-{ident}"
        if len(name) <= 64:
            return name
        return f"{prefix}-{hashlib.sha256(ident.encode()).hexdigest()[:32]}"

    def declare_competition_run(
        self, *, case_id: str, declaration: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist an operator-declared competition run (``USER_DECLARED``)."""
        load_case(self.workspace_root, case_id)
        normalized = (
            dict(declaration)
            if declaration.get("schemaVersion") == "competition-run-declaration/0.1"
            else normalize_run_declaration(declaration)
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-run", normalized["runId"]),
            payload=normalized,
        )
        return normalized

    def list_competition_runs(self, case_id: str) -> list[dict[str, Any]]:
        load_case(self.workspace_root, case_id)
        runs: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="competition-run-"):
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                runs.append(payload)
        return runs

    def load_competition_run(self, case_id: str, run_id: str) -> dict[str, Any] | None:
        load_case(self.workspace_root, case_id)
        return load_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-run", run_id),
        )

    def load_competition_resolution(self, case_id: str, run_id: str) -> dict[str, Any] | None:
        load_case(self.workspace_root, case_id)
        return load_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-resolution", run_id),
        )

    MANIFEST_SOURCE_BASES = ("BLANK", "CALIBRATION_DRAFT", "TEMPLATE", "IMPORTED")
    _MANIFEST_VERSION_RE = re.compile(r"^expected-manifest-(.+)-v(\d+)$")
    _MANIFEST_REF_RE = re.compile(r"^(.+)@v(\d+)$")

    @staticmethod
    def _manifest_digest(normalized: Mapping[str, Any]) -> str:
        """Content digest over what the operator actually reviewed — semantic
        events, timing, binding, notes, and the proof-relevant origin
        (``sourceBasis``/``limitations``: a calibration-derived draft is not
        the same proof basis as a hand-authored template even when the event
        rows are identical). Version/digest/provenance fields stay excluded
        so re-saving identical content is idempotent."""
        timing = normalized.get("timing")
        if isinstance(timing, Mapping):
            # R5-04B: an absent declaredGapComparator must not silently
            # rewrite the digest of manifests saved before comparators
            # existed — only an explicit LT/LTE is semantic content.
            timing = {
                key: value
                for key, value in timing.items()
                if not (key == "declaredGapComparator" and value is None)
            }
        core = {
            "manifestId": normalized.get("manifestId"),
            "label": normalized.get("label"),
            "runId": normalized.get("runId"),
            "sourceBasis": normalized.get("sourceBasis"),
            "limitations": normalized.get("limitations"),
            "events": normalized.get("events"),
            "timing": timing,
            "references": normalized.get("references"),
            "notes": normalized.get("notes"),
        }
        payload = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save_expected_event_manifest(
        self,
        *,
        case_id: str,
        manifest: Mapping[str, Any],
        source_basis: str | None = None,
    ) -> dict[str, Any]:
        """Persist a reviewed expected-event manifest as an immutable version.

        Saving identical content returns the existing version (idempotent).
        Saving changed content creates ``manifestVersion`` ``vN+1`` — prior
        versions stay intact so historical measurements keep pointing at the
        exact manifest they consumed.
        """
        load_case(self.workspace_root, case_id)
        normalized = normalize_manifest(manifest)
        normalized["schemaVersion"] = "competition-expected-events/0.1"
        manifest_id = str(normalized["manifestId"])
        basis = str(source_basis or normalized.get("sourceBasis") or "IMPORTED").upper()
        if basis not in self.MANIFEST_SOURCE_BASES:
            raise IntegrationRequestError(
                f"sourceBasis must be one of {', '.join(self.MANIFEST_SOURCE_BASES)}"
            )
        normalized["sourceBasis"] = basis
        digest = self._manifest_digest(normalized)

        existing_versions = self.list_expected_manifest_versions(case_id, manifest_id)
        for row in existing_versions:
            if row.get("manifestDigest") == digest:
                return row
        version = len(existing_versions) + 1
        normalized["manifestVersion"] = f"v{version}"
        normalized["manifestDigest"] = digest
        normalized["createdAt"] = _utc_now()
        normalized["manifestRef"] = f"{manifest_id}@v{version}"
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("expected-manifest", f"{manifest_id}-v{version}"),
            payload=normalized,
        )
        # latest pointer — preserves the pre-versioning flat output name
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("expected-manifest", manifest_id),
            payload=normalized,
        )
        return normalized

    def list_expected_manifests(self, case_id: str) -> list[dict[str, Any]]:
        """Latest saved version per manifestId."""
        load_case(self.workspace_root, case_id)
        manifests: list[dict[str, Any]] = []
        for name in list_case_output_names(
            self.workspace_root, case_id, prefix="expected-manifest-"
        ):
            if self._MANIFEST_VERSION_RE.match(name):
                continue
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                manifests.append(payload)
        return manifests

    def list_expected_manifest_versions(
        self, case_id: str, manifest_id: str
    ) -> list[dict[str, Any]]:
        """Every saved immutable version of one manifest, oldest first."""
        load_case(self.workspace_root, case_id)
        versions: list[tuple[int, dict[str, Any]]] = []
        for name in list_case_output_names(
            self.workspace_root, case_id, prefix="expected-manifest-"
        ):
            matched = self._MANIFEST_VERSION_RE.match(name)
            if not matched or matched.group(1) != manifest_id:
                continue
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                versions.append((int(matched.group(2)), payload))
        return [payload for _, payload in sorted(versions, key=lambda pair: pair[0])]

    def load_expected_manifest(
        self, case_id: str, manifest_id: str, *, version: int | None = None
    ) -> dict[str, Any] | None:
        """Load the latest version, or an exact ``manifestId@vN`` version."""
        load_case(self.workspace_root, case_id)
        ref = self._MANIFEST_REF_RE.match(manifest_id)
        if ref:
            manifest_id, version = ref.group(1), int(ref.group(2))
        if version is not None:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name("expected-manifest", f"{manifest_id}-v{version}"),
            )
        return load_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("expected-manifest", manifest_id),
        )

    def manifest_templates(self) -> list[dict[str, Any]]:
        """Built-in manifest templates for the visual builder."""
        return expected_manifest_templates()

    # run-scoped identifier kinds that must never be auto-promoted into a
    # reusable expected manifest — they legitimately change between runs
    _RUN_SCOPED_MATCH_KINDS = RUN_SCOPED_MATCH_FIELDS

    def draft_manifest_from_run(
        self,
        *,
        case_id: str,
        run_id: str,
        manifest_id: str,
        label: str | None = None,
    ) -> dict[str, Any]:
        """Draft an expected-event manifest from a run's QUALIFIED events only.

        Ambiguous, unresolved and unidentified evidence is never consulted.
        Run-scoped identifiers are never embedded — only stable semantic
        fields (eventType / actorId / operation) become match criteria; rows
        without enough stable signal are flagged for operator review rather
        than fabricated. The result is a DRAFT — saving is a separate,
        explicit step.
        """
        load_case(self.workspace_root, case_id)
        record = self.load_competition_run(case_id, run_id)
        if record is None:
            raise IntegrationRequestError(f"competition run not declared or confirmed: {run_id}")
        analysis = self._required_analysis(case_id)
        canonical_events = list(analysis.get("canonicalEvents") or ())
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
        resolution = resolve_competition_run(canonical_events, record, other_declarations=others)
        qualified = {
            str(ref)
            for ref in (resolution.get("qualifiedEventRefs") or resolution.get("eventRefs") or ())
        }
        events: list[dict[str, Any]] = []
        insufficient: list[str] = []
        canonical = [
            event
            for event in analysis.get("canonicalEvents") or ()
            if str(event.get("eventId")) in qualified
        ]
        # Run-lifecycle markers (RUN_STARTED/RUN_COMPLETED or mapping-declared
        # run-activity semantics) are provenance, not assessed behavior —
        # never drafted as expected events.
        lifecycle_refs = [
            str(event.get("eventId")) for event in canonical if is_run_lifecycle_event(event)
        ]
        draftable = [event for event in canonical if not is_run_lifecycle_event(event)]
        for index, event in enumerate(draftable, start=1):
            attrs = event.get("attributes") or {}
            event_type = (
                event.get("nativeEventType") or event.get("eventClass") or attrs.get("eventType")
            )
            actor = next(
                (a.split(":", 1)[-1] for a in event.get("actorRefs") or ()),
                attrs.get("agent_id") or attrs.get("agent"),
            )
            operation = event.get("operation")
            if isinstance(operation, Mapping):
                operation = operation.get("nativeOperation")
            operation = operation or attrs.get("operation")
            match = {
                key: str(value)
                for key, value in (
                    ("eventType", event_type),
                    ("actorId", actor),
                    ("operation", operation),
                )
                if value is not None and key not in self._RUN_SCOPED_MATCH_KINDS
            }
            note = None
            if not match:
                note = (
                    "Additional match criteria required — insufficient stable "
                    "semantic fields to match deterministically."
                )
                insufficient.append(f"E{index:02d}")
            events.append(
                {
                    "expectedEventId": f"E{index:02d}",
                    "ordinal": index,
                    "eventType": str(event_type) if event_type else None,
                    "actorId": str(actor) if actor else None,
                    "operation": str(operation) if operation else None,
                    "required": True,
                    "note": note,
                    "match": match,
                }
            )
        limitations = [
            "DRAFT_DERIVED_FROM_OBSERVED_CALIBRATION_EVIDENCE",
            "OBSERVED_ORDER_NOT_EXPECTED_COMPLETENESS",
            "RUN_SCOPED_IDENTIFIERS_NOT_EMBEDDED",
        ]
        if resolution.get("ambiguousEvidenceRefs") or resolution.get("unresolvedEvidenceRefs"):
            limitations.append("AMBIGUOUS_OR_UNRESOLVED_EVIDENCE_EXCLUDED_FROM_DRAFT")
        if lifecycle_refs:
            limitations.append("RUN_LIFECYCLE_MARKERS_NOT_DRAFTED")
        if insufficient:
            limitations.append(f"INSUFFICIENT_MATCH_FIELDS:{','.join(insufficient)}")
        time_states = {str(event.get("timeQuality") or "UNKNOWN") for event in canonical}
        if time_states - {"EXACT", "NORMALIZED"}:
            limitations.append("EVENT_ORDERING_TIME_QUALITY_LIMITED")
        draft = normalize_manifest(
            {
                "schemaVersion": "competition-expected-events/0.1",
                "manifestId": manifest_id,
                "label": label or f"Draft from run {run_id}",
                "events": events,
                "sourceBasis": "CALIBRATION_DRAFT",
                "limitations": limitations,
                "notes": (
                    "This draft was reconstructed from observed calibration "
                    "evidence. Observing an event in a calibration run does "
                    "not prove this is the complete expected set."
                ),
            }
        )
        draft["draftFromRun"] = {
            "runId": run_id,
            "runRole": record.get("runRole"),
            "qualifiedEventCount": len(canonical),
            "ambiguousExcluded": len(resolution.get("ambiguousEvidenceRefs") or ()),
            "unresolvedExcluded": len(resolution.get("unresolvedEvidenceRefs") or ()),
        }
        return draft

    def _required_analysis(self, case_id: str) -> dict[str, Any]:
        results = self.load_case_results(case_id)
        if results is None:
            raise IntegrationRequestError(
                f"case '{case_id}' has no saved analysis; run deterministic analysis first"
            )
        return dict(results["analysis"])

    def resolve_case_run(self, *, case_id: str, run_id: str) -> dict[str, Any]:
        """Resolve a declared run against the case's canonical events."""
        declaration = self.load_competition_run(case_id, run_id)
        if declaration is None:
            raise IntegrationRequestError(f"competition run not declared: {run_id}")
        analysis = self._required_analysis(case_id)
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
        resolution = resolve_competition_run(
            list(analysis.get("canonicalEvents") or ()),
            declaration,
            other_declarations=others,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-resolution", run_id),
            payload=resolution,
        )
        return resolution

    def _select_manifest(
        self, case_id: str, run_id: str, manifest_id: str | None
    ) -> dict[str, Any]:
        manifests = self.list_expected_manifests(case_id)
        if manifest_id is not None:
            manifest = self.load_expected_manifest(case_id, manifest_id)
            if manifest is None:
                raise IntegrationRequestError(f"expected-event manifest not found: {manifest_id}")
            # a legacy-bound manifest may only measure its declared run
            bound_run = manifest.get("runId")
            if bound_run and str(bound_run) != run_id:
                raise IntegrationRequestError(
                    f"manifest '{manifest['manifestId']}' is bound to run "
                    f"'{bound_run}' and cannot measure run '{run_id}'"
                )
            return manifest
        bound = [m for m in manifests if str(m.get("runId")) == run_id]
        candidates = bound or manifests
        if not candidates:
            raise IntegrationRequestError(
                "no expected-event manifest saved for this case; add one first"
            )
        if len(candidates) > 1:
            raise IntegrationRequestError(
                "multiple expected-event manifests present; specify manifestId "
                f"(available: {', '.join(str(m['manifestId']) for m in candidates)})"
            )
        return candidates[0]

    def run_control7_measurement(
        self, *, case_id: str, run_id: str | None = None, manifest_id: str | None = None
    ) -> dict[str, Any]:
        """Resolve the run, reconcile expected vs observed events, persist
        the Control 7 measurement and the Competition Evidence Bundle.

        A new measurement is never taken against a stale active snapshot —
        evidence or mapping changes require a fresh analysis first. Existing
        historical measurements are preserved untouched.
        """
        load_case(self.workspace_root, case_id)
        if run_id is None:
            active = self.active_run(case_id)
            run_id = str(active["runId"]) if active.get("runId") else ""
            if not run_id:
                raise IntegrationRequestError(
                    "no run selected — confirm a run on the Runs step or pass runId"
                )
        snapshot = self.analysis_snapshot_state(case_id)
        if snapshot["state"] in {"STALE_EVIDENCE_CHANGED", "STALE_MAPPING_CHANGED"}:
            raise IntegrationRequestError(
                "the active analysis snapshot is stale — evidence or mapping "
                "changed after this analysis; rerun deterministic analysis to "
                "create a new snapshot before measuring"
            )
        declaration = self.load_competition_run(case_id, run_id)
        if declaration is None:
            raise IntegrationRequestError(f"competition run not declared: {run_id}")
        analysis = self._required_analysis(case_id)
        report = self.load_case_results(case_id).get("report")  # type: ignore[union-attr]
        manifest = self._select_manifest(case_id, run_id, manifest_id)
        canonical_events = list(analysis.get("canonicalEvents") or ())
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
        resolution = resolve_competition_run(
            canonical_events, declaration, other_declarations=others
        )
        measurement = measure_event_recording(
            run_resolution=resolution,
            manifest=manifest,
            canonical_events=canonical_events,
        )

        # R5-04 shared-contract binding — every new measurement carries the
        # exact identities it consumed. Run role is workflow metadata only —
        # it is recorded, never interpreted as a verdict.
        artifact_digests = sorted(
            str(row["sha256"])
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("sha256")
        )
        approvals = self.load_case_mapping_approvals(case_id)
        mapping_refs = sorted(
            str(entry.mapping_profile["profileId"])
            for entry in approvals.values()
            if isinstance(entry.mapping_profile, Mapping) and entry.mapping_profile.get("profileId")
        )
        manifest_ref = str(manifest.get("manifestRef") or manifest["manifestId"])
        measurement["caseId"] = case_id
        measurement["measurementType"] = "AIA-LOG-001"
        measurement["analysisRunId"] = analysis.get("analysisRunId")
        measurement["activeSnapshotRef"] = snapshot.get("snapshotId")
        measurement["snapshotLabel"] = snapshot.get("snapshotLabel")
        measurement["evidenceSetRef"] = analysis.get("evidenceSetId")
        measurement["artifactDigests"] = artifact_digests
        measurement["mappingProfileRefs"] = mapping_refs
        measurement["runResolutionRef"] = f"competition-resolution:{run_id}"
        measurement["runRole"] = declaration.get("runRole")
        measurement["scenarioLabel"] = declaration.get("scenarioLabel")
        measurement["expectedManifestRef"] = manifest_ref
        measurement["expectedManifestVersion"] = manifest.get("manifestVersion")
        measurement["expectedManifestDigest"] = manifest.get("manifestDigest")
        measurement["references"] = dict(manifest.get("references") or {}) or None
        measurement["createdAt"] = _utc_now()
        # content identity over everything the measurement consumed/produced —
        # computed before the digest field itself is attached
        measurement["measurementDigest"] = "sha256:" + self._content_digest(
            {k: v for k, v in measurement.items() if k != "measurementDigest"}
        )
        # Carry any snapshot-current measurement blocks for other controls
        # (e.g. an earlier C16 reconciliation) so the shared envelope remains
        # the single per-run handoff surface.
        existing: dict[str, Mapping[str, Any]] = {}
        c16 = self.load_control16_measurement(case_id, run_id)
        if c16 is not None and c16.get("activeSnapshotRef") == snapshot.get("snapshotId"):
            existing[CONTROL16_CODE] = c16
        bundle = bundle_for_control7(
            case_id=case_id,
            run_declaration=declaration,
            run_resolution=resolution,
            expected_manifest=manifest,
            measurement=measurement,
            analysis=analysis,
            report=report,
            existing_measurements=existing,
            canonical_events=canonical_events,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-resolution", run_id),
            payload=resolution,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control7", run_id),
            payload=measurement,
        )
        # immutable copy keyed by measurement identity — the latest-pointer
        # output above may be superseded; the content-addressed copy never is
        measurement_key = str(measurement["measurementDigest"]).split(":")[-1][:24]
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control7", f"{run_id}-{measurement_key}"),
            payload=measurement,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-bundle", run_id),
            payload=bundle,
        )
        # immutable copy keyed by bundle identity — the latest-pointer output
        # above may be superseded; the content-addressed copy never is
        bundle_id = str(bundle.get("bundleId") or "")
        if bundle_id:
            save_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "competition-bundle", f"{run_id}-{bundle_id.split(':')[-1][:24]}"
                ),
                payload=bundle,
            )
        return {"run": resolution, "measurement": measurement, "bundle": bundle}

    @staticmethod
    def _content_digest(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    _MEASUREMENT_VERSION_RE = re.compile(r"^control7-(.+)-([0-9a-f]{24})$")

    def list_control7_measurements(self, case_id: str, run_id: str) -> list[dict[str, Any]]:
        """Every immutable Control 7 measurement persisted for a run."""
        load_case(self.workspace_root, case_id)
        records: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control7-"):
            matched = self._MEASUREMENT_VERSION_RE.match(name)
            if not matched or matched.group(1) != run_id:
                continue
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                records.append(payload)
        return records

    def load_control7_measurement(
        self, case_id: str, run_id: str | None = None, *, digest: str | None = None
    ) -> dict[str, Any] | None:
        """Latest Control 7 measurement for a run — or one exact historical
        measurement when ``digest`` (its ``measurementDigest`` hex) is given."""
        load_case(self.workspace_root, case_id)
        if run_id is not None and digest:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "control7", f"{run_id}-{digest.removeprefix('sha256:')[:24]}"
                ),
            )
        names = [
            name
            for name in list_case_output_names(self.workspace_root, case_id, prefix="control7-")
            if not self._MEASUREMENT_VERSION_RE.match(name)
        ]
        if run_id is not None:
            return load_case_output(
                self.workspace_root, case_id, name=self._output_name("control7", run_id)
            )
        if not names:
            return None
        return load_case_output(self.workspace_root, case_id, name=names[-1])

    def load_competition_bundle(
        self, case_id: str, run_id: str | None = None
    ) -> dict[str, Any] | None:
        load_case(self.workspace_root, case_id)
        names = list_case_output_names(self.workspace_root, case_id, prefix="competition-bundle-")
        if run_id is not None:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name("competition-bundle", run_id),
            )
        if not names:
            return None
        return load_case_output(self.workspace_root, case_id, name=names[-1])

    def run_control16_measurement(
        self,
        *,
        case_id: str,
        run_id: str | None = None,
        expected_agent_ids: Sequence[str] | None = None,
        token_accounting_profile: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve the run and reconcile provider-executed model-call usage
        under Control 16 / ACN-COST-001. Measurement only — ``verdict`` stays
        ``None``; HAIEC owns the frozen cap and the final Control Test.

        Same invariants as Control 7: never measured against a stale active
        snapshot, immutable content-addressed history, existing measurements
        preserved untouched.
        """
        load_case(self.workspace_root, case_id)
        if run_id is None:
            active = self.active_run(case_id)
            run_id = str(active["runId"]) if active.get("runId") else ""
            if not run_id:
                raise IntegrationRequestError(
                    "no run selected — confirm a run on the Runs step or pass runId"
                )
        snapshot = self.analysis_snapshot_state(case_id)
        if snapshot["state"] in {"STALE_EVIDENCE_CHANGED", "STALE_MAPPING_CHANGED"}:
            raise IntegrationRequestError(
                "the active analysis snapshot is stale — evidence or mapping "
                "changed after this analysis; rerun deterministic analysis to "
                "create a new snapshot before measuring"
            )
        declaration = self.load_competition_run(case_id, run_id)
        if declaration is None:
            raise IntegrationRequestError(f"competition run not declared: {run_id}")
        analysis = self._required_analysis(case_id)
        report = self.load_case_results(case_id).get("report")  # type: ignore[union-attr]
        canonical_events = list(analysis.get("canonicalEvents") or ())
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
        resolution = resolve_competition_run(
            canonical_events, declaration, other_declarations=others
        )
        # Approved mapping profiles by profileId — used to qualify token field
        # semantics (explicit approved fieldMappings), kept separate from the
        # generic event-mapping qualification.
        approvals = self.load_case_mapping_approvals(case_id)
        profiles_by_id: dict[str, Mapping[str, Any]] = {
            str(entry.mapping_profile["profileId"]): entry.mapping_profile
            for entry in load_default_mapping_registry().entries
        }
        profiles_by_id.update(
            {
                str(entry.mapping_profile["profileId"]): entry.mapping_profile
                for entry in approvals.values()
            }
        )
        measurement = reconcile_run_usage(
            run_resolution=resolution,
            canonical_events=canonical_events,
            expected_agent_ids=expected_agent_ids,
            approved_profiles=profiles_by_id,
            token_accounting_profile=token_accounting_profile,
        )

        # Shared-contract binding — identical identity fields as Control 7.
        artifact_digests = sorted(
            str(row["sha256"])
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("sha256")
        )
        mapping_refs = sorted(
            str(entry.mapping_profile["profileId"])
            for entry in approvals.values()
            if isinstance(entry.mapping_profile, Mapping) and entry.mapping_profile.get("profileId")
        )
        measurement["caseId"] = case_id
        measurement["measurementType"] = CONTROL16_CODE
        measurement["measurementSchemaVersion"] = measurement["schemaVersion"]
        measurement["analysisRunId"] = analysis.get("analysisRunId")
        measurement["activeSnapshotRef"] = snapshot.get("snapshotId")
        measurement["snapshotLabel"] = snapshot.get("snapshotLabel")
        measurement["evidenceSetRef"] = analysis.get("evidenceSetId")
        measurement["artifactDigests"] = artifact_digests
        measurement["mappingProfileRefs"] = mapping_refs
        measurement["runResolutionRef"] = f"competition-resolution:{run_id}"
        measurement["runRole"] = declaration.get("runRole")
        measurement["scenarioLabel"] = declaration.get("scenarioLabel")
        measurement["createdAt"] = _utc_now()
        measurement["measurementDigest"] = "sha256:" + self._content_digest(
            {k: v for k, v in measurement.items() if k != "measurementDigest"}
        )

        # Carry any existing C7 measurement alongside so the shared envelope
        # remains the single per-run handoff surface.
        existing: dict[str, Mapping[str, Any]] = {}
        expected_manifest = None
        c7 = self.load_control7_measurement(case_id, run_id)
        if c7 is not None and c7.get("activeSnapshotRef") == snapshot.get("snapshotId"):
            existing[CONTROL7_CODE] = c7
            manifest_ref = c7.get("expectedManifestRef")
            if manifest_ref:
                expected_manifest = self.load_expected_manifest(case_id, str(manifest_ref))
        bundle = bundle_for_control16(
            case_id=case_id,
            run_declaration=declaration,
            run_resolution=resolution,
            measurement=measurement,
            expected_manifest=expected_manifest,
            existing_measurements=existing,
            analysis=analysis,
            report=report,
            canonical_events=canonical_events,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-resolution", run_id),
            payload=resolution,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control16", run_id),
            payload=measurement,
        )
        # immutable copy keyed by measurement identity — the latest-pointer
        # output above may be superseded; the content-addressed copy never is
        measurement_key = str(measurement["measurementDigest"]).split(":")[-1][:24]
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control16", f"{run_id}-{measurement_key}"),
            payload=measurement,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-bundle", run_id),
            payload=bundle,
        )
        bundle_id = str(bundle.get("bundleId") or "")
        if bundle_id:
            save_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "competition-bundle", f"{run_id}-{bundle_id.split(':')[-1][:24]}"
                ),
                payload=bundle,
            )
        return {"run": resolution, "measurement": measurement, "bundle": bundle}

    _MEASUREMENT16_VERSION_RE = re.compile(r"^control16-(.+)-([0-9a-f]{24})$")

    def list_control16_measurements(self, case_id: str, run_id: str) -> list[dict[str, Any]]:
        """Every immutable Control 16 measurement persisted for a run."""
        load_case(self.workspace_root, case_id)
        records: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control16-"):
            matched = self._MEASUREMENT16_VERSION_RE.match(name)
            if not matched or matched.group(1) != run_id:
                continue
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                records.append(payload)
        return records

    def load_control16_measurement(
        self, case_id: str, run_id: str | None = None, *, digest: str | None = None
    ) -> dict[str, Any] | None:
        """Latest Control 16 measurement for a run — or one exact historical
        measurement when ``digest`` (its ``measurementDigest`` hex) is given."""
        load_case(self.workspace_root, case_id)
        if run_id is not None and digest:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "control16", f"{run_id}-{digest.removeprefix('sha256:')[:24]}"
                ),
            )
        names = [
            name
            for name in list_case_output_names(self.workspace_root, case_id, prefix="control16-")
            if not self._MEASUREMENT16_VERSION_RE.match(name)
        ]
        if run_id is not None:
            return load_case_output(
                self.workspace_root, case_id, name=self._output_name("control16", run_id)
            )
        if not names:
            return None
        return load_case_output(self.workspace_root, case_id, name=names[-1])

    # ---- Control 9 / AIA-ARC-006 drift & performance -------------------------

    _C9_PROFILE_LATEST_RE = re.compile(r"^control9-profile-(?!latest-)(.+)$")
    _C9_PROFILE_VERSION_RE = re.compile(r"^control9-profile-(.+)-v(\d+)$")
    _C9_BASELINE_LATEST_RE = re.compile(r"^control9-baseline-(?!latest-)(.+)$")
    _C9_BASELINE_VERSION_RE = re.compile(r"^control9-baseline-(.+)-v(\d+)$")
    _MEASUREMENT9_VERSION_RE = re.compile(r"^control9-(.+)-([0-9a-f]{24})$")

    def builtin_control9_profiles(self) -> list[dict[str, Any]]:
        """The built-in illustrative metric profiles (not yet case-bound)."""
        return [dict(p) for p in builtin_metric_profiles()]

    def save_control9_profile(self, *, case_id: str, profile: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one immutable metric profile version under the case.

        A profile version is never edited in place — the same
        ``(profileId, profileVersion)`` must digest to identical content or
        the save is rejected; a semantic change requires a new version.
        """
        load_case(self.workspace_root, case_id)
        normalized = normalize_metric_profile(profile)
        version_name = f"control9-profile-{normalized['profileId']}-v{normalized['profileVersion']}"
        existing = load_case_output(self.workspace_root, case_id, name=version_name)
        if existing is not None and existing.get("profileDigest") != normalized["profileDigest"]:
            raise IntegrationRequestError(
                f"metric profile {normalized['profileRef']} already exists with "
                "different content — profiles are immutable; create a new "
                "profileVersion instead"
            )
        save_case_output(self.workspace_root, case_id, name=version_name, payload=normalized)
        save_case_output(
            self.workspace_root,
            case_id,
            name=f"control9-profile-latest-{normalized['profileId']}",
            payload=normalized,
        )
        return normalized

    def list_control9_profiles(self, case_id: str) -> list[dict[str, Any]]:
        """Latest persisted version of each saved metric profile."""
        load_case(self.workspace_root, case_id)
        profiles: list[dict[str, Any]] = []
        for name in list_case_output_names(
            self.workspace_root, case_id, prefix="control9-profile-latest-"
        ):
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                profiles.append(payload)
        return sorted(profiles, key=lambda p: (str(p["profileId"]), int(p["profileVersion"])))

    def load_control9_profile(
        self, case_id: str, profile_id: str, *, version: int | None = None
    ) -> dict[str, Any] | None:
        """Load the latest version of a profile, or one exact version."""
        load_case(self.workspace_root, case_id)
        if version is None:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=f"control9-profile-latest-{profile_id}",
            )
        return load_case_output(
            self.workspace_root, case_id, name=f"control9-profile-{profile_id}-v{version}"
        )

    def save_control9_baseline(
        self, *, case_id: str, baseline: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist one immutable C9 baseline version under the case.

        Same immutability rule as profiles — an assessed baseline is never
        edited in place; measurement-defining changes create a new version.
        """
        load_case(self.workspace_root, case_id)
        normalized = normalize_control9_baseline({**baseline, "caseId": case_id})
        version_name = (
            f"control9-baseline-{normalized['baselineId']}-v{normalized['baselineVersion']}"
        )
        existing = load_case_output(self.workspace_root, case_id, name=version_name)
        if existing is not None and existing.get("baselineDigest") != normalized["baselineDigest"]:
            raise IntegrationRequestError(
                f"baseline {normalized['baselineRef']} already exists with "
                "different content — baselines are immutable; create a new "
                "baselineVersion instead"
            )
        save_case_output(self.workspace_root, case_id, name=version_name, payload=normalized)
        save_case_output(
            self.workspace_root,
            case_id,
            name=f"control9-baseline-latest-{normalized['baselineId']}",
            payload=normalized,
        )
        return normalized

    def list_control9_baselines(self, case_id: str) -> list[dict[str, Any]]:
        """Latest persisted version of each saved C9 baseline."""
        load_case(self.workspace_root, case_id)
        baselines: list[dict[str, Any]] = []
        for name in list_case_output_names(
            self.workspace_root, case_id, prefix="control9-baseline-latest-"
        ):
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                baselines.append(payload)
        return sorted(baselines, key=lambda b: (str(b["baselineId"]), int(b["baselineVersion"])))

    def load_control9_baseline(
        self, case_id: str, baseline_id: str, *, version: int | None = None
    ) -> dict[str, Any] | None:
        load_case(self.workspace_root, case_id)
        if version is None:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=f"control9-baseline-latest-{baseline_id}",
            )
        return load_case_output(
            self.workspace_root, case_id, name=f"control9-baseline-{baseline_id}-v{version}"
        )

    def _control9_live_context(
        self,
        case_id: str,
        analysis: Mapping[str, Any],
        run_resolution: Mapping[str, Any],
    ) -> tuple[list[str], str | None]:
        """The live side of the compatibility gate: the approved mapping
        identities and the semantic-profile basis observed on the run's
        qualified canonical events."""
        approvals = self.load_case_mapping_approvals(case_id)
        mapping_refs = sorted(
            str(entry.mapping_profile["profileId"])
            for entry in approvals.values()
            if isinstance(entry.mapping_profile, Mapping) and entry.mapping_profile.get("profileId")
        )
        qualified = {str(r) for r in run_resolution.get("qualifiedEventRefs") or ()}
        basis_values: set[str] = set()
        for event in analysis.get("canonicalEvents") or ():
            if str(event.get("eventId") or "") not in qualified:
                continue
            attributes = event.get("attributes") or {}
            sem = attributes.get("semanticProfileId")
            if sem:
                basis_values.add(str(sem))
        return mapping_refs, ";".join(sorted(basis_values)) or None

    def create_control9_baseline_from_run(
        self,
        *,
        case_id: str,
        source_run_id: str,
        profile_id: str,
        profile_version: int | None = None,
        baseline_id: str,
        basis: str = "KNOWN_GOOD_RUN",
        label: str | None = None,
    ) -> dict[str, Any]:
        """Derive an immutable MATCHED_WINDOWS baseline from a calibration or
        known-good run — qualified KPI observations of that run's current
        analysis snapshot only, never stale or unqualified evidence."""
        load_case(self.workspace_root, case_id)
        profile = self.load_control9_profile(case_id, profile_id, version=profile_version)
        if profile is None:
            raise IntegrationRequestError(f"metric profile not saved: {profile_id}")
        declaration = self.load_competition_run(case_id, source_run_id)
        if declaration is None:
            raise IntegrationRequestError(f"competition run not declared: {source_run_id}")
        snapshot = self.analysis_snapshot_state(case_id)
        if snapshot["state"] in {"STALE_EVIDENCE_CHANGED", "STALE_MAPPING_CHANGED"}:
            raise IntegrationRequestError(
                "the active analysis snapshot is stale — rerun deterministic "
                "analysis before deriving a baseline"
            )
        analysis = self._required_analysis(case_id)
        canonical_events = list(analysis.get("canonicalEvents") or ())
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != source_run_id]
        resolution = resolve_competition_run(
            canonical_events, declaration, other_declarations=others
        )
        projection = project_kpi_observations(
            metric_profile=profile,
            run_resolution=resolution,
            canonical_events=canonical_events,
        )
        aggregated = aggregate_live_windows(
            metric_profile=profile,
            observations=projection["observations"],
        )
        windows = []
        for key in sorted(aggregated["values"]):
            members = aggregated["liveByKey"].get(key, [])
            windows.append(
                {
                    "windowKey": key,
                    "value": aggregated["values"][key],
                    "windowStart": members[0]["windowStart"] if members else None,
                    "windowEnd": members[0]["windowEnd"] if members else None,
                    "evidenceRefs": sorted({str(o["sourceEventRef"]) for o in members}),
                }
            )
        if not windows:
            raise IntegrationRequestError(
                "no qualified KPI windows on the source run — a baseline needs "
                "at least one qualified observation"
            )
        artifact_digests = sorted(
            str(row["sha256"])
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("sha256")
        )
        mapping_refs, source_basis = self._control9_live_context(case_id, analysis, resolution)
        baseline = {
            "baselineId": baseline_id,
            "baselineVersion": 1,
            "label": label or f"{baseline_id} (from {source_run_id})",
            "basis": basis,
            "baselineMode": "MATCHED_WINDOWS",
            "metricId": profile["metricId"],
            "unit": profile["unit"],
            "direction": profile["direction"],
            "aggregation": profile["aggregation"],
            "governedScope": profile.get("governedScope"),
            "windowDefinition": profile.get("windowDefinition"),
            "metricProfileRef": profile["profileRef"],
            "metricProfileDigest": profile["profileDigest"],
            "windows": windows,
            "valueBasis": "DERIVED_FROM_RUN",
            "sourceRunId": source_run_id,
            "sourceAnalysisRunId": analysis.get("analysisRunId"),
            "sourceSnapshotRef": snapshot.get("snapshotId"),
            "sourceEvidenceSetId": analysis.get("evidenceSetId"),
            "evidenceRefs": sorted({str(r) for w in windows for r in w["evidenceRefs"]}),
            "mappingProfileDigests": mapping_refs,
            "artifactDigests": artifact_digests,
            "sourceBasis": source_basis,
            "createdAt": _utc_now(),
            "limitations": [
                "LOGSENSE_DESCRIPTIVE_BASELINE_NE_HAIEC_GOVERNING_BASELINE",
            ],
        }
        return self.save_control9_baseline(case_id=case_id, baseline=baseline)

    def run_control9_measurement(
        self,
        *,
        case_id: str,
        run_id: str | None = None,
        profile_id: str | None = None,
        profile_version: int | None = None,
        baseline_id: str | None = None,
        baseline_version: int | None = None,
    ) -> dict[str, Any]:
        """Measure KPI drift for the active run under Control 9 / AIA-ARC-006.

        Measurement only — ``verdict`` stays ``None``; HAIEC owns the
        governing baseline, drift threshold, and final Control Test. Same
        invariants as Controls 7/16: never measured against a stale active
        snapshot, immutable content-addressed history.
        """
        load_case(self.workspace_root, case_id)
        if run_id is None:
            active = self.active_run(case_id)
            run_id = str(active["runId"]) if active.get("runId") else ""
            if not run_id:
                raise IntegrationRequestError(
                    "no run selected — confirm a run on the Runs step or pass runId"
                )
        if profile_id is None:
            raise IntegrationRequestError(
                "no metric profile selected — define or clone a Control 9 metric profile first"
            )
        if baseline_id is None:
            raise IntegrationRequestError(
                "no baseline selected — drift is change relative to a declared "
                "evidence basis; select or create one first"
            )
        snapshot = self.analysis_snapshot_state(case_id)
        if snapshot["state"] in {"STALE_EVIDENCE_CHANGED", "STALE_MAPPING_CHANGED"}:
            raise IntegrationRequestError(
                "the active analysis snapshot is stale — evidence or mapping "
                "changed after this analysis; rerun deterministic analysis to "
                "create a new snapshot before measuring"
            )
        profile = self.load_control9_profile(case_id, profile_id, version=profile_version)
        if profile is None:
            raise IntegrationRequestError(f"metric profile not saved: {profile_id}")
        baseline = self.load_control9_baseline(case_id, baseline_id, version=baseline_version)
        if baseline is None:
            raise IntegrationRequestError(f"baseline not saved: {baseline_id}")
        declaration = self.load_competition_run(case_id, run_id)
        if declaration is None:
            raise IntegrationRequestError(f"competition run not declared: {run_id}")
        analysis = self._required_analysis(case_id)
        report = self.load_case_results(case_id).get("report")  # type: ignore[union-attr]
        canonical_events = list(analysis.get("canonicalEvents") or ())
        others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
        resolution = resolve_competition_run(
            canonical_events, declaration, other_declarations=others
        )
        live_mapping_refs, live_source_basis = self._control9_live_context(
            case_id, analysis, resolution
        )
        measurement = measure_drift(
            run_resolution=resolution,
            canonical_events=canonical_events,
            metric_profile=profile,
            baseline=baseline,
            live_mapping_profile_refs=live_mapping_refs,
            live_source_basis=live_source_basis,
        )

        # Shared-contract binding — identical identity fields as Controls 7/16.
        artifact_digests = sorted(
            str(row["sha256"])
            for row in analysis.get("artifactResults") or ()
            if isinstance(row, dict) and row.get("sha256")
        )
        measurement["caseId"] = case_id
        measurement["measurementSchemaVersion"] = measurement["schemaVersion"]
        measurement["analysisRunId"] = analysis.get("analysisRunId")
        measurement["activeSnapshotRef"] = snapshot.get("snapshotId")
        measurement["snapshotLabel"] = snapshot.get("snapshotLabel")
        measurement["evidenceSetRef"] = analysis.get("evidenceSetId")
        measurement["artifactDigests"] = artifact_digests
        measurement["mappingProfileRefs"] = live_mapping_refs
        measurement["runResolutionRef"] = f"competition-resolution:{run_id}"
        measurement["runRole"] = declaration.get("runRole")
        measurement["scenarioLabel"] = declaration.get("scenarioLabel")
        measurement["baselineDefinitionRef"] = baseline.get("baselineRef")
        measurement["createdAt"] = _utc_now()
        measurement["measurementDigest"] = "sha256:" + self._content_digest(
            {k: v for k, v in measurement.items() if k != "measurementDigest"}
        )

        # Carry snapshot-current C7/C16 blocks so the shared envelope remains
        # the single per-run handoff surface.
        existing: dict[str, Mapping[str, Any]] = {}
        expected_manifest = None
        c7 = self.load_control7_measurement(case_id, run_id)
        if c7 is not None and c7.get("activeSnapshotRef") == snapshot.get("snapshotId"):
            existing[CONTROL7_CODE] = c7
            manifest_ref = c7.get("expectedManifestRef")
            if manifest_ref:
                expected_manifest = self.load_expected_manifest(case_id, str(manifest_ref))
        c16 = self.load_control16_measurement(case_id, run_id)
        if c16 is not None and c16.get("activeSnapshotRef") == snapshot.get("snapshotId"):
            existing[CONTROL16_CODE] = c16
        bundle = bundle_for_control9(
            case_id=case_id,
            run_declaration=declaration,
            run_resolution=resolution,
            measurement=measurement,
            expected_manifest=expected_manifest,
            existing_measurements=existing,
            analysis=analysis,
            report=report,
            canonical_events=canonical_events,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-resolution", run_id),
            payload=resolution,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control9", run_id),
            payload=measurement,
        )
        measurement_key = str(measurement["measurementDigest"]).split(":")[-1][:24]
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("control9", f"{run_id}-{measurement_key}"),
            payload=measurement,
        )
        save_case_output(
            self.workspace_root,
            case_id,
            name=self._output_name("competition-bundle", run_id),
            payload=bundle,
        )
        bundle_id = str(bundle.get("bundleId") or "")
        if bundle_id:
            save_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "competition-bundle", f"{run_id}-{bundle_id.split(':')[-1][:24]}"
                ),
                payload=bundle,
            )
        return {"run": resolution, "measurement": measurement, "bundle": bundle}

    def control9_compatibility_preview(
        self,
        *,
        case_id: str,
        profile_id: str,
        baseline_id: str,
        run_id: str | None = None,
        profile_version: int | None = None,
        baseline_version: int | None = None,
    ) -> dict[str, Any]:
        """Compatibility preflight without producing a measurement — the
        baseline-vs-live semantic gate the operator reviews before measuring."""
        load_case(self.workspace_root, case_id)
        profile = self.load_control9_profile(case_id, profile_id, version=profile_version)
        if profile is None:
            raise IntegrationRequestError(f"metric profile not saved: {profile_id}")
        baseline = self.load_control9_baseline(case_id, baseline_id, version=baseline_version)
        if baseline is None:
            raise IntegrationRequestError(f"baseline not saved: {baseline_id}")
        if run_id is None:
            active = self.active_run(case_id)
            run_id = str(active.get("runId") or "") or None
        mapping_refs: list[str] = []
        source_basis: str | None = None
        if run_id:
            declaration = self.load_competition_run(case_id, run_id)
            analysis = (self.load_case_results(case_id) or {}).get("analysis")
            if declaration is not None and analysis is not None:
                others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
                resolution = resolve_competition_run(
                    list(analysis.get("canonicalEvents") or ()),
                    declaration,
                    other_declarations=others,
                )
                mapping_refs, source_basis = self._control9_live_context(
                    case_id, analysis, resolution
                )
        gate = compatibility_gate(
            metric_profile=profile,
            baseline=baseline,
            live_mapping_profile_refs=mapping_refs,
            live_source_basis=source_basis,
        )
        return {
            "runId": run_id,
            "metricProfileRef": profile["profileRef"],
            "metricProfileDigest": profile["profileDigest"],
            "baselineRef": baseline["baselineRef"],
            "baselineDigest": baseline["baselineDigest"],
            "compatibility": gate,
        }

    def list_control9_measurements(self, case_id: str, run_id: str) -> list[dict[str, Any]]:
        """Every immutable Control 9 measurement persisted for a run."""
        load_case(self.workspace_root, case_id)
        records: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control9-"):
            if name.startswith(("control9-profile-", "control9-baseline-")):
                continue
            matched = self._MEASUREMENT9_VERSION_RE.match(name)
            if not matched or matched.group(1) != run_id:
                continue
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                records.append(payload)
        return records

    def load_control9_measurement(
        self, case_id: str, run_id: str | None = None, *, digest: str | None = None
    ) -> dict[str, Any] | None:
        """Latest Control 9 measurement for a run — or one exact historical
        measurement when ``digest`` (its ``measurementDigest`` hex) is given."""
        load_case(self.workspace_root, case_id)
        if run_id is not None and digest:
            return load_case_output(
                self.workspace_root,
                case_id,
                name=self._output_name(
                    "control9", f"{run_id}-{digest.removeprefix('sha256:')[:24]}"
                ),
            )
        names = [
            name
            for name in list_case_output_names(self.workspace_root, case_id, prefix="control9-")
            if not name.startswith(("control9-profile-", "control9-baseline-"))
            and not self._MEASUREMENT9_VERSION_RE.match(name)
        ]
        if run_id is not None:
            return load_case_output(
                self.workspace_root, case_id, name=self._output_name("control9", run_id)
            )
        if not names:
            return None
        return load_case_output(self.workspace_root, case_id, name=names[-1])

    def haiec_handoff_status(self, case_id: str, run_id: str | None = None) -> dict[str, Any]:
        """Deterministic HAIEC handoff readiness checklist.

        Separates MEASUREMENT READY (LogSense-side completeness) from HAIEC
        HANDOFF COMPLETE (governing control/threshold refs attached). Missing
        governance refs never invalidate a measurement — they only bound
        handoff readiness.
        """
        load_case(self.workspace_root, case_id)
        snapshot = self.analysis_snapshot_state(case_id)
        active = self.active_run(case_id)
        run_id = run_id or str(active.get("runId") or "")
        measurement = self.load_control7_measurement(case_id, run_id or None)
        resolution = self.load_competition_resolution(case_id, run_id) if run_id else None
        bundle = self.load_competition_bundle(case_id, run_id or None)
        analysis = (self.load_case_results(case_id) or {}).get("analysis") or {}
        refs = (measurement or {}).get("references") or {}

        reasons: list[str] = []

        # The stored measurement must be bound to the CURRENT active snapshot —
        # a measurement produced before the latest analysis rerun is historical
        # proof only, never silently re-presented as current.
        measurement_current = False
        if measurement is not None:
            measurement_current = bool(
                measurement.get("activeSnapshotRef")
                and measurement.get("activeSnapshotRef") == snapshot.get("snapshotId")
                and (
                    not measurement.get("analysisRunId")
                    or not analysis.get("analysisRunId")
                    or measurement.get("analysisRunId") == analysis.get("analysisRunId")
                )
            )
            if not measurement_current:
                reasons.append("MEASUREMENT_BOUND_TO_PRIOR_ANALYSIS_SNAPSHOT")

        # The exact immutable manifest version the measurement consumed must
        # still exist with the recorded digest — "some manifest exists" is not
        # sufficient proof.
        manifest_exact = False
        if measurement is not None:
            manifest_ref = measurement.get("expectedManifestRef")
            manifest_digest = measurement.get("expectedManifestDigest")
            if manifest_ref and manifest_digest:
                stored = self.load_expected_manifest(case_id, str(manifest_ref))
                manifest_exact = bool(stored and stored.get("manifestDigest") == manifest_digest)
            if not manifest_exact:
                reasons.append("EXACT_MANIFEST_VERSION_UNAVAILABLE")

        # The selected bundle must correspond to this exact measurement —
        # the embedded Control 7 block plus its identity fields, never
        # timestamp coincidence. Top-level envelope fields describe whichever
        # control was exported last, so the binding check uses the nested
        # block (which carries the same identity fields and is already
        # digest-bound to the stored measurement).
        bundle_matches = False
        if measurement is not None and bundle is not None:
            bound_block = (bundle.get("measurements") or {}).get(CONTROL7_CODE)
            identity_fields = (
                "activeSnapshotRef",
                "analysisRunId",
                "expectedManifestRef",
                "expectedManifestDigest",
                "measurementState",
            )
            bundle_matches = (
                bound_block is not None
                and self._content_digest(bound_block) == self._content_digest(measurement)
                # the envelope's run binding is control-agnostic and must
                # always match; measurement-specific identity lives on the
                # nested block regardless of which control is primary.
                and bundle.get("runId") == measurement.get("runId")
                and all(
                    bound_block.get(field) == measurement.get(field) for field in identity_fields
                )
            )
            if not bundle_matches:
                reasons.append("BUNDLE_MEASUREMENT_BINDING_MISMATCH")

        checks = [
            {
                "item": "Active current analysis snapshot",
                "met": snapshot["state"] == "CURRENT",
            },
            {
                "item": "Confirmed run",
                "met": bool(run_id) and active.get("runId") == run_id,
            },
            {
                "item": "Run resolution available",
                "met": resolution is not None,
            },
            {
                "item": "C7 measurement computed",
                "met": measurement is not None,
            },
            {
                "item": "Measurement bound to current analysis snapshot",
                "met": measurement_current,
            },
            {
                "item": "Exact reviewed manifest version available",
                "met": manifest_exact,
            },
            {
                "item": "Competition bundle generated",
                "met": bundle is not None,
            },
            {
                "item": "Bundle corresponds to this exact measurement",
                "met": bundle_matches,
            },
            {
                "item": "HAIEC controlVersionRef attached",
                "met": bool(refs.get("controlVersionRef") or refs.get("controlRef")),
                "optional": True,
            },
            {
                "item": "HAIEC thresholdVersionRef attached",
                "met": bool(refs.get("thresholdVersionRef")),
                "optional": True,
            },
        ]
        measurement_ready = all(c["met"] for c in checks if not c.get("optional"))
        refs_attached = all(c["met"] for c in checks if c.get("optional"))
        if measurement is not None and not measurement_current:
            next_action = (
                "The stored Control 7 measurement was created from an earlier "
                "analysis snapshot. Run Control 7 again against the current "
                "snapshot before HAIEC handoff."
            )
        elif measurement is not None and bundle is not None and not bundle_matches:
            next_action = (
                "The stored Competition Evidence Bundle does not correspond to "
                "this exact measurement. Run Control 7 again to regenerate a "
                "bound bundle before HAIEC handoff."
            )
        elif measurement_ready and refs_attached:
            next_action = "Open HAIEC Control Test for AIA-LOG-001 using this exact run and bundle."
        elif measurement_ready:
            next_action = (
                "Measurement available; governing HAIEC control/threshold "
                "reference has not been attached. Before presenting an "
                "assessed result, select/freeze the governing Control 7 "
                "rule in HAIEC and bind it to this run/bundle."
            )
        else:
            next_action = "Complete the checklist items marked unmet first."
        return {
            "schemaVersion": "haiec-handoff-status/0.1",
            "caseId": case_id,
            "runId": run_id or None,
            "measurementReady": measurement_ready,
            "measurementCurrent": measurement_current,
            "bundleMatchesMeasurement": bundle_matches,
            "handoffComplete": measurement_ready and refs_attached,
            "checks": checks,
            "reasons": reasons,
            "governanceRefs": dict(refs) if refs else None,
            "bundleId": (bundle or {}).get("bundleId"),
            "measurementDigest": (measurement or {}).get("measurementDigest"),
            "nextAction": next_action,
        }

    def competition_tool_payload(self, case_id: str) -> dict[str, Any]:
        """Deterministic competition surface for the read-only investigator."""
        load_case(self.workspace_root, case_id)
        runs: list[dict[str, Any]] = []
        for name in list_case_output_names(
            self.workspace_root, case_id, prefix="competition-resolution-"
        ):
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                runs.append(payload)
        measurements: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control7-"):
            if self._MEASUREMENT_VERSION_RE.match(name):
                continue  # content-addressed copies — the latest pointer suffices
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                measurements.append(payload)
        control9_measurements: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control9-"):
            if name.startswith(("control9-profile-", "control9-baseline-")):
                continue
            if self._MEASUREMENT9_VERSION_RE.match(name):
                continue  # content-addressed copies — the latest pointer suffices
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                control9_measurements.append(payload)
        control16_measurements: list[dict[str, Any]] = []
        for name in list_case_output_names(self.workspace_root, case_id, prefix="control16-"):
            if self._MEASUREMENT16_VERSION_RE.match(name):
                continue  # content-addressed copies — the latest pointer suffices
            payload = load_case_output(self.workspace_root, case_id, name=name)
            if payload:
                control16_measurements.append(payload)
        bundle = self.load_competition_bundle(case_id)
        surface: dict[str, Any] = {
            "competitionRuns": runs,
            "control7Measurements": measurements,
            "control9Measurements": control9_measurements,
            "control16Measurements": control16_measurements,
            "competitionBundle": bundle,
        }
        try:
            surface["eventReadiness"] = self.event_readiness_state(case_id)
        except Exception:  # noqa: BLE001 — readiness is advisory, never blocks
            surface["eventReadiness"] = None
        surface["capabilityTruth"] = capability_truth()
        surface["eventGuidance"] = _ai_guidance_context()
        surface["importedHaiecProofs"] = self.imported_haiec_proofs(case_id)
        return surface

    def import_haiec_proof(self, case_id: str, *, file_name: str, content: bytes) -> dict[str, Any]:
        """Manually import one authoritative HAIEC proof snapshot (JSON).

        Stored as an AUTHORITATIVE EXTERNAL ASSURANCE PROOF SNAPSHOT under
        the case's derived-output store — digest-keyed, idempotent on exact
        re-import, and structurally unable to enter canonical runtime
        intake, measurement, or deduplication."""
        from logsense.competition import haiec_proof

        return haiec_proof.import_haiec_proof(
            self.workspace_root, case_id, file_name=file_name, content=content
        )

    def imported_haiec_proofs(self, case_id: str) -> list[dict[str, Any]]:
        """Digest-verified imported HAIEC proof snapshots for this case."""
        from logsense.competition import haiec_proof

        return haiec_proof.list_imported_proofs(self.workspace_root, case_id)

    def import_competition_fixture(self, *, case_id: str, fixture_name: str) -> dict[str, Any]:
        """Load a bundled deterministic Control 7 fixture into the case.

        Commits the fixture evidence through canonical intake, records the
        declared run + expected manifest, binds the schema-compatible mapping
        proposal through the standard USER-approval path (provenance:
        ``BUILTIN_COMPETITION_FIXTURE``), analyzes, and runs the measurement.
        """
        load_case(self.workspace_root, case_id)
        fixture = load_fixture(fixture_name)
        files = [
            {"name": name, "contentBase64": base64.b64encode(content).decode("ascii")}
            for name, content in fixture["evidence"].items()
        ]
        self.import_evidence({"caseId": case_id, "files": files})
        self.declare_competition_run(case_id=case_id, declaration=fixture["runDeclaration"])
        if fixture["expectedManifest"] is not None:
            self.save_expected_event_manifest(case_id=case_id, manifest=fixture["expectedManifest"])

        fixture_digests = {
            hashlib.sha256(content).hexdigest() for content in fixture["evidence"].values()
        }
        preview = self.analyze_case(case_id=case_id, save=False)["analysis"]
        proposals = preview.get("mappingProposals") or ()
        chosen: dict[str, Mapping[str, Any]] = {}
        for row in sorted(proposals, key=lambda item: str(item.get("proposalId"))):
            artifact = str(row.get("artifactId"))
            if str(row.get("sha256")) not in fixture_digests or artifact in chosen:
                continue
            chosen[artifact] = row
        for artifact_id, row in chosen.items():
            self.approve_case_mapping(
                case_id=case_id,
                artifact_id=artifact_id,
                proposal_id=str(row["proposalId"]),
                approval_source="BUILTIN_COMPETITION_FIXTURE",
                _preview_analysis=preview,
            )
        self.analyze_case(case_id=case_id)
        run_id = str(fixture["runDeclaration"]["runId"])
        control = str(fixture["meta"].get("control") or "AIA-LOG-001")
        if control == CONTROL16_CODE:
            return self.run_control16_measurement(
                case_id=case_id,
                run_id=run_id,
                expected_agent_ids=fixture["meta"].get("expectedAgentIds"),
                token_accounting_profile=fixture["meta"].get("tokenAccountingProfile"),
            )
        if control == CONTROL9_CODE:
            # The fixture's metric profile + baseline templates are completed
            # with the runtime-approved mapping identity, snapshot binding and
            # artifact digests — the same fields an operator's selections
            # produce through the real UI path.
            profile_payload = dict(fixture["meta"]["metricProfile"])
            results = self.load_case_results(case_id) or {}
            analysis = results.get("analysis") or {}
            snapshot = self.analysis_snapshot_state(case_id)
            canonical_events = list(analysis.get("canonicalEvents") or ())
            declaration = self.load_competition_run(case_id, run_id) or {}
            others = [r for r in self.list_competition_runs(case_id) if r["runId"] != run_id]
            resolution_preview = resolve_competition_run(
                canonical_events, declaration, other_declarations=others
            )
            live_refs, live_basis = self._control9_live_context(
                case_id, analysis, resolution_preview
            )
            if not profile_payload.get("mappingProfileRefs"):
                profile_payload["mappingProfileRefs"] = live_refs
            profile = self.save_control9_profile(case_id=case_id, profile=profile_payload)
            artifact_digests = sorted(
                str(row["sha256"])
                for row in analysis.get("artifactResults") or ()
                if isinstance(row, dict) and row.get("sha256")
            )
            baseline_payload = dict(fixture["meta"]["baseline"])
            baseline_payload.setdefault("caseId", case_id)
            baseline_payload.setdefault("label", f"{baseline_payload['baselineId']} (fixture)")
            baseline_payload["metricProfileRef"] = profile["profileRef"]
            baseline_payload["metricProfileDigest"] = profile["profileDigest"]
            baseline_payload.setdefault("windowDefinition", dict(profile["windowDefinition"]))
            baseline_payload.setdefault("governedScope", profile.get("governedScope"))
            baseline_payload.setdefault("mappingProfileDigests", live_refs)
            baseline_payload.setdefault("artifactDigests", artifact_digests)
            baseline_payload.setdefault("sourceBasis", live_basis)
            baseline_payload.setdefault("sourceEvidenceSetId", analysis.get("evidenceSetId"))
            baseline_payload.setdefault("sourceSnapshotRef", snapshot.get("snapshotId"))
            baseline_payload.setdefault("createdAt", _utc_now())
            baseline = self.save_control9_baseline(case_id=case_id, baseline=baseline_payload)
            return self.run_control9_measurement(
                case_id=case_id,
                run_id=run_id,
                profile_id=str(profile["profileId"]),
                profile_version=int(profile["profileVersion"]),
                baseline_id=str(baseline["baselineId"]),
                baseline_version=int(baseline["baselineVersion"]),
            )
        return self.run_control7_measurement(
            case_id=case_id,
            run_id=run_id,
            manifest_id=str(fixture["expectedManifest"]["manifestId"]),
        )

    # ---- source readiness / mapping UX ---------------------------------------

    # Deterministic control-relevance evidence groups. A control is flagged
    # only when the required *combination* of roles is present — a lone generic
    # field like ``value``, ``model`` or ``retry`` never suffices.
    _RELEVANCE_ROLE_HINTS: Mapping[str, frozenset[str]] = {
        "RUN_CORRELATION_IDENTITY": frozenset(
            {
                "runid",
                "scenariorunid",
                "traceid",
                "requestid",
                "sessionid",
                "actioncorrelationid",
                "correlationid",
                "taskid",
                "contextid",
                "spanid",
                "parentspanid",
                "conversationid",
            }
        ),
        "EVENT_ACTION_IDENTITY": frozenset(
            {"eventtype", "eventname", "eventid", "operation", "action", "spanname"}
        ),
        "TIMESTAMP": frozenset(
            {
                "ts",
                "timestamp",
                "time",
                "eventtime",
                "occurredat",
                "observedat",
                "starttime",
                "endtime",
                "durationms",
            }
        ),
        "ACTOR_AGENT_IDENTITY": frozenset(
            {
                "agentid",
                "service",
                "servicename",
                "hostname",
                "actor",
                "principal",
                "nodeid",
                "instanceid",
            }
        ),
        "METRIC_IDENTITY": frozenset(
            {"kpi", "metric", "metricname", "measurementname", "countername", "gaugename"}
        ),
        "MEASUREMENT_VALUE": frozenset(
            {"value", "metricvalue", "kpivalue", "measurementvalue", "reading", "sample"}
        ),
        "MEASUREMENT_SCOPE_TIME": frozenset(
            {
                "window",
                "windowstart",
                "windowend",
                "scope",
                "entityid",
                "cellid",
                "sliceid",
                "baseline",
                "target",
                "threshold",
                "drift",
            }
        ),
        "MODEL_CALL_IDENTITY": frozenset(
            {"model", "modelname", "modelcallid", "completionid", "llmcallid", "inferenceid"}
        ),
        "TOKEN_USAGE": frozenset(
            {
                "inputtokens",
                "outputtokens",
                "prompttokens",
                "completiontokens",
                "cachedtokens",
                "totaltokens",
                "tokencount",
                "usage",
            }
        ),
        "RETRY_ATTEMPT": frozenset({"retry", "retrycount", "attempt", "attemptnumber", "retries"}),
    }

    _CONTROL7_ROLES = (
        "RUN_CORRELATION_IDENTITY",
        "EVENT_ACTION_IDENTITY",
        "TIMESTAMP",
        "ACTOR_AGENT_IDENTITY",
    )

    @classmethod
    def control_relevance(cls, field_names: Sequence[str]) -> list[dict[str, Any]]:
        """Deterministic control evidence hints from observed field names.

        Returns ``EVIDENCE_HINT`` rows — a hint says the source *may* be useful
        for a control's measurement; it never proves measurement completeness.
        """
        normalized = {
            str(name).lower().replace("_", "").replace(".", "").replace("-", "")
            for name in field_names
        }
        role_fields: dict[str, list[str]] = {}
        for role, hints in cls._RELEVANCE_ROLE_HINTS.items():
            matched = sorted(normalized & hints)
            if matched:
                role_fields[role] = matched
        matched_roles = frozenset(role_fields)

        def _row(code: str, label: str, roles: list[str]) -> dict[str, Any]:
            return {
                "controlCode": code,
                "controlLabel": label,
                "state": "EVIDENCE_HINT",
                "matchedRoles": roles,
                "matchedFields": sorted(f for r in roles for f in role_fields[r]),
            }

        out: list[dict[str, Any]] = []

        # Control 7: at least two distinct meaningful categories.
        if sum(role in matched_roles for role in cls._CONTROL7_ROLES) >= 2:
            out.append(
                _row(
                    "AIA-LOG-001",
                    "Control 7 — Event Recording",
                    [r for r in cls._CONTROL7_ROLES if r in matched_roles],
                )
            )

        # Control 9: metric/KPI identity + measurement value + scope or time.
        if (
            "METRIC_IDENTITY" in matched_roles
            and "MEASUREMENT_VALUE" in matched_roles
            and matched_roles & {"MEASUREMENT_SCOPE_TIME", "TIMESTAMP"}
        ):
            roles = ["MEASUREMENT_VALUE", "METRIC_IDENTITY"]
            roles += [r for r in ("MEASUREMENT_SCOPE_TIME", "TIMESTAMP") if r in matched_roles]
            out.append(_row("AIA-ARC-006", "Control 9 — Drift", roles))

        # Control 16: model-call identity + token/usage evidence; run/actor/
        # retry presence strengthens the hint.
        if "MODEL_CALL_IDENTITY" in matched_roles and "TOKEN_USAGE" in matched_roles:
            roles = ["MODEL_CALL_IDENTITY", "TOKEN_USAGE"]
            roles += [
                r
                for r in ("RUN_CORRELATION_IDENTITY", "RETRY_ATTEMPT", "ACTOR_AGENT_IDENTITY")
                if r in matched_roles
            ]
            out.append(_row("ACN-COST-001", "Control 16 — Spend Cap", roles))

        return out

    def preview_case_analysis(self, case_id: str) -> dict[str, Any]:
        """One non-persisted canonical analysis for operator-facing previews.

        Callers needing several source/mapping views in one render should run
        this once and pass the result down via ``_analysis`` so an identical
        full preview is not re-executed per widget. Preview results reflect
        committed evidence plus recorded approvals — preview canonical counts
        are not part of the saved active analysis.
        """
        load_case(self.workspace_root, case_id)
        return cast("dict[str, Any]", self.analyze_case(case_id=case_id, save=False)["analysis"])

    def case_mapping_proposals(
        self, case_id: str, *, _analysis: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        analysis = _analysis or self.preview_case_analysis(case_id)
        return {
            "artifactResults": deepcopy(list(analysis.get("artifactResults") or ())),
            "mappingProposals": deepcopy(list(analysis.get("mappingProposals") or ())),
            "unresolvedArtifacts": deepcopy(list(analysis.get("unresolvedArtifacts") or ())),
            "approvedArtifactIds": sorted(self.load_case_mapping_approvals(case_id)),
        }

    @staticmethod
    def _evidence_qualification(
        artifact_id: str, source_qualifications: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Per-source evidence qualification from claim-scoped rows.

        Qualifications key on ``source:{artifact_id}:...`` refs. A source that
        produced no claim qualifications is honestly ``NOT_ASSESSED`` — never
        inferred from mapping success.
        """
        prefix = f"source:{artifact_id}:"
        decisions = [
            str(q["decision"])
            for q in source_qualifications
            if str(q.get("sourceRef") or "").startswith(prefix)
        ]
        if not decisions:
            state = "NOT_ASSESSED"
        elif "CAN_ESTABLISH" in decisions:
            state = "CAN_ESTABLISH"
        elif "CAN_SUPPORT" in decisions:
            state = "CAN_SUPPORT"
        elif "CANNOT_ESTABLISH" in decisions:
            state = "CANNOT_ESTABLISH"
        else:
            state = "UNKNOWN"
        return {
            "state": state,
            "claimDecisions": {d: decisions.count(d) for d in sorted(set(decisions))},
        }

    @staticmethod
    def source_next_action(mapping_state: str, *, analysis_stale: bool = False) -> str:
        """Plain-language deterministic next action for one source."""
        if analysis_stale and mapping_state in ("APPROVED_USER", "PREMAPPED"):
            return "Mapping approved — rerun deterministic analysis."
        return {
            "PREMAPPED": "No action needed — source is mapped.",
            "APPROVED_USER": "No action needed — mapping approved and bound.",
            "PROPOSAL_AVAILABLE": "Review and approve the available mapping proposal.",
            "APPROVAL_REJECTED_NEEDS_REVIEW": (
                "Prior approval no longer matches this artifact — review again."
            ),
            "NO_MAPPING_AVAILABLE": (
                "No deterministic mapping exists — continue with current coverage "
                "or add an adapter/template later."
            ),
            "OPAQUE_PRESERVED": (
                "Artifact preserved only — inspect manually if it is important "
                "to the investigation."
            ),
        }.get(mapping_state, "Review this source.")

    _READINESS_LABELS: Mapping[str, str] = {
        "NO_EVIDENCE": "No evidence committed yet",
        "READY": "All current sources are usable under the active mapping state",
        "READY_WITH_LIMITATIONS": (
            "Analysis can continue, but some sources have limited canonical "
            "coverage — they remain preserved as evidence"
        ),
        "REVIEW_RECOMMENDED": (
            "Sources have mapping proposals or stale approvals waiting for review"
        ),
    }

    def source_overview(
        self, case_id: str, *, _analysis: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Deterministic per-source mapping/qualification overview for the UI.

        Pass ``_analysis`` (from ``preview_case_analysis``) to reuse one preview
        across several widgets instead of re-running identical analyses.
        Preview counts are not the saved active analysis.
        """
        load_case(self.workspace_root, case_id)
        if not case_artifact_rows(self.workspace_root, case_id):
            return {
                "schemaVersion": "source-overview/0.2",
                "caseId": case_id,
                "sources": [],
                "readiness": {
                    "state": "NO_EVIDENCE",
                    "stateLabel": self._READINESS_LABELS["NO_EVIDENCE"],
                    "artifacts": 0,
                    "parsed": 0,
                    "profiled": 0,
                    "mapped": 0,
                    "needsMappingReview": 0,
                    "noMappingAvailable": 0,
                    "opaquePreserved": 0,
                },
            }
        analysis = _analysis or self.preview_case_analysis(case_id)
        preview = self.case_mapping_proposals(case_id, _analysis=analysis)
        approvals = self.load_case_mapping_approvals(case_id)
        adapter_rows = {
            str(row["artifactId"]): row for row in project_adapter_qualification_records(analysis)
        }
        source_qualifications = list(analysis.get("sourceQualifications") or ())
        unresolved_ids = {str(item["artifactId"]) for item in preview["unresolvedArtifacts"]}
        proposals_by_artifact: dict[str, list[dict[str, Any]]] = {}
        for proposal in preview["mappingProposals"]:
            proposals_by_artifact.setdefault(str(proposal["artifactId"]), []).append(proposal)

        sources: list[dict[str, Any]] = []
        for row in preview["artifactResults"]:
            artifact_id = str(row["artifactId"])
            opaque = str(row.get("format") or "") == "opaque"
            unresolved = artifact_id in unresolved_ids
            proposals = proposals_by_artifact.get(artifact_id, [])
            approved = approvals.get(artifact_id)
            if opaque:
                mapping_state = "OPAQUE_PRESERVED"
            elif unresolved and approved is not None:
                mapping_state = "APPROVAL_REJECTED_NEEDS_REVIEW"
            elif unresolved and proposals:
                mapping_state = "PROPOSAL_AVAILABLE"
            elif unresolved:
                mapping_state = "NO_MAPPING_AVAILABLE"
            elif approved is not None:
                mapping_state = "APPROVED_USER"
            else:
                mapping_state = "PREMAPPED"
            adapter = adapter_rows.get(artifact_id) or {}
            field_paths: list[str] = []
            try:
                field_paths = list(
                    self.source_profile_detail(case_id=case_id, artifact_id=artifact_id)[
                        "fieldPaths"
                    ]
                )
            except IntegrationRequestError:
                field_paths = []
            sources.append(
                {
                    "artifactId": artifact_id,
                    "path": row.get("path"),
                    "sha256": row.get("sha256"),
                    "format": row.get("format"),
                    "fieldPaths": field_paths,
                    "controlHints": self.control_relevance(field_paths),
                    "syntaxAdapterId": row.get("syntaxAdapterId"),
                    "profileState": row.get("profileState"),
                    "schemaProfileRef": row.get("schemaProfileRef"),
                    "semanticProfileIds": list(row.get("semanticProfileIds") or ()),
                    "recordCount": row.get("recordCount"),
                    "parsedRecordCount": row.get("parsedRecordCount"),
                    "failedRecordCount": row.get("failedRecordCount"),
                    "canonicalEventCount": row.get("canonicalEventCount"),
                    "mappingState": mapping_state,
                    "adapterQualification": {
                        "state": adapter.get("qualificationState") or "NOT_ASSESSED",
                        "adapterId": adapter.get("adapterId"),
                        "limitations": list(adapter.get("knownLimitations") or ()),
                    },
                    "evidenceQualification": self._evidence_qualification(
                        artifact_id, source_qualifications
                    ),
                    "proposalIds": [str(p["proposalId"]) for p in proposals],
                    "approvedProfileId": (
                        str(approved.mapping_profile.get("profileId")) if approved else None
                    ),
                    "nextAction": self.source_next_action(mapping_state),
                    "limitations": list(row.get("limitations") or ()),
                }
            )

        counts = {
            "artifacts": len(sources),
            "parsed": sum(1 for s in sources if s["profileState"] in ("PARSED", "PARTIAL")),
            "profiled": sum(1 for s in sources if s["schemaProfileRef"]),
            "mapped": sum(
                1 for s in sources if s["mappingState"] in ("APPROVED_USER", "PREMAPPED")
            ),
            "needsMappingReview": sum(
                1
                for s in sources
                if s["mappingState"] in ("PROPOSAL_AVAILABLE", "APPROVAL_REJECTED_NEEDS_REVIEW")
            ),
            "noMappingAvailable": sum(
                1 for s in sources if s["mappingState"] == "NO_MAPPING_AVAILABLE"
            ),
            "opaquePreserved": sum(1 for s in sources if s["mappingState"] == "OPAQUE_PRESERVED"),
        }
        if not sources:
            readiness_state = "NO_EVIDENCE"
        elif counts["needsMappingReview"]:
            readiness_state = "REVIEW_RECOMMENDED"
        elif (
            counts["noMappingAvailable"]
            or counts["opaquePreserved"]
            or any(s["profileState"] in ("PARTIAL", "FAILED") for s in sources)
        ):
            readiness_state = "READY_WITH_LIMITATIONS"
        else:
            readiness_state = "READY"
        readiness: dict[str, Any] = dict(counts)
        readiness["state"] = readiness_state
        readiness["stateLabel"] = self._READINESS_LABELS[readiness_state]
        return {
            "schemaVersion": "source-overview/0.2",
            "caseId": case_id,
            "sources": sources,
            "readiness": readiness,
        }

    def command_center_state(
        self, case_id: str, *, _overview: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Deterministic event command-center projection for Competition Mode.

        Real states only — collection health, active-run selection and
        immutable snapshot history are R5-03 slots and are not fabricated.
        """
        load_case(self.workspace_root, case_id)
        artifact_rows = list(case_artifact_rows(self.workspace_root, case_id))
        overview: dict[str, Any] = (
            dict(_overview)
            if _overview
            else (
                self.source_overview(case_id)
                if artifact_rows
                else {
                    "sources": [],
                    "readiness": {
                        "state": "NO_EVIDENCE",
                        "stateLabel": self._READINESS_LABELS["NO_EVIDENCE"],
                    },
                }
            )
        )
        results = self.load_case_results(case_id) or {}
        analysis = results.get("analysis") or {}

        snapshot = self.analysis_snapshot_state(case_id)
        stale_reasons: list[str] = list(snapshot.get("staleReasons") or ())
        analysis_state = "NOT_RUN" if not analysis else ("STALE" if stale_reasons else "CURRENT")

        runs = self.list_competition_runs(case_id)
        active = self.active_run(case_id)
        measurement = (
            self.load_control7_measurement(case_id, str(active["runId"]))
            if active.get("runId")
            else self.load_control7_measurement(case_id)
        )
        c16_measurement = (
            self.load_control16_measurement(case_id, str(active["runId"]))
            if active.get("runId")
            else self.load_control16_measurement(case_id)
        )
        c9_measurement = (
            self.load_control9_measurement(case_id, str(active["runId"]))
            if active.get("runId")
            else self.load_control9_measurement(case_id)
        )
        health = self.collection_health(case_id)
        if measurement:
            c7_state = "MEASURED"
        elif runs:
            c7_state = "NO_MEASUREMENT_YET"
        else:
            c7_state = "NO_RUN_SELECTED"
        if c16_measurement:
            c16_state = str(c16_measurement.get("measurementState") or "PARTIAL")
        else:
            c16_state = "NOT_READY"

        # Control 9 deterministic state + next action. Operator guidance only —
        # never a verdict. Codes are stable machine tokens for the UI.
        c9_profiles = self.list_control9_profiles(case_id) if artifact_rows else []
        c9_baselines = self.list_control9_baselines(case_id) if c9_profiles else []
        c9_stale = bool(
            c9_measurement
            and c9_measurement.get("activeSnapshotRef")
            and c9_measurement.get("activeSnapshotRef") != snapshot.get("snapshotId")
        )
        if not active.get("runId"):
            c9_state, c9_action = "NO_RUN_SELECTED", "SELECT_ACTIVE_RUN"
        elif not c9_profiles:
            c9_state, c9_action = "NO_METRIC_PROFILE", "DEFINE_C9_METRIC"
        elif not c9_baselines:
            c9_state, c9_action = "NO_BASELINE", "SELECT_C9_BASELINE"
        elif c9_measurement is None:
            c9_state, c9_action = "READY_TO_MEASURE", "MEASURE_CONTROL_9"
        elif c9_stale:
            c9_state, c9_action = (
                "STALE_MEASUREMENT",
                "RERUN_ANALYSIS" if stale_reasons else "REMEASURE_CONTROL_9",
            )
        elif str(c9_measurement.get("measurementState")) == "MEASURED":
            c9_state, c9_action = "MEASURED", "EXPORT_C9_BUNDLE_FOR_HAIEC"
        elif str(c9_measurement.get("measurementState")) == "PARTIAL":
            c9_state, c9_action = "PARTIAL", "RESOLVE_C9_MEASUREMENT_GAPS"
        elif str((c9_measurement.get("compatibility") or {}).get("overallState")) == (
            "INCOMPATIBLE"
        ):
            c9_state, c9_action = "INCOMPATIBLE", "FIX_C9_COMPATIBILITY"
        else:
            c9_state, c9_action = "NOT_MEASURED", "QUALIFY_KPI_FIELDS"
        c9_block = {
            "state": c9_state,
            "runId": (c9_measurement or {}).get("runId"),
            "measurementState": (c9_measurement or {}).get("measurementState"),
            "metricProfileRef": (c9_measurement or {}).get("metricProfileRef"),
            "baselineRef": (c9_measurement or {}).get("baselineRef"),
            "coveragePercent": (c9_measurement or {}).get("coveragePercent"),
            "nextAction": c9_action,
        }

        frontier = analysis.get("evidenceFrontier") or []
        readiness = overview.get("readiness") or {}
        material_health_gaps = bool(
            health.get("state") == "REPORTED"
            and (
                (health.get("totals") or {}).get("failedRecordCount")
                or health.get("preservedOnlySources")
            )
        )

        # Deterministic next-action projection — operator guidance, not an
        # assurance judgment.
        if not artifact_rows:
            next_action = ("ADD_EVIDENCE", "Add the evidence supplied by the environment.")
        elif readiness.get("needsMappingReview"):
            next_action = (
                "SOURCE_REVIEW_REQUIRED",
                "Review Source Setup before analysis — "
                f"{readiness['needsMappingReview']} source(s) have mapping proposals "
                "or stale approvals.",
            )
        elif stale_reasons:
            next_action = (
                "MAPPING_APPROVED_ANALYSIS_STALE",
                "Your evidence or mapping changed after this analysis. Run analysis "
                "again to create a new snapshot — the previous snapshot remains preserved.",
            )
        elif not analysis:
            next_action = ("READY_FOR_ANALYSIS", "Run deterministic analysis.")
        elif material_health_gaps:
            next_action = (
                "REVIEW_COLLECTION_HEALTH",
                "Collection has limitations worth reviewing — see Source Setup / "
                "Collection Health before measuring controls.",
            )
        elif not runs:
            next_action = (
                "REVIEW_RUN_CANDIDATES",
                "Review discovered runs and confirm the execution you want to investigate.",
            )
        elif active.get("runId") is None:
            next_action = (
                "SELECT_ACTIVE_RUN",
                "Select the active run — measurement and handoff follow the globally selected run.",
            )
        elif active.get("resolutionState") == "AMBIGUOUS":
            next_action = (
                "REVIEW_RUN_EVIDENCE",
                "The active run has ambiguous evidence — review the conflicting "
                "identifiers on the Runs step.",
            )
        elif not self.list_expected_manifests(case_id):
            next_action = (
                "BUILD_EXPECTED_EVENT_SET",
                "Build the expected-event manifest — blank, from a calibration "
                "run, or from a template — on the Competition Controls step.",
            )
        elif c7_state != "MEASURED":
            next_action = (
                "MEASURE_CONTROL_7",
                "Run the deterministic Control 7 measurement for the active "
                "run and reviewed manifest.",
            )
        else:
            # Handoff progression reuses the same deterministic readiness
            # projection as the HAIEC handoff panel — a bare non-empty
            # references map is never enough.
            handoff = self.haiec_handoff_status(case_id, str(active.get("runId")))
            if not handoff["measurementReady"]:
                next_action = (
                    "REMEASURE_CONTROL_7",
                    "The stored Control 7 measurement is not bound to the "
                    "current analysis snapshot/bundle. " + str(handoff["nextAction"]),
                )
            elif not handoff["handoffComplete"]:
                next_action = (
                    "ATTACH_OR_FREEZE_HAIEC_CONTROL",
                    "Measurement is ready. Before presenting an assessed "
                    "result, select/freeze the governing Control 7 rule in "
                    "HAIEC and bind it to this run/bundle.",
                )
            elif c16_measurement is None:
                next_action = (
                    "MEASURE_CONTROL_16",
                    "Control 7 handoff is complete. Run the deterministic "
                    "Control 16 token & retry reconciliation for the active run.",
                )
            elif c16_measurement.get("activeSnapshotRef") != snapshot.get("snapshotId"):
                next_action = (
                    "REMEASURE_CONTROL_16",
                    "The stored Control 16 measurement is bound to a prior "
                    "analysis snapshot — rerun the reconciliation.",
                )
            elif str(c16_measurement.get("measurementState")) == "PARTIAL":
                blockers = [lim for lim in c16_measurement.get("limitations") or () if ":" in lim]
                next_action = (
                    "RESOLVE_USAGE_EVIDENCE",
                    "Control 16 reconciliation is PARTIAL — "
                    + (", ".join(blockers[:3]) if blockers else "see measurement limitations")
                    + ". Missing usage is not zero; resolve the evidence, then remeasure.",
                )
            elif str(c16_measurement.get("measurementState")) == "NOT_MEASURED":
                next_action = (
                    "QUALIFY_TOKEN_FIELDS",
                    "No qualified model-call usage evidence bound to the active "
                    "run — review Source Setup mappings and usage fields.",
                )
            else:
                next_action = (
                    "EXPORT_C16_BUNDLE_FOR_HAIEC",
                    "Control 16 reconciliation is MEASURED. Export the "
                    "Competition Evidence Bundle and evaluate ACN-COST-001 "
                    "against the frozen HAIEC token-cap policy.",
                )

        # Per-control feasibility — deterministic READY/WITH-LIMITATIONS/
        # NOT_READY for the feasibility chooser; reuses already-loaded state.
        active_resolution = (
            self.load_competition_resolution(case_id, str(active["runId"]))
            if active.get("runId")
            else None
        )
        bound_refs = set((active_resolution or {}).get("qualifiedEventRefs") or ())
        run_fields = {
            str(key)
            for event in (analysis.get("canonicalEvents") or ())
            if str(event.get("eventId")) in bound_refs
            for key in (event.get("attributes") or {})
        }
        feasibility = control_feasibility(
            active_run=active,
            resolution=active_resolution,
            manifests=self.list_expected_manifests(case_id),
            c7_measurement=measurement,
            c9_profiles=c9_profiles,
            c9_baselines=c9_baselines,
            c9_compatibility=(c9_measurement or {}).get("compatibility"),
            c9_measurement=c9_measurement,
            c16_usage_fields_present=any(
                hint["controlCode"] == CONTROL16_CODE
                for hint in self.control_relevance(sorted(run_fields))
            ),
            c16_measurement=c16_measurement,
        )

        return {
            "schemaVersion": "command-center/0.2",
            "caseId": case_id,
            "artifactCount": len(artifact_rows),
            "readinessState": readiness.get("state") or "NO_EVIDENCE",
            "readinessLabel": readiness.get("stateLabel"),
            "readinessCounts": readiness,
            "analysis": {
                "state": analysis_state,
                "runId": analysis.get("analysisRunId"),
                "createdAt": (analysis.get("snapshot") or {}).get("createdAt"),
                "staleReasons": stale_reasons,
            },
            "snapshot": {
                "snapshotId": snapshot.get("snapshotId"),
                "label": snapshot.get("snapshotLabel"),
                "state": snapshot["state"],
                "provenance": snapshot.get("provenance"),
            },
            "collectionHealth": {
                "state": health["state"],
                "parsedSources": health.get("parsedSources"),
                "preservedOnlySources": health.get("preservedOnlySources"),
                "failedRecordCount": (health.get("totals") or {}).get("failedRecordCount"),
                "coverageState": health.get("coverageState"),
                "limitationCount": len(health.get("limitations") or ()),
            },
            "control7": {
                "state": c7_state,
                "runId": (measurement or {}).get("runId"),
                "measurementState": (measurement or {}).get("measurementState"),
            },
            "control9": c9_block,
            "control16": {
                "state": c16_state,
                "runId": (c16_measurement or {}).get("runId"),
                "measurementState": (c16_measurement or {}).get("measurementState"),
                "actualRunTokens": (c16_measurement or {}).get("actualRunTokens"),
                "knownQualifiedTokens": (c16_measurement or {}).get("knownQualifiedTokens"),
            },
            "capabilityTruth": capability_truth(),
            "controlFeasibility": feasibility["controls"],
            "activeRun": active,
            "confirmedRunCount": len(runs),
            "openGaps": len(frontier) if analysis else None,
            "nextAction": {"code": next_action[0], "message": next_action[1]},
        }

    def source_profile_detail(self, *, case_id: str, artifact_id: str) -> dict[str, Any]:
        """Schema-profile detail for one committed artifact (re-profiles the
        immutable bytes deterministically — never mutates canonical state)."""
        rows = {
            str(row["artifact_id"]): row for row in case_artifact_rows(self.workspace_root, case_id)
        }
        row = rows.get(artifact_id)
        if row is None:
            raise IntegrationRequestError(f"unknown case artifact: {artifact_id}")
        content = read_case_artifact(self.workspace_root, case_id, row)
        profile = profile_artifact(
            artifact_id=artifact_id,
            format_name=str(row.get("format_family") or "opaque"),
            content=content,
            file_name=str(row["logical_path"]),
        )
        schema = profile["schemaProfile"]
        field_paths = [str(item["path"]) for item in schema.get("fieldProfiles") or ()]
        return {
            "artifactId": artifact_id,
            "path": row["logical_path"],
            "format": row.get("format_family"),
            "schemaProfile": schema,
            "fieldPaths": field_paths,
            "controlRelevance": self.control_relevance(field_paths),
            "state": profile["state"],
            "parseFailures": profile["parseFailures"],
            "recordCount": profile["recordCount"],
        }

    def mapping_proposal_detail(
        self,
        *,
        case_id: str,
        artifact_id: str,
        proposal_id: str,
        _analysis: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Flatten a mapping proposal's template into reviewable rows plus
        field coverage against the artifact's detected schema."""
        preview = self.case_mapping_proposals(case_id, _analysis=_analysis)
        proposal = next(
            (
                item
                for item in preview["mappingProposals"]
                if str(item["artifactId"]) == artifact_id and str(item["proposalId"]) == proposal_id
            ),
            None,
        )
        if proposal is None:
            raise IntegrationRequestError(
                f"no mapping proposal '{proposal_id}' for artifact '{artifact_id}'"
            )
        template = load_default_mapping_registry().get(str(proposal["templateProfileId"]))
        mapping_rows: list[dict[str, Any]] = []
        for category in (
            "timeMappings",
            "fieldMappings",
            "entityMappings",
            "operationMappings",
            "statusMappings",
            "stateMappings",
            "correlationMappings",
            "relationMappings",
            "scenarioMappings",
            "transformRules",
        ):
            for item in template.mapping_profile.get(category, []):
                mapping_rows.append(
                    {
                        "category": category,
                        "sourceField": item.get("sourcePath"),
                        "canonicalField": item.get("targetPath"),
                        "transform": item.get("transform"),
                        "required": bool(item.get("required", False)),
                    }
                )
        detail = self.source_profile_detail(case_id=case_id, artifact_id=artifact_id)
        detected = set(detail["fieldPaths"])
        mapped_sources = {str(r["sourceField"]) for r in mapping_rows if r["sourceField"]}
        required_sources = {str(r["sourceField"]) for r in mapping_rows if r["required"]}
        return {
            "proposal": proposal,
            "templateProfileId": str(template.mapping_profile.get("profileId")),
            "mappingRows": mapping_rows,
            "coverage": {
                "detectedFields": len(detected),
                "mappedFields": len(mapped_sources & detected),
                "unmappedFields": sorted(detected - mapped_sources),
                "requiredMappedFields": len(required_sources & detected),
                "requiredTotal": len(required_sources),
            },
            "fieldPaths": detail["fieldPaths"],
            "controlRelevance": detail["controlRelevance"],
        }

    def approved_mapping_detail(self, *, case_id: str, artifact_id: str) -> dict[str, Any] | None:
        """Persisted USER-approved binding for one artifact, if present."""
        entry = self.load_case_mapping_approvals(case_id).get(artifact_id)
        if entry is None:
            return None
        profile = entry.mapping_profile
        return {
            "artifactId": artifact_id,
            "artifactSha256": entry.artifact_sha256,
            "artifactPath": entry.artifact_path,
            "profileId": profile.get("profileId"),
            "templateProposalIds": list(profile.get("acceptedProposalIds") or ()),
            "approvalMode": profile.get("approvalMode"),
            "approvedAt": profile.get("approvedAt"),
            "sourceFingerprint": profile.get("sourceFingerprint"),
            "limitations": list(profile.get("limitations") or ()),
        }

    def source_provenance(
        self,
        *,
        case_id: str,
        artifact_id: str,
        _overview: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministic provenance chain for one source artifact."""
        overview = dict(_overview) if _overview else self.source_overview(case_id)
        row = next((s for s in overview["sources"] if s["artifactId"] == artifact_id), None)
        if row is None:
            raise IntegrationRequestError(f"unknown case artifact: {artifact_id}")
        approved = self.approved_mapping_detail(case_id=case_id, artifact_id=artifact_id)
        return {
            "artifact": row["path"],
            "artifactSha256": row["sha256"],
            "syntaxAdapter": row["syntaxAdapterId"],
            "format": row["format"],
            "schemaProfile": row["schemaProfileRef"],
            "semanticProfiles": row["semanticProfileIds"],
            "mappingProfile": (approved["profileId"] if approved else None)
            or ("none — " + str(row["mappingState"])),
            "canonicalEventCount": row["canonicalEventCount"],
            "mappingState": row["mappingState"],
        }

    # ---- event teammate layer ------------------------------------------------
    # Deterministic projections for the event-operating surface: control
    # feasibility, discovery artifacts, registers, Judgment-Day readiness and
    # the portable evidence pack. Everything here reads existing canonical
    # state — nothing invents HAIEC-side truth; external items stay UNKNOWN.

    _DISCOVERY_OUTPUT = "discovery-workspace"

    def _event_context(self, case_id: str) -> dict[str, Any]:
        """Shared deterministic inputs for the event-layer projections."""
        load_case(self.workspace_root, case_id)
        results = self.load_case_results(case_id) or {}
        analysis = results.get("analysis") or {}
        active = self.active_run(case_id)
        run_id = str(active.get("runId") or "") or None
        resolution = self.load_competition_resolution(case_id, run_id) if run_id else None
        canonical = list(analysis.get("canonicalEvents") or ())

        bound = set((resolution or {}).get("qualifiedEventRefs") or ())
        field_names = {
            str(key)
            for event in canonical
            if str(event.get("eventId")) in bound
            for key in (event.get("attributes") or {})
        }
        usage_present = any(
            hint["controlCode"] == CONTROL16_CODE
            for hint in self.control_relevance(sorted(field_names))
        )

        profiles = self.list_control9_profiles(case_id)
        baselines = self.list_control9_baselines(case_id)
        compat: dict[str, Any] | None = None
        if run_id and profiles and baselines:
            try:
                compat = self.control9_compatibility_preview(
                    case_id=case_id,
                    profile_id=str(profiles[-1]["profileId"]),
                    baseline_id=str(baselines[-1]["baselineId"]),
                    run_id=run_id,
                )["compatibility"]
            except (IntegrationRequestError, KeyError, TypeError, ValueError):
                compat = None

        # Qualified run-activity provenance per declared run — resolved from
        # persisted run resolutions where they exist, else deterministically
        # re-resolved. Never inferred from declaration/observation timestamps.
        declarations = self.list_competition_runs(case_id)
        run_activities: dict[str, dict[str, Any]] = {}
        resolutions: dict[str, dict[str, Any]] = {}
        for decl in declarations:
            rid = str(decl.get("runId"))
            run_resolution = (
                resolution
                if run_id == rid and resolution is not None
                else self.load_competition_resolution(case_id, rid)
            )
            if run_resolution is None:
                others = [r for r in declarations if str(r.get("runId")) != rid]
                run_resolution = resolve_competition_run(canonical, decl, other_declarations=others)
            run_activities[rid] = resolve_run_activity(canonical, run_resolution)
            resolutions[rid] = run_resolution

        return {
            "analysis": analysis,
            "canonicalEvents": canonical,
            "active": active,
            "runId": run_id,
            "resolution": resolution,
            "resolutions": resolutions,
            "runActivities": run_activities,
            "runActivity": run_activities.get(run_id) if run_id else None,
            "manifests": self.list_expected_manifests(case_id),
            "c7": self.load_control7_measurement(case_id, run_id),
            "c9": self.load_control9_measurement(case_id, run_id),
            "c16": self.load_control16_measurement(case_id, run_id),
            "profiles": profiles,
            "baselines": baselines,
            "c9Compatibility": compat,
            "c16UsageFieldsPresent": usage_present,
            "runs": self.list_competition_runs(case_id),
            "snapshot": self.analysis_snapshot_state(case_id),
            "health": self.collection_health(case_id),
            "overview": (
                self.source_overview(case_id)
                if case_artifact_rows(self.workspace_root, case_id)
                else {"sources": [], "readiness": {"state": "NO_EVIDENCE"}}
            ),
            "workspace": load_case_output(self.workspace_root, case_id, name=self._DISCOVERY_OUTPUT)
            or {},
        }

    @staticmethod
    def _external_haiec_refs(ctx: Mapping[str, Any]) -> dict[str, Any]:
        """HAIEC references explicitly supplied on stored measurements."""
        refs: dict[str, Any] = {}
        for key in ("c7", "c9", "c16"):
            for ref_key, value in ((ctx.get(key) or {}).get("references") or {}).items():
                if value:
                    refs[str(ref_key)] = value
        return refs

    def control_feasibility_state(self, case_id: str) -> dict[str, Any]:
        """READY / READY_WITH_LIMITATIONS / NOT_READY per control — deterministic."""
        ctx = self._event_context(case_id)
        return control_feasibility(
            active_run=ctx["active"],
            resolution=ctx["resolution"],
            manifests=ctx["manifests"],
            c7_measurement=ctx["c7"],
            c9_profiles=ctx["profiles"],
            c9_baselines=ctx["baselines"],
            c9_compatibility=ctx["c9Compatibility"],
            c9_measurement=ctx["c9"],
            c16_usage_fields_present=ctx["c16UsageFieldsPresent"],
            c16_measurement=ctx["c16"],
        )

    def discovery_workspace(self, case_id: str) -> dict[str, Any]:
        """The five first-hour artifacts — auto-populated where deterministic,
        operator-entered entries preserved from the workspace document."""
        ctx = self._event_context(case_id)
        workspace = ctx["workspace"]
        return {
            "schemaVersion": "discovery-workspace/0.1",
            "caseId": case_id,
            "sourceInventory": source_inventory(ctx["overview"]),
            "runIdMap": run_id_map(ctx["canonicalEvents"]),
            "enforcementPoints": list(workspace.get("enforcementPoints") or ()),
            "metricInventoryHints": {
                code: [
                    row
                    for row in (ctx["overview"].get("sources") or ())
                    if any(h.get("controlCode") == code for h in row.get("controlHints") or ())
                ]
                for code in (CONTROL7_CODE, CONTROL9_CODE, CONTROL16_CODE)
            },
            "scenarioRunMap": [
                {
                    "runId": run.get("runId"),
                    "label": run.get("label"),
                    "runRole": run.get("runRole"),
                    "scenarioLabel": run.get("scenarioLabel"),
                    "resolutionState": run.get("resolutionState"),
                }
                for run in ctx["runs"]
            ],
            "operatorGapEntries": list(workspace.get("operatorGapEntries") or ()),
            "notes": str(workspace.get("notes") or ""),
        }

    def update_discovery_workspace(
        self,
        *,
        case_id: str,
        enforcement_points: Sequence[Mapping[str, Any]] | None = None,
        operator_gap_entries: Sequence[Mapping[str, Any]] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Persist operator-entered discovery content (enforcement points,
        policy/enforcement gap rows, notes). Bounded, validated, user-owned."""
        load_case(self.workspace_root, case_id)
        workspace = dict(
            load_case_output(self.workspace_root, case_id, name=self._DISCOVERY_OUTPUT) or {}
        )
        if enforcement_points is not None:
            rows: list[dict[str, Any]] = []
            for entry in enforcement_points:
                name = str(entry.get("point") or "").strip()
                if not name:
                    raise IntegrationRequestError("enforcement point requires a name")
                rows.append(
                    {
                        "point": name[:120],
                        "passesThrough": str(entry.get("passesThrough") or "")[:400],
                        "candidateControls": [
                            str(c) for c in (entry.get("candidateControls") or ())
                        ][:8],
                        "canObserve": bool(entry.get("canObserve")),
                        "canRefuse": bool(entry.get("canRefuse")),
                        "telemetryEmitted": str(entry.get("telemetryEmitted") or "")[:200],
                    }
                )
            workspace["enforcementPoints"] = rows[:50]
        if operator_gap_entries is not None:
            allowed = {
                "POLICY",
                "ENFORCEMENT",
                "LAB_ACCESS",
                "EVIDENCE",
                "COLLECTION",
                "MAPPING",
                "RUN_RESOLUTION",
                "MEASUREMENT",
                "COVERAGE",
            }
            rows = []
            for entry in operator_gap_entries:
                category = str(entry.get("category") or "POLICY")
                if category not in allowed:
                    raise IntegrationRequestError(f"unknown gap category: {category}")
                rows.append(
                    {
                        "category": category,
                        "control": entry.get("control"),
                        "run": entry.get("run"),
                        "gap": str(entry.get("gap") or "")[:400],
                        "whyItMatters": str(entry.get("whyItMatters") or "")[:400],
                        "consequence": str(entry.get("consequence") or "")[:400],
                        "whatRemainsSupportable": str(entry.get("whatRemainsSupportable") or "")[
                            :400
                        ],
                        "nextAction": str(entry.get("nextAction") or "")[:400],
                        "evidenceRefs": [str(r) for r in (entry.get("evidenceRefs") or ())][:20],
                    }
                )
            workspace["operatorGapEntries"] = rows[:100]
        if notes is not None:
            workspace["notes"] = str(notes)[:4000]
        workspace["schemaVersion"] = "discovery-workspace-store/0.1"
        workspace["caseId"] = case_id
        save_case_output(
            self.workspace_root, case_id, name=self._DISCOVERY_OUTPUT, payload=workspace
        )
        return workspace

    def event_source_registry(self, case_id: str) -> dict[str, Any]:
        """Source Intake Registry — readiness rows + capability matrix over
        existing intake/mapping state. No new storage; a projection."""
        ctx = self._event_context(case_id)
        registry = source_registry(
            overview_sources=list(ctx["overview"].get("sources") or ()),
            canonical_events=ctx["canonicalEvents"],
            run_resolutions=list(ctx["resolutions"].values()),
            run_activities=list(ctx["runActivities"].values()),
        )
        registry["matrix"] = capability_matrix(registry)
        return registry

    def enforcement_point_discovery(self, case_id: str) -> dict[str, Any]:
        """Observed + operator-declared enforcement-point candidates —
        evidence hints only; the lab architecture is never pre-labeled."""
        ctx = self._event_context(case_id)
        return enforcement_point_discovery(
            canonical_events=ctx["canonicalEvents"],
            declared_points=ctx["workspace"].get("enforcementPoints") or (),
        )

    def first_hour_dashboard(self, case_id: str) -> dict[str, Any]:
        """The compact first-hour block: source registry, capability matrix,
        run identity, run start, enforcement points, control readiness and
        prioritized deterministic next actions."""
        ctx = self._event_context(case_id)
        registry = source_registry(
            overview_sources=list(ctx["overview"].get("sources") or ()),
            canonical_events=ctx["canonicalEvents"],
            run_resolutions=list(ctx["resolutions"].values()),
            run_activities=list(ctx["runActivities"].values()),
        )
        registry["matrix"] = capability_matrix(registry)
        ep = enforcement_point_discovery(
            canonical_events=ctx["canonicalEvents"],
            declared_points=ctx["workspace"].get("enforcementPoints") or (),
        )
        feasibility = control_source_feasibility(
            canonical_events=ctx["canonicalEvents"],
            overview_sources=list(ctx["overview"].get("sources") or ()),
            resolution=ctx["resolution"],
            declared_run=bool(ctx["active"].get("runId")),
            manifests=ctx["manifests"],
            profiles=ctx["profiles"],
            baselines=ctx["baselines"],
            ep_discovery=ep,
        )
        dashboard = first_hour_dashboard(
            registry=registry,
            runs=ctx["runs"],
            resolutions=ctx["resolutions"],
            run_activities=ctx["runActivities"],
            ep_discovery=ep,
            feasibility=feasibility,
        )
        dashboard["sourceRegistry"] = registry
        dashboard["capabilityMatrix"] = registry["matrix"]
        dashboard["enforcementPointDiscovery"] = ep
        dashboard["acquisitionFeasibility"] = feasibility
        return dashboard

    def handoff_preview(self, case_id: str) -> dict[str, Any]:
        """Per-control HAIEC handoff preview — what a Competition Evidence
        Bundle would carry right now, plus the deterministic next step.

        Nothing is persisted here; running the measurement produces the
        real bundle. ``runStartedAt`` mirrors the qualified run-activity
        contract — null unless the run start is ESTABLISHED.
        """
        ctx = self._event_context(case_id)
        analysis = ctx["analysis"]
        activity = ctx.get("runActivity") or {}
        feasibility = control_source_feasibility(
            canonical_events=ctx["canonicalEvents"],
            overview_sources=list(ctx["overview"].get("sources") or ()),
            resolution=ctx["resolution"],
            declared_run=bool(ctx["active"].get("runId")),
            manifests=ctx["manifests"],
            profiles=ctx["profiles"],
            baselines=ctx["baselines"],
            ep_discovery=enforcement_point_discovery(
                canonical_events=ctx["canonicalEvents"],
                declared_points=ctx["workspace"].get("enforcementPoints") or (),
            ),
        )
        bound_refs = list((ctx["resolution"] or {}).get("qualifiedEventRefs") or ())
        bound_set = {str(ref) for ref in bound_refs}
        # Source attribution for skeptical-stranger traceability — which
        # committed artifacts produced the run-bound evidence.
        source_artifact_ids = sorted(
            {
                str(raw.get("artifactId"))
                for event in ctx["canonicalEvents"]
                if str(event.get("eventId")) in bound_set
                for raw in (event.get("rawRecordRefs") or ())
                if isinstance(raw, Mapping) and raw.get("artifactId")
            }
        )
        bundle = self.load_competition_bundle(case_id, ctx["runId"])
        controls: dict[str, Any] = {}
        for key, code, measurement in (
            ("C7", CONTROL7_CODE, ctx["c7"]),
            ("C9", CONTROL9_CODE, ctx["c9"]),
            ("C16", CONTROL16_CODE, ctx["c16"]),
        ):
            acq = (feasibility.get("controls") or {}).get(key) or {}
            measured = measurement is not None
            controls[key] = {
                "controlCode": code,
                "acquisitionState": acq.get("state") or "BLOCKED",
                "missingFacts": list(acq.get("missingFacts") or ()),
                "preview": {
                    "runId": ctx["runId"],
                    "runStartedAt": activity.get("runStartedAt"),
                    "runActivityState": activity.get("startState"),
                    "measurementType": code,
                    "measurementState": (
                        measurement.get("measurementState") if measured else "NOT_MEASURED_YET"
                    ),
                    "bundleId": (bundle or {}).get("bundleId"),
                    "analysisRunId": analysis.get("analysisRunId"),
                    "evidenceSetRef": analysis.get("evidenceSetId"),
                    "evidenceRefs": len(bound_refs),
                    # Skeptical-stranger traceability — the identity chain a
                    # second operator follows without verbal explanation.
                    "mappingProfileRefs": list((measurement or {}).get("mappingProfileRefs") or ()),
                    "sourceRefs": source_artifact_ids,
                    "limitations": list(
                        ((bundle or {}).get("limitations") or ())
                        if measured
                        else (acq.get("missingFacts") or ())
                    ),
                },
                "action": (
                    "Export for HAIEC — the canonical Competition Evidence "
                    "Bundle already exists for this run."
                    if measured and bundle
                    else (
                        "Run the measurement — it produces the canonical "
                        "Competition Evidence Bundle for HAIEC."
                        if acq.get("state") == "READY"
                        else "Resolve the missing facts first — "
                        + ", ".join(acq.get("missingFacts") or ())
                    )
                ),
            }
        return {
            "schemaVersion": "handoff-preview/0.1",
            "caseId": case_id,
            "runId": ctx["runId"],
            "runStartedAt": activity.get("runStartedAt"),
            "runActivityState": activity.get("startState"),
            "controls": controls,
            "note": (
                "The canonical Competition Evidence Bundle is the only "
                "handoff surface — this preview never creates a second "
                "transport contract."
            ),
        }

    def competition_gap_register(self, case_id: str) -> dict[str, Any]:
        """Exportable Gap Register from deterministic limitations/frontiers."""
        ctx = self._event_context(case_id)
        return gap_register(
            case_id=case_id,
            frontier=ctx["analysis"].get("evidenceFrontier") or (),
            health=ctx["health"],
            overview=ctx["overview"],
            resolution=ctx["resolution"],
            c7=ctx["c7"],
            c9=ctx["c9"],
            c16=ctx["c16"],
            active_run=ctx["active"],
            operator_entries=ctx["workspace"].get("operatorGapEntries") or (),
            external_refs=self._external_haiec_refs(ctx),
            run_activities=ctx["runActivities"],
        )

    def competition_run_register(self, case_id: str) -> dict[str, Any]:
        """Exportable run register — roles and measurement states, no verdicts."""
        ctx = self._event_context(case_id)
        states: dict[str, dict[str, Any]] = {}
        for run in ctx["runs"]:
            rid = str(run["runId"])
            states[rid] = {
                CONTROL7_CODE: self.load_control7_measurement(case_id, rid),
                CONTROL9_CODE: self.load_control9_measurement(case_id, rid),
                CONTROL16_CODE: self.load_control16_measurement(case_id, rid),
            }
        return run_register(
            case_id=case_id,
            runs=ctx["runs"],
            measurement_states=states,
            snapshot=ctx["snapshot"],
            run_activities=ctx["runActivities"],
        )

    def judgment_day_state(self, case_id: str) -> dict[str, Any]:
        """Six-artifact + three-axis readiness for the Export/Judge surface."""
        ctx = self._event_context(case_id)
        return judgment_day_readiness(
            runs=ctx["runs"],
            measurements={
                CONTROL7_CODE: ctx["c7"],
                CONTROL9_CODE: ctx["c9"],
                CONTROL16_CODE: ctx["c16"],
            },
            external_refs=self._external_haiec_refs(ctx),
            run_activity=ctx["runActivity"],
        )

    def judge_evidence_pack(self, case_id: str) -> tuple[bytes, dict[str, Any]]:
        """Build the portable TMF-JUDGE-EVIDENCE-PACK.zip + its manifest."""
        ctx = self._event_context(case_id)
        register = self.competition_run_register(case_id)
        gaps = self.competition_gap_register(case_id)
        manifests = [dict(row) for row in list_manifests(self.workspace_root, case_id)]
        inventory = [dict(row) for row in evidence_inventory(self.workspace_root, case_id)]
        per_run: dict[str, dict[str, Any]] = {}
        for run in ctx["runs"]:
            rid = str(run["runId"])
            per_run[rid] = {
                "resolution": self.load_competition_resolution(case_id, rid),
                "runActivity": ctx["runActivities"].get(rid),
                "sourceManifest": {"manifests": manifests, "artifacts": inventory},
                "snapshot": {
                    "snapshotId": ctx["snapshot"].get("snapshotId"),
                    "label": ctx["snapshot"].get("label"),
                    "state": ctx["snapshot"].get("state"),
                },
                "measurements": {
                    CONTROL7_CODE: self.load_control7_measurement(case_id, rid),
                    CONTROL9_CODE: self.load_control9_measurement(case_id, rid),
                    CONTROL16_CODE: self.load_control16_measurement(case_id, rid),
                },
            }
        version = "unknown"
        with contextlib.suppress(Exception):  # version label is descriptive only
            from importlib.metadata import version as _pkg_version

            version = _pkg_version("logsense")
        return build_judge_pack(
            case_id=case_id,
            created_at=_utc_now(),
            source_version=version,
            source_git_sha=None,
            register=register,
            gap_reg=gaps,
            per_run=per_run,
            external_refs=self._external_haiec_refs(ctx),
            architecture_labels=(ctx["workspace"].get("architectureLabels") or None),
        )

    def event_readiness_state(self, case_id: str) -> dict[str, Any]:
        """One composed event-operating projection for the UI and AI context."""
        ctx = self._event_context(case_id)
        return {
            "schemaVersion": "event-readiness/0.1",
            "caseId": case_id,
            "feasibility": control_feasibility(
                active_run=ctx["active"],
                resolution=ctx["resolution"],
                manifests=ctx["manifests"],
                c7_measurement=ctx["c7"],
                c9_profiles=ctx["profiles"],
                c9_baselines=ctx["baselines"],
                c9_compatibility=ctx["c9Compatibility"],
                c9_measurement=ctx["c9"],
                c16_usage_fields_present=ctx["c16UsageFieldsPresent"],
                c16_measurement=ctx["c16"],
            ),
            "readiness": judgment_day_readiness(
                runs=ctx["runs"],
                measurements={
                    CONTROL7_CODE: ctx["c7"],
                    CONTROL9_CODE: ctx["c9"],
                    CONTROL16_CODE: ctx["c16"],
                },
                external_refs=self._external_haiec_refs(ctx),
                run_activity=ctx["runActivity"],
            ),
            "runIdMap": run_id_map(ctx["canonicalEvents"]),
            "sourceInventory": source_inventory(ctx["overview"]),
            "discovery": {
                "enforcementPoints": ctx["workspace"].get("enforcementPoints") or (),
                "operatorGapEntries": ctx["workspace"].get("operatorGapEntries") or (),
            },
        }
