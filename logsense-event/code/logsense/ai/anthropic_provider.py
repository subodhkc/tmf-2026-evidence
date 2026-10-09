from __future__ import annotations

import inspect
import json
import os
from typing import Any

from logsense.ai.capabilities import tool_specs
from logsense.ai.instructions import INVESTIGATOR_SYSTEM_INSTRUCTIONS
from logsense.ai.provider import InvestigatorAnswer
from logsense.ai.tools import InvestigatorToolbox

_SUBMIT_TOOL = "submit_investigator_answer"
_MAX_TURNS = 12


class AnthropicProviderUnavailable(RuntimeError):
    """Raised when the optional Anthropic investigator dependencies are unavailable."""


def _load_anthropic_sdk() -> Any:
    try:
        import anthropic  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in optional-dependency environments
        raise AnthropicProviderUnavailable(
            "Claude investigator support is optional; install LogSense with the 'investigator' extra"
        ) from exc
    return anthropic


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Serialize an Anthropic content block for message history reuse."""
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        return {str(k): v for k, v in dump().items()}
    if isinstance(block, dict):
        return dict(block)
    return {"type": "text", "text": str(block)}


def _tool_schemas() -> list[dict[str, Any]]:
    """Build Anthropic tool definitions from the frozen provider-neutral manifest.

    Schemas derive from ``tool_specs()`` plus the toolbox methods' own
    docstrings/signatures, so a new canonical tool appears for Claude without
    a second hard-coded list.
    """
    schemas: list[dict[str, Any]] = []
    for spec in tool_specs():
        name = str(spec["name"])
        method = getattr(InvestigatorToolbox, name)
        doc = inspect.getdoc(method) or name
        properties: dict[str, Any] = {}
        required: list[str] = []
        signature = inspect.signature(method)
        for parameter in signature.parameters.values():
            if parameter.name == "self":
                continue
            properties[parameter.name] = {
                "type": "string",
                "description": f"Exact {parameter.name} reference value",
            }
            if parameter.default is inspect.Parameter.empty:
                required.append(parameter.name)
        schemas.append(
            {
                "name": name,
                "description": doc,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
    schemas.append(
        {
            "name": _SUBMIT_TOOL,
            "description": (
                "Submit the final investigator answer. Call exactly once when the answer "
                "is ready; citations must be exact reference IDs returned by tools used "
                "in this turn."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "Evidence-bounded answer to the investigator question",
                    },
                    "citations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exact reference IDs from tool-result citations",
                    },
                    "uncertainty": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Explicit unresolved facts, limits, or uncertainty",
                    },
                },
                "required": ["answer", "citations", "uncertainty"],
            },
        }
    )
    return schemas


class AnthropicInvestigatorProvider:
    """Anthropic Messages API adapter over the provider-neutral LogSense toolbox.

    Tool calls run through the same read-only ``InvestigatorToolbox`` and the
    same system instructions as the OpenAI adapter. The outer
    ``InvestigatorSession`` validates returned citations against the audited
    tool calls from this turn; the model never establishes forensic truth.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        max_turns: int = _MAX_TURNS,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.getenv("LOGSENSE_ANTHROPIC_MODEL") or None
        self.max_turns = max_turns
        self._api_key = api_key  # never logged, persisted, or exposed in answers

    @property
    def provider_id(self) -> str:
        return "anthropic-messages"

    def ask(self, question: str, toolbox: InvestigatorToolbox) -> InvestigatorAnswer:
        if not (self._api_key or os.getenv("ANTHROPIC_API_KEY")):
            raise AnthropicProviderUnavailable(
                "Anthropic API key is not configured; set ANTHROPIC_API_KEY or run 'logsense setup'"
            )
        sdk = _load_anthropic_sdk()
        client_kwargs: dict[str, Any] = {}
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        client = sdk.Anthropic(**client_kwargs)

        system = (
            INVESTIGATOR_SYSTEM_INSTRUCTIONS
            + f"\nWhen the answer is ready you MUST call the `{_SUBMIT_TOOL}` tool exactly once "
            "with the fields answer, citations, uncertainty. Do not answer in plain text."
        )
        routed_question = f"{toolbox.routing_hint(question)}\n\nInvestigator question:\n{question}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": routed_question}]
        request: dict[str, Any] = {
            "model": self.model or "claude-sonnet-4-5",
            "max_tokens": 4096,
            "system": system,
            "tools": _tool_schemas(),
            "messages": messages,
        }

        submitted: dict[str, Any] | None = None
        last_text = ""
        for _ in range(self.max_turns):
            response = client.messages.create(**request)
            messages.append(
                {"role": "assistant", "content": [_block_to_dict(b) for b in response.content]}
            )
            tool_uses = [
                block for block in response.content if getattr(block, "type", None) == "tool_use"
            ]
            if not tool_uses:
                last_text = "".join(
                    getattr(block, "text", "")
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                break
            results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                if tool_use.name == _SUBMIT_TOOL:
                    submitted = dict(tool_use.input) if isinstance(tool_use.input, dict) else {}
                    continue
                result = toolbox.invoke(tool_use.name, **dict(tool_use.input or {}))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": _json_result(result),
                    }
                )
            if submitted is not None:
                break
            if not results:
                break
            messages.append({"role": "user", "content": results})
            request["messages"] = messages

        if submitted is None:
            # No structured submission: surface the raw text and let the outer
            # provenance gate decide. An uncited evidence-bearing answer fails
            # closed rather than being presented as truth.
            return InvestigatorAnswer(
                text=last_text.strip(),
                citations=(),
                uncertainty=() if last_text.strip() else ("provider returned no answer",),
                tool_calls=tuple(str(item.get("tool")) for item in toolbox.audit_results()),
                provider=self.provider_id,
            )
        return InvestigatorAnswer(
            text=str(submitted.get("answer") or ""),
            citations=tuple(str(x) for x in submitted.get("citations") or () if str(x)),
            uncertainty=tuple(str(x) for x in submitted.get("uncertainty") or () if str(x)),
            tool_calls=tuple(str(item.get("tool")) for item in toolbox.audit_results()),
            provider=self.provider_id,
        )
