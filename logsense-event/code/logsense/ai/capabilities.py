from __future__ import annotations

from copy import deepcopy
from typing import Any

_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {"name": "get_claim", "argument": "claim_id", "source": "forensicClaims"},
    {"name": "get_evidence_card", "argument": "claim_id", "source": "evidenceCards"},
    {"name": "get_session", "argument": None, "source": "investigationSession"},
    {"name": "get_execution_archetype", "argument": "ref", "source": "executionArchetypes"},
    {
        "name": "get_delegated_action_integrity",
        "argument": "ref",
        "source": "delegatedActionIntegrity",
    },
    {"name": "get_effect_envelope", "argument": "ref", "source": "effectEnvelopeAssessments"},
    {"name": "get_guardrail_mediation", "argument": "ref", "source": "guardrailMediation"},
    {"name": "get_material_stories", "argument": None, "source": "investigationStories"},
    {"name": "get_investigation_insights", "argument": None, "source": "investigationInsights"},
    {"name": "get_trust_break_candidates", "argument": None, "source": "trustBreakCandidates"},
    {"name": "get_recovery_projection", "argument": "ref", "source": "recoveryProjections"},
    {"name": "get_comparison_perimeter", "argument": None, "source": "analysisPerimeter"},
    {
        "name": "get_adapter_qualification",
        "argument": "adapter_id",
        "source": "adapterQualifications",
    },
    {"name": "propose_next_evidence", "argument": "frontier_id", "source": "evidenceFrontier"},
    {"name": "get_competition_run", "argument": "run_id", "source": "competitionRuns"},
    {
        "name": "get_control7_event_measurement",
        "argument": "run_id",
        "source": "control7Measurements",
    },
    {"name": "get_competition_evidence_bundle", "argument": None, "source": "competitionBundle"},
    {
        "name": "get_control9_drift_measurement",
        "argument": "run_id",
        "source": "control9Measurements",
    },
    {
        "name": "get_control16_usage_measurement",
        "argument": "run_id",
        "source": "control16Measurements",
    },
    {"name": "get_event_readiness", "argument": None, "source": "eventReadiness"},
    {"name": "get_event_guidance", "argument": "topic", "source": "eventGuidance"},
    {"name": "get_forensic_window", "argument": "run_id", "source": "timelineEvents"},
    {
        "name": "get_imported_haiec_control_test_result",
        "argument": "control_id",
        "source": "importedHaiecProofs",
    },
)


def investigator_capability_manifest() -> dict[str, Any]:
    """Return the frozen provider-neutral Ask LogSense capability boundary."""
    return {
        "manifestVersion": "1.1.0",
        "mode": "READ_ONLY_INVESTIGATOR",
        "canonicalMutationAllowed": False,
        "rawEvidenceExecutionAllowed": False,
        "modelMayEstablishEvidenceState": False,
        "modelMayEstablishCauseState": False,
        "modelMayEstablishRelationState": False,
        "modelMayCloseFrontier": False,
        "citationRequiredForEvidenceBearingAnswer": True,
        "evidenceContentTrust": "UNTRUSTED_DATA",
        "tools": deepcopy(list(_TOOL_SPECS)),
    }


def tool_specs() -> tuple[dict[str, Any], ...]:
    return tuple(deepcopy(item) for item in _TOOL_SPECS)
