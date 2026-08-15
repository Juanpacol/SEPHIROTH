"""Lazy singleton factory for the Gemini client, built from settings."""

from __future__ import annotations

from typing import Optional

from core.config import settings

from .gemini_client import GeminiClient

_client: Optional[GeminiClient] = None


def get_llm_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            vision_model=settings.gemini_vision_model,
            max_output_tokens=settings.gemini_max_output_tokens,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_retries=settings.gemini_max_retries,
            rpm_limit=settings.gemini_rpm_limit,
            max_tool_rounds=settings.llm_max_tool_rounds,
        )
    return _client


def reset_llm_client() -> None:
    """Test-only: drop the cached client so the next call rebuilds it."""
    global _client
    _client = None
