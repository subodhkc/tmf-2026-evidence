from __future__ import annotations

from collections.abc import Callable

from logsense.ai.provider import InvestigatorAnswer
from logsense.ai.tools import InvestigatorToolbox


class DeterministicTestProvider:
    """Credential-free provider used to prove session/citation boundaries."""

    def __init__(
        self,
        script: Callable[[str, InvestigatorToolbox], InvestigatorAnswer],
        *,
        provider_id: str = "deterministic-test-provider",
    ):
        self._script = script
        self._provider_id = provider_id

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def ask(self, question: str, toolbox: InvestigatorToolbox) -> InvestigatorAnswer:
        answer = self._script(question, toolbox)
        if answer.provider == "unknown":
            return InvestigatorAnswer(
                text=answer.text,
                citations=answer.citations,
                uncertainty=answer.uncertainty,
                tool_calls=answer.tool_calls,
                provider=self._provider_id,
            )
        return answer
