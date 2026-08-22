"""The `ModelProvider` contract.

Three implementations (`GeminiClient`, `GroqClient`, `FallbackLLMClient`) plus
the test double `FakeLLMClient` already shared these method names and this
`ChatResult` shape — by convention, with nothing that failed when they
diverged. This module writes down what was already true so it can be checked
mechanically instead of assumed.

See `docs/specs/SPEC-001-model-provider.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, runtime_checkable

# A tool executor receives (tool_name, arguments) and returns the tool output.
ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Any]]


class LLMUnavailableError(RuntimeError):
    """The only exception that triggers provider fallback (no key, quota
    exhausted, an unsupported capability, or a transient outage)."""


@dataclass
class ChatResult:
    """Final result of a chat exchange, including the tool-call trace.

    `prompt_tokens`/`completion_tokens` are summed across every round of
    the tool-calling loop (a multi-round exchange makes more than one
    provider call). Default to 0 for any client that can't report usage
    (`FakeLLMClient` in tests, a provider response missing usage
    metadata) -- additive fields, so nothing that already constructs a
    bare `ChatResult(content=...)` needs to change."""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@runtime_checkable
class ModelProvider(Protocol):
    """Structural contract every LLM backend satisfies.

    `chat`'s parameters after `messages` are keyword-only: every call site in
    the repo already passes them by keyword, so marking them keyword-only here
    makes that guarantee mechanical rather than conventional.

    `generate_json`'s first two parameters stay positional-or-keyword, in this
    order — `intelligence/evaluation/faithfulness.py` calls it positionally,
    `intelligence/nlp/timeline_extractor.py` calls it by keyword.
    """

    model: str
    supports_vision: bool
    supports_tools: bool

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        think: Optional[bool] = False,
    ) -> ChatResult: ...

    async def generate_json(
        self, prompt: str, schema: Dict[str, Any], *, system_prompt: Optional[str] = None
    ) -> Any: ...

    async def describe_image(
        self, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int = 512
    ) -> str: ...

    async def health(self) -> bool: ...


__all__ = ["ChatResult", "LLMUnavailableError", "ModelProvider", "ToolExecutor"]
