"""The `ModelProvider` contract.

Three implementations (`GeminiClient`, `GroqClient`, `FallbackLLMClient`) plus
the test double `FakeLLMClient` already shared these method names and this
`ChatResult` shape — by convention, with nothing that failed when they
diverged. This module writes down what was already true so it can be checked
mechanically instead of assumed.

See `docs/specs/SPEC-001-model-provider.md`.
"""

from __future__ import annotations

import re
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


_REASON_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("no_api_key", re.compile(r"is not configured")),
    # A configured-but-wrong key: expired, revoked, or pasted with a typo.
    (
        "auth_error",
        re.compile(r"\b40[13]\b|unauthori[sz]ed|invalid api key|api key not valid|permission[_ ]denied"),
    ),
    ("no_vision_support", re.compile(r"no vision[_ ]model")),
    ("model_not_found", re.compile(r"not found on this ollama")),
    # `\brate\b` alone would also match "generate"; the limit has to be named.
    ("rate_limited", re.compile(r"\b429\b|rate[- ]?limit|too many requests|quota|resource_exhausted")),
    ("timeout", re.compile(r"time[- ]?out|timed out|deadline exceeded")),
    (
        "unreachable",
        re.compile(r"could not reach|connection (?:refused|error|reset)|connect(?:ion)? (?:failed|error)"),
    ),
    ("server_error", re.compile(r"\b5\d\d\b|internal server error|service unavailable|overloaded")),
)


def classify_unavailable(exc: BaseException) -> str:
    """A short, stable reason code for why a provider could not serve a call.

    Keyword-based on purpose: a dozen sites raise `LLMUnavailableError` with a
    message that is the client's own or the provider's verbatim, and
    structuring all of them would mean changing every client's error handling
    for a label. The label is what gets recorded in a trace and a log line --
    never the message itself, which can echo a provider's response text.
    Anything unrecognised is `unavailable`.
    """
    if isinstance(exc, PHINotAllowedError):
        return "phi_not_allowed"
    text = str(exc).lower()
    for reason, pattern in _REASON_PATTERNS:
        if pattern.search(text):
            return reason
    return "unavailable"


class AnswerSink(Protocol):
    """Receives the answering round's text as it is produced, so a caller
    that can only emit a complete `ChatResult` once the tool loop finishes
    can still relay provisional fragments while the final round generates.

    `delta(text)` is called with a raw, non-empty fragment of the *current*
    round's content — provisional, pre-citation-guard, pre-verification,
    pre-abstention text. `reset()` voids everything sent to `delta` since
    the previous `reset()` (or since the sink was created): the round that
    produced it turned out not to be the answer (it carried tool calls, or
    the attempt is being retried), and a caller relaying these fragments
    must treat them as if they had never been sent.
    """

    async def delta(self, text: str) -> None: ...

    async def reset(self) -> None: ...


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

    `chat`'s `answer_sink` is an optional, keyword-only, last parameter: a
    provider that can stream its final, tool-free round calls `delta()` on
    it as content arrives. An implementer that cannot stream still must
    accept the parameter and simply ignore it (Gemini, Groq, and Ollama's
    OpenAI-compatible path do this today). An implementer that does stream
    must call `reset()` once a round that emitted at least one delta turns
    out to carry tool calls, before running those tools — the sink must
    never be left holding text from a round that wasn't the answer.
    Transparent retry or provider fallback on a streamed round is allowed
    only before that round's first delta; once a fragment reached the sink,
    a failure must propagate as `LLMUnavailableError` with no retry and no
    fallback, since the caller already forwarded unrecoverable text.
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
        tool_choice: Optional[str] = None,
        answer_sink: Optional["AnswerSink"] = None,
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
    "AnswerSink",
    "ChatResult",
    "classify_unavailable",
    "LLMUnavailableError",
    "ModelProvider",
    "PHINotAllowedError",
    "ProviderInfo",
    "ToolExecutor",
    "_is_local_endpoint",
]
