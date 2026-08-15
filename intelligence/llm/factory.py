"""Lazy singleton factory for the LLM client, built from settings.

Returns a bare `GeminiClient` unless `GROQ_API_KEY` is configured, in
which case it returns a `FallbackLLMClient` wrapping Gemini (primary) and
Groq (secondary text/tool-calling fallback) — see fallback_client.py.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from core.config import settings

from .fallback_client import FallbackLLMClient
from .gemini_client import GeminiClient
from .groq_client import GroqClient

_client: Optional[Union[GeminiClient, FallbackLLMClient]] = None


def get_llm_client() -> Any:
    global _client
    if _client is None:
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
                max_output_tokens=settings.gemini_max_output_tokens,
                max_retries=settings.groq_max_retries,
                max_tool_rounds=settings.llm_max_tool_rounds,
            )
            _client = FallbackLLMClient(primary=primary, secondary=secondary)
        else:
            _client = primary
    return _client


def reset_llm_client() -> None:
    """Test-only: drop the cached client so the next call rebuilds it."""
    global _client
    _client = None
