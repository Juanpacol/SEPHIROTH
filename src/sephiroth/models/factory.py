"""Lazy singleton factory for the LLM client, built from settings.

Moved from `intelligence/llm/factory.py` in Phase 1
(`docs/specs/SPEC-001-model-provider.md`). With the default configuration
(`llm_provider="gemini"`), behavior is byte-identical to the pre-Phase-1
factory: a bare `GeminiClient` unless `GROQ_API_KEY` is configured, in which
case a `FallbackLLMClient` wraps Gemini (primary) and Groq (secondary).

`llm_provider="groq"` is new: it returns a bare `GroqClient`, not a client
wrapping the other way around — there's no acceptance criterion requiring
"Gemini as Groq's fallback." `describe_image`/`describe_image_stream` fall
through Gemini -> Groq too, but only when `groq_vision_model` is explicitly
set (opt-in, off by default — see config.py and GroqClient's docstrings on
why vision fallback stays best-effort rather than always-on).

`llm_provider="split"` composes two *local* Ollama clients (chat + vision),
with Groq as a chat-only fallback — no Gemini object is constructed for
`"ollama"` or `"split"` at all, even when `GEMINI_API_KEY` is set (see
`docs/specs`/the local-only isolation spec).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from core.config import settings

from .fallback import FallbackLLMClient
from .gemini import GeminiClient
from .groq import GroqClient
from .ollama import OllamaClient
from .vision_split import VisionChatSplitClient

_client: Optional[Union[GeminiClient, GroqClient, OllamaClient, FallbackLLMClient, VisionChatSplitClient]] = (
    None
)

#: One extra `OllamaClient` per distinct `AgentCapability.model_hint` in use,
#: keyed by model name. Local-only by design (`llm_provider in {"ollama",
#: "split"}`): a hint names an Ollama model tag (e.g.
#: `llama3-groq-tool-use:8b`, fine-tuned specifically for reliable
#: tool-calling), not a Gemini/Groq model, so it is meaningless against
#: those providers and silently ignored there — see `get_llm_client`.
_hinted_clients: Dict[str, OllamaClient] = {}


def get_llm_client(model_hint: Optional[str] = None) -> Any:
    global _client
    if model_hint and settings.llm_provider in ("ollama", "split"):
        if model_hint not in _hinted_clients:
            _hinted_clients[model_hint] = OllamaClient(
                model=model_hint,
                vision_model=settings.ollama_vision_model,
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                max_output_tokens=settings.ollama_max_output_tokens,
                timeout_seconds=settings.ollama_timeout_seconds,
                max_retries=settings.ollama_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.ollama_rpm_limit,
            )
        return _hinted_clients[model_hint]

    if _client is None:
        if settings.llm_provider == "split":
            vision_client = OllamaClient(
                model=settings.ollama_vision_model or settings.ollama_model,
                vision_model=settings.ollama_vision_model,
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                max_output_tokens=settings.ollama_max_output_tokens,
                timeout_seconds=settings.ollama_timeout_seconds,
                max_retries=settings.ollama_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.ollama_rpm_limit,
            )
            chat_primary = OllamaClient(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                max_output_tokens=settings.ollama_max_output_tokens,
                timeout_seconds=settings.ollama_timeout_seconds,
                max_retries=settings.ollama_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.ollama_rpm_limit,
            )
            chat_client: Any = chat_primary
            if settings.groq_api_key:
                chat_secondary = GroqClient(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    max_output_tokens=settings.groq_max_output_tokens,
                    timeout_seconds=settings.groq_timeout_seconds,
                    max_retries=settings.groq_max_retries,
                    max_tool_rounds=settings.llm_max_tool_rounds,
                    rpm_limit=settings.groq_rpm_limit,
                )
                chat_client = FallbackLLMClient(primary=chat_primary, secondary=chat_secondary)
            _client = VisionChatSplitClient(chat_client=chat_client, vision_client=vision_client)
            return _client

        if settings.llm_provider == "ollama":
            _client = OllamaClient(
                model=settings.ollama_model,
                vision_model=settings.ollama_vision_model,
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                max_output_tokens=settings.ollama_max_output_tokens,
                timeout_seconds=settings.ollama_timeout_seconds,
                max_retries=settings.ollama_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.ollama_rpm_limit,
            )
            return _client

        if settings.llm_provider == "groq":
            _client = GroqClient(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                vision_model=settings.groq_vision_model,
                max_output_tokens=settings.groq_max_output_tokens,
                timeout_seconds=settings.groq_timeout_seconds,
                max_retries=settings.groq_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.groq_rpm_limit,
            )
            return _client

        primary = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            vision_model=settings.gemini_vision_model,
            max_output_tokens=settings.gemini_max_output_tokens,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_retries=settings.gemini_max_retries,
            rpm_limit=settings.gemini_rpm_limit,
            max_tool_rounds=settings.llm_max_tool_rounds,
        )
        if settings.llm_enable_fallback and settings.groq_api_key:
            secondary = GroqClient(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                vision_model=settings.groq_vision_model,
                max_output_tokens=settings.groq_max_output_tokens,
                timeout_seconds=settings.groq_timeout_seconds,
                max_retries=settings.groq_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
                rpm_limit=settings.groq_rpm_limit,
            )
            _client = FallbackLLMClient(primary=primary, secondary=secondary)
        else:
            _client = primary
    return _client


def reset_llm_client() -> None:
    """Test-only: drop the cached client(s) so the next call rebuilds them."""
    global _client
    _client = None
    _hinted_clients.clear()


__all__ = ["get_llm_client", "reset_llm_client"]
