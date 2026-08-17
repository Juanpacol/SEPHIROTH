"""Fallback composition: try the primary LLM client (Gemini) first; on
failure (rate limit, daily quota exhaustion, any other outage) fall through to
a secondary client (Groq) for text/tool-calling. Vision and embeddings have no
Groq equivalent and always go to the primary.

Moved from `intelligence/llm/fallback_client.py` in Phase 1
(`docs/specs/SPEC-001-model-provider.md`). `supports_vision`/`supports_tools`
proxy the primary, matching the existing `self.model = primary.model` pattern.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import ChatResult, LLMUnavailableError, ToolExecutor

logger = logging.getLogger(__name__)


class FallbackLLMClient:
    """Wraps a primary and secondary text client with the same contract as
    GeminiClient (`chat`, `generate_json`, `health`, `describe_image`).
    `describe_image` always uses the primary — the secondary is assumed to
    have no vision support (true for Groq today)."""

    def __init__(self, primary: Any, secondary: Any):
        self.primary = primary
        self.secondary = secondary
        # Exposed for logging/error messages that reference `client.model`.
        self.model = primary.model

    @property
    def supports_vision(self) -> bool:
        return self.primary.supports_vision

    @property
    def supports_tools(self) -> bool:
        return self.primary.supports_tools

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        think: Optional[bool] = False,
    ) -> ChatResult:
        try:
            return await self.primary.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                tool_executor=tool_executor,
                think=think,
            )
        except LLMUnavailableError as exc:
            logger.warning(
                "primary LLM (%s) unavailable (%s); falling back to secondary", self.primary.model, exc
            )
            return await self.secondary.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                tool_executor=tool_executor,
                think=think,
            )

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
    ) -> Any:
        try:
            return await self.primary.generate_json(prompt, schema, system_prompt=system_prompt)
        except LLMUnavailableError as exc:
            logger.warning(
                "primary LLM (%s) unavailable (%s); falling back to secondary", self.primary.model, exc
            )
            return await self.secondary.generate_json(prompt, schema, system_prompt=system_prompt)

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        # No fallback here on purpose: the secondary (Groq) has no
        # comparable vision endpoint. Vision degrades to "unavailable"
        # exactly as it would with a bare GeminiClient — see vision_server.py.
        return await self.primary.describe_image(
            image_bytes=image_bytes, mime_type=mime_type, prompt=prompt, max_output_tokens=max_output_tokens
        )

    async def describe_image_stream(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ):
        # Same no-fallback rationale as describe_image above.
        async for chunk in self.primary.describe_image_stream(
            image_bytes=image_bytes, mime_type=mime_type, prompt=prompt, max_output_tokens=max_output_tokens
        ):
            yield chunk

    async def health(self) -> bool:
        primary_ok = await self.primary.health()
        if primary_ok:
            return True
        return await self.secondary.health()


__all__ = ["FallbackLLMClient"]
