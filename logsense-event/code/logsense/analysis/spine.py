from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from logsense.adapters.canonical_events import project_canonical_events
from logsense.adapters.mapping_profiles import MappingProfileEntry, load_default_mapping_registry
from logsense.adapters.profiling import profile_artifact
from logsense.adapters.registry import load_default_registry
from logsense.adapters.runtime_mapping import (
    MappingProposal,
    approved_mapping_matches_proposals,
    propose_schema_compatible_mappings,
)
from logsense.adapters.semantic_profiles import load_event_semantic_registry
from logsense.adapters.source_descriptors import SourceDescriptorProjector
from logsense.forensics.actions import assemble_action_groups
from logsense.forensics.cause_activation import (
    CauseEvaluationInstruction,
    evaluate_cause_instruction,
)
from logsense.forensics.context import project_context_lineage_item
from logsense.forensics.delegation import evaluate_delegated_action_integrity
from logsense.forensics.effects import assess_effect_envelope
from logsense.forensics.findings import (
    action_status_contradiction,
    coverage_gaps,
    source_authority_contradiction,
)
from logsense.forensics.frontier import project_frontiers_from_gaps
from logsense.forensics.identity import assess_source_independence
from logsense.forensics.lifecycle import (
    evaluate_action_lifecycle,
    evaluate_five_plane_coverage,
    reconstruct_state_transitions,
)
from logsense.forensics.mediation import assess_guardrail_mediation
from logsense.forensics.qualification import qualify_source
from logsense.forensics.recovery import assess_recovery_projection
from logsense.forensics.relations import bind_transition, evaluate_changes_binding
from logsense.forensics.snapshots import build_investigation_snapshot
from logsense.forensics.stories import project_investigation_stories
from logsense.forensics.temporal import (
    normalize_event_time,
    source_coverage_profile,
    timeline_event,
)
from logsense.telemetry.otlp import (
    detect_otlp_envelope_signals,
    parse_otlp_logs_payload,
    parse_otlp_metrics_payload,
    parse_otlp_trace_payload,
    reconstruct_trace_paths,
)


@dataclass(frozen=True)
class ArtifactEvidence:
    artifact_id: str
    path: str
    content: bytes
    ingested_at: str
    media_type: str | None = None
    currentness: str = "UNKNOWN"
    completeness_state: str = "UNKNOWN"
    environment: str | None = None
    producer: str | None = None


@dataclass(frozen=True)
class OtlpTraceEvidence:
    artifact_ref: str
    source_ref: str
    content: bytes
    otlp_spec_version: str | None = None
    semantic_conventions_version: str | None = None


@dataclass(frozen=True)
class OtlpLogEvidence:
    artifact_ref: str
    source_ref: str
    content: bytes
    otlp_spec_version: str | None = None
    semantic_conventions_version: str | None = None


@dataclass(frozen=True)
class OtlpMetricEvidence:
    artifact_ref: str
    source_ref: str
    content: bytes
    otlp_spec_version: str | None = None
    semantic_conventions_version: str | None = None


@dataclass(frozen=True)
class DelegatedActionIntegrityInstruction:
    action_group_ref: str
    dimensions: tuple[Mapping[str, Any], ...]
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextLineageInstruction:
    context_item_ref: str
    origin: str
    source_authority: str
    mutability: str
    validation_state: str
    integrity_state: str
    temporal_basis: str
    model_visible: bool | None
    explicitly_referenced: bool | None
    retrieved_at: str | None = None
    evidence_refs: tuple[str, ...] = ()
    influence_evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuardrailMediationInstruction:
    action_group_ref: str
    guardrail_ref: str
    requirement_declared: bool | None
    confirmation_presented: bool | None
    confirmation_completed: bool | None
    decision: str
    decision_time_ref: str | None
    action_time_ref: str | None
    decision_time: str | None
    action_time: str | None
    deny_branch_blocked_action: bool | None
    approved_argument_digest: str | None
    executed_argument_digest: str | None
    mediation_evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryInstruction:
    incident_snapshot_ref: str
    recovery_action_refs: tuple[str, ...] = ()
    rollback_requested_refs: tuple[str, ...] = ()
    rollback_completed_refs: tuple[str, ...] = ()
    state_restored_refs: tuple[str, ...] = ()
    service_health_restored_refs: tuple[str, ...] = ()
    downstream_impact_resolved_refs: tuple[str, ...] = ()
    verification_test_refs: tuple[str, ...] = ()
    replay_or_cancel_capability: str = "UNKNOWN"
    verification_state: str = "UNKNOWN"
    contradicted: bool = False
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectEnvelopeInstruction:
    envelope_ref: str
    bound_ref: str
    bound_provenance_ref: str
    principal_ref: str
    canonical_operation: str
    target_key: str
    target_id: str
    property_name: str
    direction: str
    expected_limit: Any
    observed_delta: Any
    transition_ref: str
    authority_established: bool
    evidence_refs: tuple[str, ...]
    exact_target_identity: bool = True
    property_comparable: bool = True
    transition_bound: bool = True
    envelope_version: str | None = None
    envelope_digest: str | None = None


