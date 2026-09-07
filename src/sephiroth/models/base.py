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


class PHINotAllowedError(LLMUnavailableError):
    """Patient content was about to reach a provider outside the deployment
    while `ai_allow_phi` is off (SPEC-022, ADR-015).

    Subclasses `LLMUnavailableError` on purpose. Every seam that can carry
    patient content already handles "the model cannot serve this" by degrading
    to something deterministic, and a refusal on privacy grounds should take
    that same path rather than needing a second one written at each site. A
    caller that wants to tell the two apart still can.
    """


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


#: Hosts that mean "this machine". A `base_url` on one of these is local by
#: construction; anything else is judged by `_is_private_host`.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})  # nosec B104 -- a hostname being compared against, not a bind address


def _is_local_endpoint(base_url: str) -> bool:
    """Whether a request to this URL stays inside the deployment.

    A report, not a firewall (SPEC-022 §11 risk 2). It answers the question a
    host string can actually answer -- is this address on this machine or this
    private network -- and a tunnel on loopback can defeat it. Being wrong in
    the safe direction matters more than being clever: an unparseable or empty
    URL is treated as *not* local.
    """
    from urllib.parse import urlsplit

    host = (urlsplit(base_url).hostname or "").lower()
    if not host:
        return False
    if host in _LOOPBACK_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        from ipaddress import ip_address

        return ip_address(host).is_private
    except ValueError:
        # A bare service name on a container network ("ollama", "api") has no
        # dots and cannot be a public DNS name.
        return "." not in host


@dataclass(frozen=True)
class ProviderInfo:
    """What is actually running, for anything that reports it to a human.

    Exists because three endpoints each answered that question from
    `settings.gemini_*` regardless of the configured provider, so an operator
    running entirely on a local model was told their data was going to Google
    (SPEC-022 §2). One structure, built by the client itself, is the only way
    those three stay true to each other.

    `endpoint` is a host, never a full URL with a key in it.
    """

    provider: str
    model: str
    vision_model: str = ""
    local: bool = False
    endpoint: str = ""
    #: A composite (fallback, split) describes its parts. Empty for a leaf.
    components: tuple["ProviderInfo", ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "vision_model": self.vision_model,
            "local": self.local,
            "endpoint": self.endpoint,
            "components": [c.as_dict() for c in self.components],
        }


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

    def describe(self) -> ProviderInfo:
        """What this client is, for a human reading a status page.

        Pure: no I/O, so `/health` can call it without becoming a probe.
        """
        ...


__all__ = [
    "ChatResult",
    "LLMUnavailableError",
    "ModelProvider",
    "PHINotAllowedError",
    "ProviderInfo",
    "ToolExecutor",
    "_is_local_endpoint",
]
