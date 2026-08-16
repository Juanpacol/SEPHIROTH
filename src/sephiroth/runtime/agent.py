"""One clinical agent: a capability record + an LLM client + the tool runtime.

Moved from `intelligence/agents/base.py::MCPAgent`
(`docs/specs/SPEC-003-agent-runtime.md`). Behaviorally identical `.run()` —
built from an `AgentCapability` instead of class attributes, and dispatching
through `sephiroth.tools.get_tool_runtime()` instead of the (now-deleted)
`intelligence.mcp` registry shim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sephiroth.contracts import AgentCapability
from sephiroth.models import ChatResult, ModelProvider
from sephiroth.tools import get_tool_runtime

MEDICAL_DISCLAIMER = (
    "You are a clinical decision-support assistant for healthcare professionals. "
    "You do NOT diagnose. Every recommendation must be marked as requiring "
    "professional review, and every factual claim must cite its source."
)


class Agent:
    """A capability record, an LLM client, and a tool scope — nothing else."""

    def __init__(self, capability: AgentCapability, client: ModelProvider):
        self.capability = capability
        self.client = client

    @property
    def name(self) -> str:
        return self.capability.id

    async def run(self, query: str, context: Optional[Dict[str, Any]] = None) -> ChatResult:
        registry = get_tool_runtime()
        await registry.load()

        allowed_tools = self.capability.tools or None  # [] means "no tools", same as None did
        system_parts = [MEDICAL_DISCLAIMER, self.capability.role_prompt]
        tools: List[Dict[str, Any]] = []
        if allowed_tools:
            tools = registry.llm_tools(allowed_tools)
            system_parts.append(registry.system_prompt_summary(allowed_tools))

        user_content = query
        if context:
            context_lines = "\n".join(f"{k}: {v}" for k, v in context.items() if v)
            user_content = f"{query}\n\n--- Patient context ---\n{context_lines}"

        return await self.client.chat(
            messages=[{"role": "user", "content": user_content}],
            system_prompt="\n\n".join(p for p in system_parts if p),
            tools=tools,
            # Scoped, not the raw dispatcher: advertising a filtered schema list
            # does not stop a model from naming a tool outside its whitelist.
            tool_executor=registry.scoped_executor(allowed_tools) if tools else None,
        )


__all__ = ["Agent", "MEDICAL_DISCLAIMER"]
