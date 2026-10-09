from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from logsense.ai.capabilities import investigator_capability_manifest
from logsense.ai.retrieval import BoundedRetrievalIndex, routing_hint
from logsense.competition.haiec_proof import find_control_test_result
from logsense.presentation.forensic_window import forensic_window_rows
from logsense.presentation.workbench import timeline_rows


class InvestigatorToolError(ValueError):
    """Raised for unsupported or malformed read-only investigator tool calls."""


def _refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key.endswith("Id") or key.endswith("Ref"):
                if child is not None and str(child):
                    refs.add(str(child))
            elif (
                key.endswith("Refs")
                and isinstance(child, Sequence)
                and not isinstance(child, (str, bytes, bytearray))
            ):
                refs.update(str(x) for x in child if x is not None and str(x))
            refs.update(_refs(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            refs.update(_refs(child))
    return refs


def _row_identity(row: Mapping[str, Any]) -> set[str]:
    preferred = (
        "claimId",
        "storyId",
        "insightId",
        "recoveryId",
        "assessmentId",
        "evaluationId",
        "mediationId",
        "candidateId",
        "adapterId",
        "frontierId",
        "actionGroupRef",
    )
    return {str(row[key]) for key in preferred if row.get(key) is not None and str(row.get(key))}


def _tool_result(
    tool: str, payload: Any, *, state: str = "FOUND", limitations: Sequence[str] = ()
) -> dict[str, Any]:
    citations = sorted(_refs(payload)) if payload is not None else []
    return {
        "tool": tool,
        "state": state,
        "payload": deepcopy(payload),
        "citations": citations,
        "limitations": sorted({str(x) for x in limitations if str(x)}),
        "contentTrust": "UNTRUSTED_DATA",
        "canonicalMutationAllowed": False,
    }


class InvestigatorToolbox:
    """Read-only query surface over deterministic LogSense projections.

    Tool results are deep copies. Evidence text, titles, statements, and other
    strings are returned as untrusted data and are never executed as prompts or
    instructions by this layer. `invoke()` also records a per-question audit
    trail so providers may cite only data they actually retrieved.
    """

    def __init__(
        self,
        *,
        analysis: Mapping[str, Any] | None = None,
        report: Mapping[str, Any] | None = None,
        competition: Mapping[str, Any] | None = None,
    ):
        self._analysis = deepcopy(dict(analysis or {}))
        self._report = deepcopy(dict(report or {}))
        self._competition = deepcopy(dict(competition or {}))
        self._audit: list[dict[str, Any]] = []
        self._retrieval = BoundedRetrievalIndex(analysis=self._analysis, report=self._report)

    @property
    def capability_manifest(self) -> dict[str, Any]:
        return investigator_capability_manifest()

    def reset_audit(self) -> None:
        self._audit.clear()

    def audit_results(self) -> list[dict[str, Any]]:
        return deepcopy(self._audit)

    def used_citations(self) -> list[str]:
        refs: set[str] = set()
        for result in self._audit:
            refs.update(str(x) for x in result.get("citations", ()) if str(x))
        return sorted(refs)

    def citation_inventory(self) -> list[str]:
        refs = _refs(self._analysis) | _refs(self._report)
        return sorted(refs)

    def routing_hint(self, question: str, *, top_k: int = 5) -> str:
        """Return non-citable typed routing metadata for provider tool selection."""
        return routing_hint(self._retrieval.search(question, top_k=top_k))

    def _source(self, key: str) -> Any:
        if key in self._report:
            return self._report[key]
        if key in self._analysis:
            return self._analysis[key]
        return self._competition.get(key)

    def _find(self, key: str, value: str) -> Any:
        rows = self._source(key)
        if isinstance(rows, Mapping):
            rows = [rows]
        for row in rows or ():
            if isinstance(row, Mapping) and value in _row_identity(row):
                return row
        return None

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        row = self._find("forensicClaims", claim_id)
        return _tool_result("get_claim", row, state="FOUND" if row is not None else "NOT_FOUND")

    def get_evidence_card(self, claim_id: str) -> dict[str, Any]:
        rows = self._source("evidenceCards") or ()
        row = next(
            (
                item
                for item in rows
                if isinstance(item, Mapping) and str(item.get("claimId")) == claim_id
            ),
            None,
        )
        return _tool_result(
            "get_evidence_card", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_session(self) -> dict[str, Any]:
        row = self._source("investigationSession")
        if row is None:
            sessions = self._source("investigationSessions") or ()
            row = sessions[0] if sessions else None
        return _tool_result("get_session", row, state="FOUND" if row is not None else "NOT_FOUND")

    def get_execution_archetype(self, ref: str) -> dict[str, Any]:
        row = self._find("executionArchetypes", ref)
        return _tool_result(
            "get_execution_archetype", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_delegated_action_integrity(self, ref: str) -> dict[str, Any]:
        row = self._find("delegatedActionIntegrity", ref)
        if row is None:
            row = self._find("delegatedActionIntegrityEvaluations", ref)
        return _tool_result(
            "get_delegated_action_integrity", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_effect_envelope(self, ref: str) -> dict[str, Any]:
        row = self._find("effectEnvelopeAssessments", ref)
        return _tool_result(
            "get_effect_envelope", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_guardrail_mediation(self, ref: str) -> dict[str, Any]:
        row = self._find("guardrailMediation", ref)
        if row is None:
            row = self._find("guardrailMediationProjections", ref)
        return _tool_result(
            "get_guardrail_mediation", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_material_stories(self) -> dict[str, Any]:
        rows = list(self._source("investigationStories") or ())
        return _tool_result("get_material_stories", rows, state="FOUND" if rows else "NOT_FOUND")

    def get_investigation_insights(self) -> dict[str, Any]:
        rows = list(self._source("investigationInsights") or ())
        return _tool_result(
            "get_investigation_insights", rows, state="FOUND" if rows else "NOT_FOUND"
        )

    def get_trust_break_candidates(self) -> dict[str, Any]:
        rows = list(self._source("trustBreakCandidates") or ())
        return _tool_result(
            "get_trust_break_candidates", rows, state="FOUND" if rows else "NOT_FOUND"
        )

    def get_recovery_projection(self, ref: str) -> dict[str, Any]:
        row = self._find("recoveryProjections", ref)
        return _tool_result(
            "get_recovery_projection", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_comparison_perimeter(self) -> dict[str, Any]:
        row = self._source("analysisPerimeter")
        if row is None:
            rows = self._source("analysisPerimeters") or ()
            row = rows[-1] if rows else None
        return _tool_result(
            "get_comparison_perimeter", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def get_adapter_qualification(self, adapter_id: str) -> dict[str, Any]:
        row = self._find("adapterQualifications", adapter_id)
        if row is None:
            row = self._find("adapterQualificationRecords", adapter_id)
        return _tool_result(
            "get_adapter_qualification", row, state="FOUND" if row is not None else "NOT_FOUND"
        )

    def propose_next_evidence(self, frontier_id: str) -> dict[str, Any]:
        frontier = self._find("evidenceFrontier", frontier_id)
        if frontier is None:
            return _tool_result("propose_next_evidence", None, state="NOT_FOUND")
        proposal = {
            "frontierId": frontier.get("frontierId"),
            "subjectRefs": list(frontier.get("subjectRefs") or ()),
            "missingFact": frontier.get("missingFact"),
            "whyNeeded": frontier.get("whyNeeded"),
            "verificationRequirement": frontier.get("verificationRequirement"),
            "proposedTestRef": frontier.get("proposedTestRef"),
            "currentEvidenceRefs": list(frontier.get("currentEvidenceRefs") or ()),
            "state": frontier.get("state"),
            "notClaimed": ["ROOT_CAUSE", "CAPABILITY_ABSENCE", "CANONICAL_MUTATION"],
        }
        return _tool_result(
            "propose_next_evidence",
            proposal,
            limitations=("DETERMINISTIC_FRONTIER_PROJECTION_NOT_LLM_RECOMMENDATION",),
        )

    def get_competition_run(self, run_id: str | None = None) -> dict[str, Any]:
        rows: Any = self._source("competitionRuns") or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        if run_id is not None:
            row = next(
                (item for item in rows if str(item.get("runId")) == str(run_id)),
                None,
            )
        else:
            row = rows[0] if len(rows) == 1 else None
        return _tool_result(
            "get_competition_run",
            row,
            state="FOUND" if row is not None else "NOT_FOUND",
            limitations=("RUN_BINDING_IS_USER_DECLARED",),
        )

    def get_control7_event_measurement(self, run_id: str | None = None) -> dict[str, Any]:
        rows: Any = self._source("control7Measurements") or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        if run_id is not None:
            row = next(
                (item for item in rows if str(item.get("runId")) == str(run_id)),
                None,
            )
        else:
            row = rows[0] if len(rows) == 1 else None
        return _tool_result(
            "get_control7_event_measurement",
            row,
            state="FOUND" if row is not None else "NOT_FOUND",
            limitations=(
                "MEASUREMENT_NOT_GOVERNANCE_VERDICT",
                "MISSING_EVENT_NOT_PROOF_OF_ABSENCE",
            ),
        )

    def get_competition_evidence_bundle(self) -> dict[str, Any]:
        row = self._source("competitionBundle")
        return _tool_result(
            "get_competition_evidence_bundle",
            row,
            state="FOUND" if row is not None else "NOT_FOUND",
        )

    def _measurement_by_run(self, key: str, tool: str, run_id: str | None) -> dict[str, Any]:
        rows: Any = self._source(key) or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        if run_id is not None:
            row = next(
                (item for item in rows if str(item.get("runId")) == str(run_id)),
                None,
            )
        else:
            row = rows[0] if len(rows) == 1 else None
        return _tool_result(
            tool,
            row,
            state="FOUND" if row is not None else "NOT_FOUND",
            limitations=(
                "MEASUREMENT_NOT_GOVERNANCE_VERDICT",
                "MISSING_EVIDENCE_NOT_ZERO",
            ),
        )

    def get_control9_drift_measurement(self, run_id: str | None = None) -> dict[str, Any]:
        return self._measurement_by_run(
            "control9Measurements", "get_control9_drift_measurement", run_id
        )

    def get_control16_usage_measurement(self, run_id: str | None = None) -> dict[str, Any]:
        return self._measurement_by_run(
            "control16Measurements", "get_control16_usage_measurement", run_id
        )

    def get_event_readiness(self) -> dict[str, Any]:
        """Deterministic event readiness: control feasibility + six artifacts."""
        row = self._source("eventReadiness")
        return _tool_result(
            "get_event_readiness",
            row,
            state="FOUND" if row is not None else "NOT_FOUND",
            limitations=("READINESS_GUIDANCE_NOT_VERDICT",),
        )

    def get_event_guidance(self, topic: str | None = None) -> dict[str, Any]:
        """Bounded competition guidance section — advisory, not evidence."""
        guide = self._source("eventGuidance") or {}
        topics = guide.get("topics") or {}
        if topic and isinstance(topics, Mapping):
            row = topics.get(str(topic))
            return _tool_result(
                "get_event_guidance",
                row,
                state="FOUND" if row is not None else "NOT_FOUND",
                limitations=("COMPETITION_GUIDANCE_NOT_FORENSIC_EVIDENCE",),
            )
        return _tool_result(
            "get_event_guidance",
            {"topics": sorted(topics) if isinstance(topics, Mapping) else [], "guide": guide},
            state="FOUND" if guide else "NOT_FOUND",
            limitations=("COMPETITION_GUIDANCE_NOT_FORENSIC_EVIDENCE",),
        )

    def get_forensic_window(
        self,
        run_id: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Existing deterministic forensic-window projection — the same
        filtering the Timeline tab uses. Navigation/forensic view only;
        never a control verdict."""
        rows = timeline_rows(self._analysis)
        if not rows:
            return _tool_result("get_forensic_window", None, state="NOT_FOUND")
        try:
            window = forensic_window_rows(
                rows,
                from_time=from_time,
                to_time=to_time,
                identity=run_id,
                source=source,
            )
        except ValueError as exc:
            return _tool_result(
                "get_forensic_window",
                {"error": str(exc)},
                state="NOT_FOUND",
                limitations=("INVALID_WINDOW_BOUND",),
            )
        return _tool_result(
            "get_forensic_window",
            window,
            state="FOUND" if window["matchedCount"] else "NOT_FOUND",
            limitations=(
                "NO_CONTROL_VERDICT",
                "SEQUENCE_NOT_CAUSALITY",
                "CROSS_CLOCK_COMPARABILITY_NOT_ESTABLISHED"
                if not window["crossClockEstablished"]
                else "CLOCK_DOMAIN_SINGLE",
            ),
        )

    def get_imported_haiec_control_test_result(
        self,
        control_id: str,
        run_id: str,
        window_ref: str | None = None,
    ) -> dict[str, Any]:
        """Exact-match lookup over manually imported authoritative HAIEC
        Control Test results. LogSense reads the persisted snapshot; it
        never computes, substitutes, or promotes a verdict."""
        proofs: Any = self._source("importedHaiecProofs") or ()
        outcome = find_control_test_result(
            proofs, control_id=str(control_id), run_id=str(run_id), window_ref=window_ref
        )
        limitations = [
            "IMPORTED_SNAPSHOT_NOT_RUNTIME_EVIDENCE",
            "HAIEC_VERDICT_OWNER",
            "LOGSENSE_RECOMPUTATION_NO",
        ]
        if outcome["state"] == "NOT_FOUND":
            limitations.append("IMPORT_AUTHORITATIVE_HAIEC_CONTROL_TEST_RESULT")
        if outcome["state"] == "CONFLICT":
            limitations.append("AUTHORITATIVE_RESULT_CONFLICT_OPERATOR_REVIEW_REQUIRED")
        return _tool_result(
            "get_imported_haiec_control_test_result",
            outcome,
            state=outcome["state"],
            limitations=limitations,
        )

    def invoke(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        allowed = {item["name"] for item in self.capability_manifest["tools"]}
        if tool_name not in allowed:
            raise InvestigatorToolError(f"unsupported investigator tool: {tool_name}")
        method = getattr(self, tool_name)
        result = cast("dict[str, Any]", method(**arguments))
        self._audit.append(deepcopy(result))
        return result
