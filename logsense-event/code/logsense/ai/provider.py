from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast


class InvestigatorBoundaryError(ValueError):
    """Raised when an AI response crosses the deterministic investigator boundary."""


@dataclass(frozen=True)
class InvestigatorAnswer:
    text: str
    citations: tuple[str, ...]
    uncertainty: tuple[str, ...] = ()
    tool_calls: tuple[str, ...] = ()
    provider: str = "unknown"


class AIProvider(Protocol):
    """Replaceable reasoning provider over read-only deterministic tools."""

    @property
    def provider_id(self) -> str: ...

    def ask(self, question: str, toolbox: object) -> InvestigatorAnswer: ...


PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_NAMES: tuple[str, ...] = (PROVIDER_OPENAI, PROVIDER_ANTHROPIC)
PROVIDER_LABELS: dict[str, str] = {
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_ANTHROPIC: "Claude (Anthropic)",
}
PROVIDER_KEY_ENV: dict[str, str] = {
    PROVIDER_OPENAI: "OPENAI_API_KEY",
    PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY",
}
PROVIDER_MODEL_ENV: dict[str, str] = {
    PROVIDER_OPENAI: "LOGSENSE_OPENAI_MODEL",
    PROVIDER_ANTHROPIC: "LOGSENSE_ANTHROPIC_MODEL",
}
ENV_PROVIDER_CHOICE = "LOGSENSE_AI_PROVIDER"


def normalize_provider_name(name: str | None) -> str:
    """Map UI/CLI spellings onto canonical provider IDs."""
    value = str(name or "").strip().lower()
    aliases = {
        "openai": PROVIDER_OPENAI,
        "gpt": PROVIDER_OPENAI,
        "claude": PROVIDER_ANTHROPIC,
        "anthropic": PROVIDER_ANTHROPIC,
        "anthropic-messages": PROVIDER_ANTHROPIC,
    }
    resolved = aliases.get(value, "")
    if not resolved:
        raise InvestigatorBoundaryError(
            f"unknown AI provider: {name!r} (expected one of {', '.join(PROVIDER_NAMES)})"
        )
    return resolved


def provider_key_env(name: str) -> str:
    return PROVIDER_KEY_ENV[normalize_provider_name(name)]


def provider_model_env(name: str) -> str:
    return PROVIDER_MODEL_ENV[normalize_provider_name(name)]


def create_provider(name: str | None = None, **overrides: Any) -> AIProvider:
    """Instantiate the configured investigator provider.

    ``name`` resolves in order: explicit argument → ``LOGSENSE_AI_PROVIDER``
    → persisted user preference → a provider whose key is already configured →
    OpenAI (the historical default).
    """
    if name is None:
        from logsense.user_config import resolve_ai_provider

        name = resolve_ai_provider()
    provider_name = normalize_provider_name(name)
    provider: AIProvider
    if provider_name == PROVIDER_ANTHROPIC:
        from logsense.ai.anthropic_provider import AnthropicInvestigatorProvider

        provider = cast(AIProvider, AnthropicInvestigatorProvider(**overrides))
    else:
        from logsense.ai.openai_provider import OpenAIInvestigatorProvider

        provider = cast(AIProvider, OpenAIInvestigatorProvider(**overrides))
    return provider


def validate_investigator_answer(
    answer: InvestigatorAnswer,
    *,
    allowed_citations: Sequence[str],
    require_citation: bool = True,
) -> InvestigatorAnswer:
    """Fail closed when a provider cites facts it was not given.

    This validates provenance only. It does not promote model prose into a
    canonical forensic conclusion.
    """
    allowed = {str(x) for x in allowed_citations if str(x)}
    cited = {str(x) for x in answer.citations if str(x)}
    unknown = sorted(cited - allowed)
    if unknown:
        raise InvestigatorBoundaryError(
            "provider cited references outside deterministic tool results: " + ", ".join(unknown)
        )
    if require_citation and answer.text.strip() and not cited:
        raise InvestigatorBoundaryError("evidence-bearing investigator answers require citations")
    return answer
