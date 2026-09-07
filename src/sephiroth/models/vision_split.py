"""Vision/chat split composition.

Routes `describe_image`/`describe_image_stream` to one client (Gemini —
the only provider in this codebase proven to do vision well; see the
runtime audit's finding that smaller/free chat models fabricate citations
more than Gemini) and `chat`/`generate_json` to a separate client (or
`FallbackLLMClient` chain) for text/tool-calling. Unlike `FallbackLLMClient`,
this is not about resilience — it's about sending each capability to the
provider actually measured to be good at it.

No fallback for vision by design (confirmed with the user): if the vision
client is unavailable, `describe_image` raises `LLMUnavailableError` and
`RadiologyAgent`/`vision_server.py` already degrade that to a `status:
"unavailable"` result rather than crashing — same behavior as today.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import ChatResult, ToolExecutor


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
    ) -> ChatResult:
        return await self.chat_client.chat(
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

    async def health(self) -> bool:
        chat_ok = await self.chat_client.health()
        vision_ok = await self.vision_client.health()
        return chat_ok and vision_ok


__all__ = ["VisionChatSplitClient"]
