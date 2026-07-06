"""Base class for Ollama-powered agents with MCP tool access."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from intelligence.llm import ChatResult, OllamaClient
from intelligence.mcp import get_registry

MEDICAL_DISCLAIMER = (
    "You are a clinical decision-support assistant for healthcare professionals. "
    "You do NOT diagnose. Every recommendation must be marked as requiring "
    "professional review, and every factual claim must cite its source."
)


class OllamaMCPAgent:
    """An agent = a system prompt + a whitelist of MCP tools + an Ollama model.

    Subclasses set ``name``, ``role_prompt`` and ``allowed_tools``. The MCP
    registry injects a natural-language tool catalog into the system prompt and
    enforces the structured tool contract via Ollama's native ``tools`` param.
    """

    name: str = "base-agent"
    role_prompt: str = ""
    allowed_tools: Optional[List[str]] = None  # None = no tools

    def __init__(self, client: OllamaClient):
        self.client = client

    async def run(self, query: str, context: Optional[Dict[str, Any]] = None) -> ChatResult:
        registry = get_registry()
        await registry.load()

        system_parts = [MEDICAL_DISCLAIMER, self.role_prompt]
        tools: List[Dict[str, Any]] = []
        if self.allowed_tools:
            tools = registry.ollama_tools(self.allowed_tools)
            system_parts.append(registry.system_prompt_summary(self.allowed_tools))

        user_content = query
        if context:
            context_lines = "\n".join(f"{k}: {v}" for k, v in context.items() if v)
            user_content = f"{query}\n\n--- Patient context ---\n{context_lines}"

        return await self.client.chat(
            messages=[{"role": "user", "content": user_content}],
            system_prompt="\n\n".join(p for p in system_parts if p),
            tools=tools,
            tool_executor=registry.execute if tools else None,
        )
