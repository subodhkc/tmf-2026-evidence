from __future__ import annotations

from dataclasses import dataclass

from logsense.ai.provider import AIProvider, InvestigatorAnswer, validate_investigator_answer
from logsense.ai.tools import InvestigatorToolbox


@dataclass(frozen=True)
class InvestigatorTurn:
    question: str
    answer: InvestigatorAnswer
    tool_results: tuple[dict, ...]


class InvestigatorSession:
    """Audited Ask LogSense orchestration over deterministic read-only tools."""

    def __init__(self, *, provider: AIProvider, toolbox: InvestigatorToolbox):
        self.provider = provider
        self.toolbox = toolbox
        self._turns: list[InvestigatorTurn] = []

    def ask(self, question: str) -> InvestigatorTurn:
        normalized = question.strip()
        if not normalized:
            raise ValueError("question is required")
        self.toolbox.reset_audit()
        answer = self.provider.ask(normalized, self.toolbox)
        tool_results = tuple(self.toolbox.audit_results())
        validated = validate_investigator_answer(
            answer,
            allowed_citations=self.toolbox.used_citations(),
            require_citation=bool(answer.text.strip()),
        )
        turn = InvestigatorTurn(question=normalized, answer=validated, tool_results=tool_results)
        self._turns.append(turn)
        return turn

    def turns(self) -> tuple[InvestigatorTurn, ...]:
        return tuple(self._turns)
