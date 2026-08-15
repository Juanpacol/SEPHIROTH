"""Cloud LLM layer — Gemini client with MCP tool-calling support, with an
optional Groq fallback for text/tool-calling when Gemini's free-tier quota
is exhausted (see fallback_client.py)."""

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
