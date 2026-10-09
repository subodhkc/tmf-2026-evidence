from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from logsense.ai.instructions import INVESTIGATOR_SYSTEM_INSTRUCTIONS
from logsense.ai.provider import InvestigatorAnswer
from logsense.ai.tools import InvestigatorToolbox


class OpenAIProviderUnavailable(RuntimeError):
    """Raised when the optional OpenAI investigator dependencies are unavailable."""


class _InvestigatorOutput(BaseModel):
    answer: str = Field(description="Evidence-bounded answer to the investigator question")
    citations: list[str] = Field(
        default_factory=list, description="Exact reference IDs from tool-result citations"
    )
    uncertainty: list[str] = Field(
        default_factory=list, description="Explicit unresolved facts, limits, or uncertainty"
    )


def _load_agents_sdk() -> Any:
    try:
        import agents  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in optional-dependency environments
        raise OpenAIProviderUnavailable(
            "OpenAI investigator support is optional; install LogSense with the 'investigator' extra"
        ) from exc
    return agents


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# Retained alias; the canonical text lives in logsense.ai.instructions.
_SYSTEM_INSTRUCTIONS = INVESTIGATOR_SYSTEM_INSTRUCTIONS


class OpenAIInvestigatorProvider:
    """OpenAI Agents SDK adapter over the provider-neutral LogSense toolbox.

    The SDK orchestrates reasoning and tool calls only. Canonical truth remains in
    deterministic LogSense objects, and the outer InvestigatorSession validates
    the returned citations against the audited tool calls from this turn.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        session_id: str | None = None,
        session_db_path: str | Path | None = None,
    ) -> None:
        self.model = model or os.getenv("LOGSENSE_OPENAI_MODEL") or None
        self.session_id = session_id
        self.session_db_path = str(session_db_path) if session_db_path is not None else ":memory:"
        self._sdk_session: Any = None

    @property
    def provider_id(self) -> str:
        return "openai-agents"

    def _build_tools(self, toolbox: InvestigatorToolbox, sdk: Any) -> list[Any]:
        function_tool = sdk.function_tool

        @function_tool
        def get_claim(claim_id: str) -> str:
            """Get one deterministic ForensicClaim by exact claim ID."""
            return _json_result(toolbox.invoke("get_claim", claim_id=claim_id))

        @function_tool
        def get_evidence_card(claim_id: str) -> str:
            """Get the EvidenceCard for one exact claim ID."""
            return _json_result(toolbox.invoke("get_evidence_card", claim_id=claim_id))

        @function_tool
        def get_session() -> str:
            """Get the deterministic investigation-session projection."""
            return _json_result(toolbox.invoke("get_session"))

        @function_tool
        def get_execution_archetype(ref: str) -> str:
            """Get one execution-archetype projection by exact reference."""
            return _json_result(toolbox.invoke("get_execution_archetype", ref=ref))

        @function_tool
        def get_delegated_action_integrity(ref: str) -> str:
            """Get one delegated-action integrity projection by exact reference."""
            return _json_result(toolbox.invoke("get_delegated_action_integrity", ref=ref))

        @function_tool
        def get_effect_envelope(ref: str) -> str:
            """Get one effect-envelope assessment by exact reference."""
            return _json_result(toolbox.invoke("get_effect_envelope", ref=ref))

        @function_tool
        def get_guardrail_mediation(ref: str) -> str:
            """Get one guardrail-mediation projection by exact reference."""
            return _json_result(toolbox.invoke("get_guardrail_mediation", ref=ref))

        @function_tool
        def get_material_stories() -> str:
            """Get deterministic material investigation stories."""
            return _json_result(toolbox.invoke("get_material_stories"))

        @function_tool
        def get_investigation_insights() -> str:
            """Get deterministic investigation insight projections."""
            return _json_result(toolbox.invoke("get_investigation_insights"))

        @function_tool
        def get_trust_break_candidates() -> str:
            """Get deterministic trust-break candidate projections."""
            return _json_result(toolbox.invoke("get_trust_break_candidates"))

        @function_tool
        def get_recovery_projection(ref: str) -> str:
            """Get one recovery projection by exact reference."""
            return _json_result(toolbox.invoke("get_recovery_projection", ref=ref))

        @function_tool
        def get_comparison_perimeter() -> str:
            """Get the deterministic analysis/comparison perimeter."""
            return _json_result(toolbox.invoke("get_comparison_perimeter"))

        @function_tool
        def get_adapter_qualification(adapter_id: str) -> str:
            """Get one adapter qualification by exact adapter ID."""
            return _json_result(toolbox.invoke("get_adapter_qualification", adapter_id=adapter_id))

        @function_tool
        def propose_next_evidence(frontier_id: str) -> str:
            """Project the deterministic verification requirement for one frontier item."""
            return _json_result(toolbox.invoke("propose_next_evidence", frontier_id=frontier_id))

        @function_tool
        def get_competition_run(run_id: str = "") -> str:
            """Get the deterministic competition run resolution for a run ID (omit for the only run)."""
            return _json_result(toolbox.invoke("get_competition_run", run_id=run_id or None))

        @function_tool
        def get_control7_event_measurement(run_id: str = "") -> str:
            """Get the deterministic Control 7 (AIA-LOG-001) event recording measurement (omit run_id for the only run)."""
            return _json_result(
                toolbox.invoke("get_control7_event_measurement", run_id=run_id or None)
            )

        @function_tool
        def get_competition_evidence_bundle() -> str:
            """Get the deterministic Competition Evidence Bundle for the case."""
            return _json_result(toolbox.invoke("get_competition_evidence_bundle"))

        return [
            get_claim,
            get_evidence_card,
            get_session,
            get_execution_archetype,
            get_delegated_action_integrity,
            get_effect_envelope,
            get_guardrail_mediation,
            get_material_stories,
            get_investigation_insights,
            get_trust_break_candidates,
            get_recovery_projection,
            get_comparison_perimeter,
            get_adapter_qualification,
            propose_next_evidence,
            get_competition_run,
            get_control7_event_measurement,
            get_competition_evidence_bundle,
        ]

    def _session(self, sdk: Any) -> Any:
        if not self.session_id:
            return None
        if self._sdk_session is None:
            self._sdk_session = sdk.SQLiteSession(self.session_id, db_path=self.session_db_path)
        return self._sdk_session

    def ask(self, question: str, toolbox: InvestigatorToolbox) -> InvestigatorAnswer:
        sdk = _load_agents_sdk()
        agent_kwargs: dict[str, Any] = {
            "name": "Ask LogSense",
            "instructions": _SYSTEM_INSTRUCTIONS,
            "tools": self._build_tools(toolbox, sdk),
            "output_type": _InvestigatorOutput,
        }
        if self.model:
            agent_kwargs["model"] = self.model
        agent = sdk.Agent(**agent_kwargs)
        run_kwargs: dict[str, Any] = {}
        session = self._session(sdk)
        if session is not None:
            run_kwargs["session"] = session
        routed_question = f"{toolbox.routing_hint(question)}\n\nInvestigator question:\n{question}"
        result = sdk.Runner.run_sync(agent, routed_question, **run_kwargs)
        output = result.final_output
        if isinstance(output, _InvestigatorOutput):
            parsed = output
        elif isinstance(output, dict):
            parsed = _InvestigatorOutput.model_validate(output)
        else:
            parsed = _InvestigatorOutput.model_validate_json(str(output))
        return InvestigatorAnswer(
            text=parsed.answer,
            citations=tuple(parsed.citations),
            uncertainty=tuple(parsed.uncertainty),
            tool_calls=tuple(str(item.get("tool")) for item in toolbox.audit_results()),
            provider=self.provider_id,
        )