@dataclass(frozen=True)
class SourceContradictionInstruction:
    subject_refs: tuple[str, ...]
    claim_scope: str
    left_value_digest: str | None
    right_value_digest: str | None
    left_evidence_refs: tuple[str, ...]
    right_evidence_refs: tuple[str, ...]
    left_lineage_family: str | None
    right_lineage_family: str | None
    exact_subject_binding: bool = True
    same_property: bool = True


@dataclass(frozen=True)
class StateBindingInstruction:
    action_group_ref: str
    transition_ref: str
    evidence_refs: tuple[str, ...]
    lineage_families: tuple[str, ...] = ()
    target_identity_state: str = "EXACT"


def _artifact_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _qualification_binding(action_group: Mapping[str, Any]) -> str:
    return "EXACT" if (action_group.get("actionIdentity") or {}).get("identityState") == "EXACT" else "PARTIAL"


def _qualify_cell(
    cell: Mapping[str, Any],
    *,
    claim_class: str,
    action_group: Mapping[str, Any],
    event_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    analysis_run_id: str,
    ordinal_start: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    refs = [str(x) for x in cell.get("evidenceRefs", [])]
    by_source: dict[str, list[str]] = {}
    for ref in refs:
        event = event_by_id.get(ref)
        if event and event.get("sourceRef"):
            by_source.setdefault(str(event["sourceRef"]), []).append(ref)

    qualifications: list[dict[str, Any]] = []
    ordinal = ordinal_start
    for source_ref, source_event_refs in sorted(by_source.items()):
        descriptor = source_by_id.get(source_ref)
        if descriptor is None:
            continue
        qualifications.append(
            qualify_source(
                descriptor,
                claim_class=claim_class,
                analysis_run_id=analysis_run_id,
                qualification_id=f"{analysis_run_id}:qualification:{ordinal}",
                subject_binding=_qualification_binding(action_group),
                evidence_refs=source_event_refs,
            )
        )
        ordinal += 1

    original_state = str(cell.get("state", "UNKNOWN"))
    decisions = {q["decision"] for q in qualifications}
    limitations = list(cell.get("limitations", []))
    if original_state in {"UNKNOWN", "MISSING", "NOT_APPLICABLE"} or "CAN_ESTABLISH" in decisions:
        state = original_state
    elif "CAN_SUPPORT" in decisions:
        state = "PARTIAL"
        limitations.append("SOURCE_CAN_SUPPORT_BUT_NOT_ESTABLISH_CLAIM")
    else:
        state = "UNKNOWN"
        limitations.append("NO_SOURCE_QUALIFIED_TO_ESTABLISH_CLAIM")

    return {
        "state": state,
        "evidenceRefs": refs,
        "gapRefs": list(cell.get("gapRefs", [])),
        "limitations": sorted(set(limitations)),
    }, qualifications, ordinal


def _gate_lifecycle(
    lifecycle: Mapping[str, Any],
    *,
    action_group: Mapping[str, Any],
    event_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    analysis_run_id: str,
    ordinal_start: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    mapping = {
        "actionRequested": "ACTION_REQUESTED",
        "actionAuthorized": "ACTION_AUTHORIZED",
        "actionAccepted": "ACTION_ACCEPTED",
        "actionApplied": "ACTION_APPLIED",
        "actionConfirmed": "ACTION_CONFIRMED",
    }
    out = dict(lifecycle)
    qualifications: list[dict[str, Any]] = []
    ordinal = ordinal_start
    for key, claim_class in mapping.items():
        gated, rows, ordinal = _qualify_cell(
            lifecycle[key],
            claim_class=claim_class,
            action_group=action_group,
            event_by_id=event_by_id,
            source_by_id=source_by_id,
            analysis_run_id=analysis_run_id,
            ordinal_start=ordinal,
        )
        out[key] = gated
        qualifications.extend(rows)
    return out, qualifications, ordinal


def _gate_five_plane(
    five_plane: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, Any],
    action_group: Mapping[str, Any],
    event_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    analysis_run_id: str,
    ordinal_start: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    out = dict(five_plane)
    qualifications: list[dict[str, Any]] = []
    ordinal = ordinal_start

    grant, rows, ordinal = _qualify_cell(
        five_plane["effectivelyGranted"],
        claim_class="EFFECTIVE_GRANT",
        action_group=action_group,
        event_by_id=event_by_id,
        source_by_id=source_by_id,
        analysis_run_id=analysis_run_id,
        ordinal_start=ordinal,
    )
    out["effectivelyGranted"] = grant
    qualifications.extend(rows)

    applied_state = lifecycle["actionApplied"]["state"]
    confirmed_state = lifecycle["actionConfirmed"]["state"]
    if "PRESENT" in {applied_state, confirmed_state}:
        observed_state = "PRESENT"
    elif "PARTIAL" in {applied_state, confirmed_state}:
        observed_state = "PARTIAL"
    else:
        observed_state = "UNKNOWN"
    observed = dict(five_plane["observed"])
    observed["state"] = observed_state
    if observed_state != "PRESENT" and observed.get("evidenceRefs"):
        observed["limitations"] = sorted(
            set(observed.get("limitations", [])) | {"OBSERVED_EVIDENCE_NOT_QUALIFIED_TO_ESTABLISH_EFFECT"}
        )
    out["observed"] = observed
    return out, qualifications, ordinal


def analyze_artifacts(
    artifacts: Sequence[ArtifactEvidence],
    *,
    case_id: str,
    evidence_set_id: str,
    analysis_run_id: str,
    created_at: str,
    expected_source_roles: Sequence[str] = (),
    state_bindings: Sequence[StateBindingInstruction] = (),
    approved_mappings: Mapping[str, MappingProfileEntry] | None = None,
    cause_instructions: Sequence[CauseEvaluationInstruction] = (),
    source_contradiction_instructions: Sequence[SourceContradictionInstruction] = (),
    effect_envelope_instructions: Sequence[EffectEnvelopeInstruction] = (),
    delegated_action_integrity_instructions: Sequence[DelegatedActionIntegrityInstruction] = (),
    context_lineage_instructions: Sequence[ContextLineageInstruction] = (),
    guardrail_mediation_instructions: Sequence[GuardrailMediationInstruction] = (),
    recovery_instructions: Sequence[RecoveryInstruction] = (),
    otlp_traces: Sequence[OtlpTraceEvidence] = (),
    otlp_logs: Sequence[OtlpLogEvidence] = (),
    otlp_metrics: Sequence[OtlpMetricEvidence] = (),
) -> dict[str, Any]:
    """Run a deterministic evidence-to-snapshot analysis spine.

    The spine composes existing canonical owners. Unknown fingerprints are
    preserved/profiled and may emit conservative schema-compatible mapping
    proposals, but never force-map. A runtime mapping is usable only when the
    caller explicitly supplies an approved mapping entry bound to the current
    artifact fingerprint and one of the proposals emitted for the current
    schema. State-to-action binding requires explicit binding evidence.
    Cause-rule selection is intentionally not automated in this slice.
    """
    syntax_registry = load_default_registry()
    mapping_registry = load_default_mapping_registry()
    semantic_registry = load_event_semantic_registry()
    descriptor_projector = SourceDescriptorProjector(
        semantic_registry=semantic_registry,
        adapter_registry=syntax_registry,
    )

    artifact_results: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []
    source_descriptors: list[dict[str, Any]] = []
    canonical_events: list[dict[str, Any]] = []
    unresolved_artifacts: list[dict[str, Any]] = []
    mapping_proposals: list[dict[str, Any]] = []
    approved_mappings = approved_mappings or {}
    record_count = parsed_count = failed_count = 0
    # Operator-accessible OTLP seam: a committed artifact whose bytes decode
    # as a standard OTLP JSON export envelope is additionally interpreted by
    # the typed OTLP parsers below. Generic artifact handling is unchanged --
    # the same raw bytes still flow through the artifact path with their
    # digest/provenance; typed OTLP parsing is an additional deterministic
    # interpretation, never a replacement for the preserved artifact.
    seen_otlp_fingerprints = {
        (signal, _artifact_sha256(evidence.content))
        for signal, evidence in (
            [("TRACES", e) for e in otlp_traces]
            + [("LOGS", e) for e in otlp_logs]
            + [("METRICS", e) for e in otlp_metrics]
        )
    }
    typed_otlp_traces = list(otlp_traces)
    typed_otlp_logs = list(otlp_logs)
    typed_otlp_metrics = list(otlp_metrics)
    for artifact in artifacts:
        digest = _artifact_sha256(artifact.content)
        for signal in detect_otlp_envelope_signals(artifact.content):
            if (signal, digest) in seen_otlp_fingerprints:
                continue
            if signal == "TRACES":
                typed_otlp_traces.append(
                    OtlpTraceEvidence(
                        artifact_ref=artifact.artifact_id,
                        source_ref=artifact.path,
                        content=artifact.content,
                    )
                )
            elif signal == "LOGS":
                typed_otlp_logs.append(
                    OtlpLogEvidence(
                        artifact_ref=artifact.artifact_id,
                        source_ref=artifact.path,
                        content=artifact.content,
                    )
                )
            else:
                typed_otlp_metrics.append(
                    OtlpMetricEvidence(
                        artifact_ref=artifact.artifact_id,
                        source_ref=artifact.path,
                        content=artifact.content,
                    )
                )

    otlp_results: list[dict[str, Any]] = []
    otlp_parse_failures: list[dict[str, Any]] = []
    trace_path_edges: list[dict[str, Any]] = []
    trace_path_unresolved: list[dict[str, Any]] = []
    trace_path_rejected: list[dict[str, Any]] = []
    otlp_relation_evaluations: list[dict[str, Any]] = []
    otlp_source_refs: set[str] = set()
    otlp_limitations: set[str] = set()

    for trace_evidence in typed_otlp_traces:
        parsed = parse_otlp_trace_payload(
            trace_evidence.content,
            artifact_ref=trace_evidence.artifact_ref,
            source_ref=trace_evidence.source_ref,
            otlp_spec_version=trace_evidence.otlp_spec_version,
            semantic_conventions_version=trace_evidence.semantic_conventions_version,
        )
        paths = reconstruct_trace_paths(parsed.spans, analysis_run_id=analysis_run_id)
        otlp_source_refs.add(trace_evidence.source_ref)
        otlp_parse_failures.extend(parsed.parse_failures)
        otlp_limitations.update(parsed.limitations)
        otlp_limitations.update(paths.limitations)
        trace_path_edges.extend(paths.edges)
        trace_path_unresolved.extend(paths.unresolved_parent_refs)
        trace_path_rejected.extend(paths.rejected_refs)
        otlp_relation_evaluations.extend(paths.relation_evaluations)
        otlp_results.append({
            "artifactRef": trace_evidence.artifact_ref,
            "sourceRef": trace_evidence.source_ref,
            "provenance": parsed.provenance,
            "spanCount": len(parsed.spans),
            "pathEdgeCount": len(paths.edges),
            "relationCount": len(paths.relation_evaluations),
            "parseFailureCount": len(parsed.parse_failures),
            "limitations": sorted(set(parsed.limitations) | set(paths.limitations)),
        })

    otlp_log_results: list[dict[str, Any]] = []
    for log_evidence in typed_otlp_logs:
        parsed_logs = parse_otlp_logs_payload(
            log_evidence.content,
            artifact_ref=log_evidence.artifact_ref,
            source_ref=log_evidence.source_ref,
            otlp_spec_version=log_evidence.otlp_spec_version,
            semantic_conventions_version=log_evidence.semantic_conventions_version,
        )
        otlp_source_refs.add(log_evidence.source_ref)
        otlp_parse_failures.extend(parsed_logs.parse_failures)
        otlp_limitations.update(parsed_logs.limitations)
        otlp_log_results.append({
            "artifactRef": log_evidence.artifact_ref,
            "sourceRef": log_evidence.source_ref,
            "provenance": parsed_logs.provenance,
            "logRecordCount": len(parsed_logs.log_records),
            "logRecords": list(parsed_logs.log_records),
            "parseFailureCount": len(parsed_logs.parse_failures),
            "limitations": sorted(set(parsed_logs.limitations)),
        })

    otlp_metric_results: list[dict[str, Any]] = []
    for metric_evidence in typed_otlp_metrics:
        parsed_metrics = parse_otlp_metrics_payload(
            metric_evidence.content,
            artifact_ref=metric_evidence.artifact_ref,
            source_ref=metric_evidence.source_ref,
            otlp_spec_version=metric_evidence.otlp_spec_version,
            semantic_conventions_version=metric_evidence.semantic_conventions_version,
        )
        otlp_source_refs.add(metric_evidence.source_ref)
        otlp_parse_failures.extend(parsed_metrics.parse_failures)
        otlp_limitations.update(parsed_metrics.limitations)
        otlp_metric_results.append({
            "artifactRef": metric_evidence.artifact_ref,
            "sourceRef": metric_evidence.source_ref,
            "provenance": parsed_metrics.provenance,
            "metricCount": len(parsed_metrics.metrics),
            "metrics": list(parsed_metrics.metrics),
            "parseFailureCount": len(parsed_metrics.parse_failures),
            "limitations": sorted(set(parsed_metrics.limitations)),
        })

    for artifact in artifacts:
        selection = syntax_registry.select(artifact.path, artifact.media_type)
        format_name = selection.adapter.formats[0] if selection.adapter.formats else "opaque"
        digest = _artifact_sha256(artifact.content)
        profile = profile_artifact(
            artifact_id=artifact.artifact_id,
            format_name=format_name,
            content=artifact.content,
            file_name=artifact.path,
        )
        record_count += int(profile["recordCount"])
        parsed_count += int(profile["parsedRecordCount"])
        failed_count += int(profile["failedRecordCount"])
        parse_failures.extend(profile["parseFailures"])

        mapping = mapping_registry.resolve_exact(
            artifact_sha256=digest,
            syntax_adapter_id=selection.adapter.adapter_id,
        )
        event_count = 0
        semantic_profile_ids: tuple[str, ...] = ()
        limitations = list(selection.limitations)
        proposals: tuple[MappingProposal, ...] = ()

        if mapping is None:
            semantic_selection = semantic_registry.select(
                syntax_adapter_id=selection.adapter.adapter_id,
                schema_profile=profile["schemaProfile"],
                file_name=artifact.path,
            )
            semantic_profile_ids = semantic_selection.profile_ids
            limitations.extend(semantic_selection.limitations)
            proposals = propose_schema_compatible_mappings(
                mapping_registry,
                schema_profile=profile["schemaProfile"],
                syntax_adapter_id=selection.adapter.adapter_id,
                semantic_profile_ids=semantic_selection.profile_ids,
            )
            for proposal in proposals:
                mapping_proposals.append({
                    "artifactId": artifact.artifact_id,
                    "path": artifact.path,
                    "sha256": digest,
                    **proposal.to_dict(),
                })

            approved = approved_mappings.get(artifact.artifact_id)
            if approved is not None:
                if (
                    approved.artifact_sha256 == digest
                    and approved.syntax_adapter_id == selection.adapter.adapter_id
                    and approved_mapping_matches_proposals(approved, proposals)
                ):
                    mapping = approved
                    limitations.append("EXPLICIT_RUNTIME_MAPPING_APPROVED")
                else:
                    limitations.append("APPROVED_MAPPING_REJECTED_CURRENT_SCHEMA_MISMATCH")

        if mapping is None:
            unresolved_artifacts.append({
                "artifactId": artifact.artifact_id,
                "path": artifact.path,
                "sha256": digest,
                "reason": "NO_APPROVED_MAPPING",
                "proposalIds": [proposal.proposal_id for proposal in proposals],
            })
            limitations.append("NO_APPROVED_MAPPING")
        else:
            semantic_profile_ids = mapping.semantic_profile_ids
            projected_sources = descriptor_projector.project(
                artifact_id=artifact.artifact_id,
                artifact_path=artifact.path,
                syntax_adapter_id=selection.adapter.adapter_id,
                semantic_profile_ids=semantic_profile_ids,
                integrity_state="VERIFIED",
                completeness_state=artifact.completeness_state,
                currentness=artifact.currentness,
                environment=artifact.environment,
                producer=artifact.producer,
            )
            source_descriptors.extend(projected_sources.descriptors)
            events = project_canonical_events(
                artifact_id=artifact.artifact_id,
                artifact_path=artifact.path,
                artifact_sha256=digest,
                format_name=format_name,
                syntax_adapter_id=selection.adapter.adapter_id,
                content=artifact.content,
                ingested_at=artifact.ingested_at,
                mapping_registry=mapping_registry,
                semantic_registry=semantic_registry,
                mapping_entry=mapping,
            )
            canonical_events.extend(events.events)
            event_count = len(events.events)
            limitations.extend(events.limitations)

        artifact_results.append({
            "artifactId": artifact.artifact_id,
            "path": artifact.path,
            "sha256": digest,
            "syntaxAdapterId": selection.adapter.adapter_id,
            "format": format_name,
            "profileState": profile["state"],
            "schemaProfileRef": profile["schemaProfile"]["profileId"] if format_name != "opaque" else None,
            "semanticProfileIds": list(semantic_profile_ids),
            "recordCount": profile["recordCount"],
            "parsedRecordCount": profile["parsedRecordCount"],
            "failedRecordCount": profile["failedRecordCount"],
            "canonicalEventCount": event_count,
            "limitations": sorted(set(limitations)),
        })

    event_by_id = {str(event["eventId"]): event for event in canonical_events}
    source_by_id = {str(source["sourceId"]): source for source in source_descriptors}

    temporal_normalizations: list[dict[str, Any]] = []
    timeline_events: list[dict[str, Any]] = []
    for index, event in enumerate(sorted(canonical_events, key=lambda x: str(x["eventId"])), start=1):
        normalization = normalize_event_time(
            event,
            analysis_run_id=analysis_run_id,
            normalization_id=f"{analysis_run_id}:time:{index}",
            clock_domain_ref=event.get("clockDomainRef"),
        )
        temporal_normalizations.append(normalization)
        timeline_events.append(
            timeline_event(
                event,
                normalization,
                analysis_run_id=analysis_run_id,
                timeline_event_id=f"{analysis_run_id}:timeline:{index}",
            )
        )

    independence = assess_source_independence(canonical_events, source_by_id)
    action_result = assemble_action_groups(
        canonical_events,
        case_id=case_id,
        evidence_set_id=evidence_set_id,
        analysis_run_id=analysis_run_id,
    )

    transition_projection = reconstruct_state_transitions(
        canonical_events,
        analysis_run_id=analysis_run_id,
    )
    transition_by_id = {str(x["transitionId"]): dict(x) for x in transition_projection.transitions}
    action_by_id = {str(x["actionGroupId"]): x for x in action_result.action_groups}
    relation_evaluations: list[dict[str, Any]] = list(otlp_relation_evaluations)
    confirmed_by_action: dict[str, list[str]] = {}

    for index, binding in enumerate(state_bindings, start=1):
        action = action_by_id.get(binding.action_group_ref)
        transition = transition_by_id.get(binding.transition_ref)
        if action is None or transition is None:
            continue
        relation = evaluate_changes_binding(
            evaluation_id=f"{analysis_run_id}:relation:changes:{index}",
            analysis_run_id=analysis_run_id,
            action_group=action,
            transition=transition,
            target_identity_state=binding.target_identity_state,
            binding_evidence_refs=binding.evidence_refs,
            lineage_families=binding.lineage_families,
        )
        relation_evaluations.append(relation.evaluation)
        if relation.evaluation["decision"] == "ESTABLISHED":
            transition_by_id[binding.transition_ref] = bind_transition(
                transition,
                relation.evaluation,
                operation_event_refs=action.get("eventRefs", []),
            )
            confirmed_by_action.setdefault(binding.action_group_ref, []).extend(
                transition.get("evidenceRefs", [])
            )

    lifecycle_rows: list[dict[str, Any]] = []
    five_plane_rows: list[dict[str, Any]] = []
    qualification_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    contradiction_rows: list[dict[str, Any]] = []
    lifecycle_by_action: dict[str, dict[str, Any]] = {}
    qualification_ordinal = 1

    for index, action in enumerate(action_result.action_groups, start=1):
        raw_lifecycle = evaluate_action_lifecycle(
            action,
            canonical_events,
            coverage_id=f"{analysis_run_id}:lifecycle:{index}",
            confirmed_evidence_refs=sorted(set(confirmed_by_action.get(str(action["actionGroupId"]), []))),
        )
        lifecycle, qualifications, qualification_ordinal = _gate_lifecycle(
            raw_lifecycle,
            action_group=action,
            event_by_id=event_by_id,
            source_by_id=source_by_id,
            analysis_run_id=analysis_run_id,
            ordinal_start=qualification_ordinal,
        )
        qualification_rows.extend(qualifications)
        lifecycle_rows.append(lifecycle)
        lifecycle_by_action[str(action["actionGroupId"])] = lifecycle

        raw_five = evaluate_five_plane_coverage(
            action,
            lifecycle,
            canonical_events,
            coverage_id=f"{analysis_run_id}:five-plane:{index}",
        )
        five, qualifications, qualification_ordinal = _gate_five_plane(
            raw_five,
            lifecycle=lifecycle,
            action_group=action,
            event_by_id=event_by_id,
            source_by_id=source_by_id,
            analysis_run_id=analysis_run_id,
            ordinal_start=qualification_ordinal,
        )
        qualification_rows.extend(qualifications)
        five_plane_rows.append(five)

        gap_rows.extend(
            coverage_gaps(
                action_group_ref=str(action["actionGroupId"]),
                evidence_set_id=evidence_set_id,
                subject_refs=[
                    x for x in [
                        (action.get("actionIdentity") or {}).get("actorRef"),
                        (action.get("actionIdentity") or {}).get("targetRef"),
                    ] if x
                ],
                lifecycle=lifecycle,
                five_plane=five,
            )
        )
        contradiction = action_status_contradiction(
            contradiction_id=f"{analysis_run_id}:contradiction:{index}",
            analysis_run_id=analysis_run_id,
            subject_refs=[
                x for x in [
                    (action.get("actionIdentity") or {}).get("actorRef"),
                    (action.get("actionIdentity") or {}).get("targetRef"),
                ] if x
            ],
            action_group_ref=str(action["actionGroupId"]),
            lifecycle=lifecycle,
        )
        if contradiction is not None:
            contradiction_rows.append(contradiction)

    for index, sc in enumerate(source_contradiction_instructions, start=1):
        contradiction = source_authority_contradiction(
            contradiction_id=f"{analysis_run_id}:source-contradiction:{index}",
            analysis_run_id=analysis_run_id,
            subject_refs=sc.subject_refs,
            claim_scope=sc.claim_scope,
            left_value_digest=sc.left_value_digest,
            right_value_digest=sc.right_value_digest,
            left_evidence_refs=sc.left_evidence_refs,
            right_evidence_refs=sc.right_evidence_refs,
            left_lineage_family=sc.left_lineage_family,
            right_lineage_family=sc.right_lineage_family,
            exact_subject_binding=sc.exact_subject_binding,
            same_property=sc.same_property,
        )
        if contradiction is not None:
            contradiction_rows.append(contradiction)

    effect_envelope_rows: list[dict[str, Any]] = []
    for index, ee in enumerate(effect_envelope_instructions, start=1):
        effect_envelope_rows.append(
            assess_effect_envelope(
                assessment_id=f"{analysis_run_id}:effect-envelope:{index}",
                envelope_ref=ee.envelope_ref,
                bound_ref=ee.bound_ref,
                bound_provenance_ref=ee.bound_provenance_ref,
                principal_ref=ee.principal_ref,
                canonical_operation=ee.canonical_operation,
                target_key=ee.target_key,
                target_id=ee.target_id,
                property_name=ee.property_name,
                direction=ee.direction,
                expected_limit=ee.expected_limit,
                observed_delta=ee.observed_delta,
                transition_ref=ee.transition_ref,
                authority_established=ee.authority_established,
                evidence_refs=ee.evidence_refs,
                exact_target_identity=ee.exact_target_identity,
                property_comparable=ee.property_comparable,
                transition_bound=ee.transition_bound,
                envelope_version=ee.envelope_version,
                envelope_digest=ee.envelope_digest,
            )
        )

    delegated_action_integrity_rows: list[dict[str, Any]] = []
    for index, dai in enumerate(delegated_action_integrity_instructions, start=1):
        delegated_action_integrity_rows.append(
            evaluate_delegated_action_integrity(
                evaluation_id=f"{analysis_run_id}:dai:{index}",
                action_group_ref=dai.action_group_ref,
                dimensions=dai.dimensions,
                evidence_refs=dai.evidence_refs,
                limitations=dai.limitations,
            )
        )

    context_lineage_rows: list[dict[str, Any]] = []
    for cli in context_lineage_instructions:
        context_lineage_rows.append(
            project_context_lineage_item(
                context_item_ref=cli.context_item_ref,
                origin=cli.origin,
                source_authority=cli.source_authority,
                mutability=cli.mutability,
                validation_state=cli.validation_state,
                integrity_state=cli.integrity_state,
                temporal_basis=cli.temporal_basis,
                model_visible=cli.model_visible,
                explicitly_referenced=cli.explicitly_referenced,
                retrieved_at=cli.retrieved_at,
                evidence_refs=cli.evidence_refs,
                influence_evidence_refs=cli.influence_evidence_refs,
                limitations=cli.limitations,
            )
        )

    guardrail_mediation_rows: list[dict[str, Any]] = []
    for index, gm in enumerate(guardrail_mediation_instructions, start=1):
        guardrail_mediation_rows.append(
            assess_guardrail_mediation(
                mediation_id=f"{analysis_run_id}:mediation:{index}",
                action_group_ref=gm.action_group_ref,
                guardrail_ref=gm.guardrail_ref,
                requirement_declared=gm.requirement_declared,
                confirmation_presented=gm.confirmation_presented,
                confirmation_completed=gm.confirmation_completed,
                decision=gm.decision,
                decision_time_ref=gm.decision_time_ref,
                action_time_ref=gm.action_time_ref,
                decision_time=gm.decision_time,
                action_time=gm.action_time,
                deny_branch_blocked_action=gm.deny_branch_blocked_action,
                approved_argument_digest=gm.approved_argument_digest,
                executed_argument_digest=gm.executed_argument_digest,
                mediation_evidence_refs=gm.mediation_evidence_refs,
                limitations=gm.limitations,
            )
        )

    recovery_rows: list[dict[str, Any]] = []
    for index, rec in enumerate(recovery_instructions, start=1):
        recovery_rows.append(
            assess_recovery_projection(
                recovery_id=f"{analysis_run_id}:recovery:{index}",
                incident_snapshot_ref=rec.incident_snapshot_ref,
                recovery_action_refs=rec.recovery_action_refs,
                rollback_requested_refs=rec.rollback_requested_refs,
                rollback_completed_refs=rec.rollback_completed_refs,
                state_restored_refs=rec.state_restored_refs,
                service_health_restored_refs=rec.service_health_restored_refs,
                downstream_impact_resolved_refs=rec.downstream_impact_resolved_refs,
                verification_test_refs=rec.verification_test_refs,
                replay_or_cancel_capability=rec.replay_or_cancel_capability,
                verification_state=rec.verification_state,
                contradicted=rec.contradicted,
                evidence_refs=rec.evidence_refs,
                limitations=rec.limitations,
            )
        )

    cause_rows: list[dict[str, Any]] = []
    for index, ci in enumerate(cause_instructions, start=1):
        cause_action = action_by_id.get(ci.action_group_ref)
        cause_lifecycle = lifecycle_by_action.get(ci.action_group_ref)
        if cause_action is None or cause_lifecycle is None:
            raise ValueError(
                f"cause instruction references unknown action group: {ci.action_group_ref}"
            )
        cause_rows.append(
            evaluate_cause_instruction(
                ci,
                action_group=cause_action,
                lifecycle=cause_lifecycle,
                analysis_run_id=analysis_run_id,
                evaluation_id=f"{analysis_run_id}:cause:{index}",
            )
        )

    source_roles = [str(x.get("sourceKind")) for x in source_descriptors if x.get("sourceKind")]
    event_times = sorted(str(x["eventTime"]) for x in canonical_events if x.get("eventTime"))
    coverage = source_coverage_profile(
        coverage_profile_id=f"{analysis_run_id}:source-coverage",
        evidence_set_id=evidence_set_id,
        observed_source_roles=source_roles,
        expected_source_roles=expected_source_roles,
        artifact_count=len(artifacts),
        record_count=record_count,
        parsed_record_count=parsed_count,
        failed_record_count=failed_count,
        time_start=event_times[0] if event_times else None,
        time_end=event_times[-1] if event_times else None,
        completeness_proven=False,
        unsupported_artifact_refs=[x["artifactId"] for x in unresolved_artifacts],
    )

    entity_refs = sorted({
        str(ref)
        for event in canonical_events
        for ref in list(event.get("actorRefs", [])) + list(event.get("targetRefs", []))
    })
    correlation_refs = sorted({
        str(ref)
        for action in action_result.action_groups
        for ref in action.get("correlationGroupRefs", [])
    })
    snapshot_limitations = {
        "CAUSE_RULE_SELECTION_REQUIRES_EXPLICIT_PREDICATE_FACTS",
        "SOURCE_QUALIFICATION_IS_CLAIM_SCOPED",
    }
    if unresolved_artifacts:
        snapshot_limitations.add("UNPROJECTED_EVIDENCE_PRESENT")
    if action_result.ungrouped_event_refs:
        snapshot_limitations.add("UNGROUPED_EVENTS_PRESENT")
    if independence.limitations:
        snapshot_limitations.update(independence.limitations)
    if otlp_traces:
        snapshot_limitations.add("OTLP_TELEMETRY_NOT_INCLUDED_IN_STANDARD_SOURCE_COVERAGE")
    if otlp_logs:
        snapshot_limitations.add("OTLP_LOG_TELEMETRY_NOT_INCLUDED_IN_STANDARD_SOURCE_COVERAGE")
    if otlp_metrics:
        snapshot_limitations.add("OTLP_METRIC_TELEMETRY_NOT_INCLUDED_IN_STANDARD_SOURCE_COVERAGE")
    if otlp_traces or otlp_logs or otlp_metrics:
        snapshot_limitations.update(otlp_limitations)
    analysis_limitations = set(snapshot_limitations)
    if cause_rows:
        analysis_limitations.add("CAUSE_EVALUATIONS_CALLER_BOUNDED")
    if effect_envelope_rows:
        analysis_limitations.add("EFFECT_ENVELOPE_ASSESSMENTS_CALLER_BOUNDED")
    if delegated_action_integrity_rows:
        analysis_limitations.add("DELEGATED_ACTION_INTEGRITY_PROJECTIONS_CALLER_BOUNDED")
    if context_lineage_rows:
        analysis_limitations.add("CONTEXT_LINEAGE_PROJECTIONS_CALLER_BOUNDED")
    if guardrail_mediation_rows:
        analysis_limitations.add("GUARDRAIL_MEDIATION_PROJECTIONS_CALLER_BOUNDED")
    if recovery_rows:
        analysis_limitations.add("RECOVERY_PROJECTIONS_CALLER_BOUNDED")

    evidence_frontier_rows = project_frontiers_from_gaps(
        gap_rows,
        created_from_snapshot=f"{case_id}:snapshot:{evidence_set_id}:{analysis_run_id}",
    )

    snapshot = build_investigation_snapshot(
        case_id=case_id,
        evidence_set_id=evidence_set_id,
        analysis_run_id=analysis_run_id,
        created_at=created_at,
        entity_refs=entity_refs,
        event_refs=[str(x["eventId"]) for x in canonical_events],
        source_refs=sorted({str(x["sourceId"]) for x in source_descriptors} | otlp_source_refs),
        correlation_group_refs=correlation_refs,
        action_group_refs=[str(x["actionGroupId"]) for x in action_result.action_groups],
        relation_evaluation_refs=[str(x["evaluationId"]) for x in relation_evaluations],
        state_transition_refs=[str(x["transitionId"]) for x in transition_by_id.values()],
        contradiction_refs=[str(x["contradictionId"]) for x in contradiction_rows],
        divergence_refs=[],
        timeline_event_refs=[str(x["timelineEventId"]) for x in timeline_events],
        five_plane_coverage_refs=[str(x["coverageId"]) for x in five_plane_rows],
        action_lifecycle_coverage_refs=[str(x["coverageId"]) for x in lifecycle_rows],
        gap_refs=[str(x["gapId"]) for x in gap_rows],
        duplicate_group_refs=[],
        limitations=sorted(snapshot_limitations),
    )

    investigation_story_rows = project_investigation_stories(
        analysis_run_id=analysis_run_id,
        snapshot_ref=str(snapshot["snapshotId"]),
        effect_envelopes=effect_envelope_rows,
        delegated_action_integrity=delegated_action_integrity_rows,
        guardrail_mediations=guardrail_mediation_rows,
        recovery_projections=recovery_rows,
        contradictions=contradiction_rows,
        evidence_frontiers=evidence_frontier_rows,
    )

    return {
        "caseId": case_id,
        "evidenceSetId": evidence_set_id,
        "analysisRunId": analysis_run_id,
        "artifactResults": artifact_results,
        "parseFailures": parse_failures,
        "unresolvedArtifacts": unresolved_artifacts,
        "mappingProposals": mapping_proposals,
        "sourceDescriptors": source_descriptors,
        "otlpTelemetry": otlp_results,
        "otlpLogTelemetry": otlp_log_results,
        "otlpMetricTelemetry": otlp_metric_results,
        "otlpParseFailures": otlp_parse_failures,
        "tracePathEdges": trace_path_edges,
        "tracePathUnresolved": trace_path_unresolved,
        "tracePathRejected": trace_path_rejected,
        "sourceCoverage": coverage,
        "canonicalEvents": canonical_events,
        "temporalNormalizations": temporal_normalizations,
        "timelineEvents": timeline_events,
        "sourceIndependence": {
            "independentLineageCount": independence.independent_lineage_count,
            "lineageByEvent": independence.lineage_by_event,
            "duplicateGroups": [list(x) for x in independence.duplicate_groups],
            "limitations": list(independence.limitations),
        },
        "actionGroups": list(action_result.action_groups),
        "ungroupedEventRefs": list(action_result.ungrouped_event_refs),
        "rejectedJoinRefs": list(action_result.rejected_join_refs),
        "sourceQualifications": qualification_rows,
        "stateTransitions": list(transition_by_id.values()),
        "relationEvaluations": relation_evaluations,
        "actionLifecycleCoverage": lifecycle_rows,
        "fivePlaneCoverage": five_plane_rows,
        "gaps": gap_rows,
        "evidenceFrontier": list(evidence_frontier_rows),
        "investigationStories": list(investigation_story_rows),
        "contradictions": contradiction_rows,
        "causeEvaluations": cause_rows,
        "effectEnvelopeAssessments": effect_envelope_rows,
        "delegatedActionIntegrity": delegated_action_integrity_rows,
        "contextLineage": context_lineage_rows,
        "guardrailMediations": guardrail_mediation_rows,
        "recoveryProjections": recovery_rows,
        "snapshot": snapshot,
        "limitations": sorted(analysis_limitations),
    }
