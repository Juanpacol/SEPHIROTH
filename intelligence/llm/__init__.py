"""DEPRECATED — moved to `sephiroth.models` in Phase 1. Re-exports for
backward compatibility only; removed in Phase 2. See
`docs/specs/SPEC-001-model-provider.md`."""

from .factory import get_llm_client, reset_llm_client
from .fallback_client import FallbackLLMClient
from .gemini_client import ChatResult, GeminiClient, LLMUnavailableError
from .groq_client import GroqClient

__all__ = [
    "ChatResult",
    "GeminiClient",
    "GroqClient",
    "FallbackLLMClient",
    "LLMUnavailableError",
    "get_llm_client",
    "reset_llm_client",
]
