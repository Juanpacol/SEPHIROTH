"""Vision/chat split composition.

This is a *capability split*, not a "Gemini does vision" statement: it
routes `describe_image`/`describe_image_stream` to `vision_client` and
`chat`/`generate_json` to `chat_client` (which may itself be a
`FallbackLLMClient` chain), so each capability can use a different model.
Under `llm_provider="split"` both `chat_client` and `vision_client` are
local Ollama clients, with Groq as a chat-only fallback.

No fallback for vision by design (confirmed with the user): if the vision
client is unavailable, `describe_image` raises `LLMUnavailableError` and
`RadiologyAgent`/`vision_server.py` already degrade that to a `status:
"unavailable"` result rather than crashing — same behavior as today.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import ChatResult, ProviderInfo, ToolExecutor


class VisionChatSplitClient:
    """`vision_client` handles describe_image(_stream)/health's vision half;
    `chat_client` (itself possibly a `FallbackLLMClient` chain) handles
    chat/generate_json. `model`/`supports_tools` proxy `chat_client` since
    those describe the conversational path; `supports_vision` proxies
    `vision_client`."""

    def __init__(self, chat_client: Any, vision_client: Any):
        self.chat_client = chat_client
        self.vision_client = vision_client
        self.model = chat_client.model

    @property
    def supports_vision(self) -> bool:
        return self.vision_client.supports_vision

    @property
    def supports_tools(self) -> bool:
        return self.chat_client.supports_tools

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        think: Optional[bool] = False,
        tool_choice: Optional[str] = None,
    ) -> ChatResult:
        return await self.chat_client.chat(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            tool_executor=tool_executor,
            think=think,
            tool_choice=tool_choice,
        )

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
    ) -> Any:
        return await self.chat_client.generate_json(prompt, schema, system_prompt=system_prompt)

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        return await self.vision_client.describe_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )

    async def describe_image_stream(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ):
        async for chunk in self.vision_client.describe_image_stream(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        ):
            yield chunk

    def describe(self) -> ProviderInfo:
        """The vision half is the one that usually is not local -- this client
        exists precisely to send images somewhere a local model cannot handle
        them -- so the conjunction is what an operator needs to see."""
        chat = self.chat_client.describe()
        vision = self.vision_client.describe()
        return ProviderInfo(
            provider="split",
            model=chat.model,
            vision_model=vision.vision_model or vision.model,
            local=chat.local and vision.local,
            endpoint=chat.endpoint,
            components=(chat, vision),
        )

    async def health(self) -> bool:
        """Gates `/consult`, which only needs the conversational path — a
        vision model that is missing or unreachable degrades to `status:
        "unavailable"` at the call site and must never 503 the consultation
        endpoint. See `vision_health()` for the (non-fatal) vision signal."""
        return await self.chat_client.health()

    async def vision_health(self) -> bool:
        """Non-fatal operator signal, surfaced by `/api/agents/status`.
        Never raises — any exception from the underlying client's health
        check is treated as "unhealthy," and this is never ANDed into
        `health()`."""
        try:
            return await self.vision_client.health()
        except Exception:
            return False


__all__ = ["VisionChatSplitClient"]
