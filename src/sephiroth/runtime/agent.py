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

_LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


class ToolCallOmittedError(RuntimeError):
    """A capability with `require_tool_call=True` completed with zero tool
    calls — the model answered from parametric memory instead of using its
    (available, forced-on-round-0) tool. `tool_choice="required"` only
    covers round 0 (forcing it every round would loop forever — see
    `OllamaClient.chat`); this is the post-hoc check for the case that
    slips past it: a small local model that ignores `tool_choice` outright,
    or that calls a tool on round 0 but then answers without one on a later
    round. For an evidence-citing agent this is exactly how a fabricated
    citation gets into the answer in the first place — `_run_specialist`
    classifies this as `FailureCategory.TOOL` (recovery.py) so it goes
    through the same retry-then-abstain path as any other transient
    failure, rather than shipping an ungrounded answer."""


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
        language = (context or {}).get("language")
        if language and language in _LANGUAGE_NAMES:
            system_parts.append(
                f"Respond in {_LANGUAGE_NAMES[language]}, regardless of the language used "
                "elsewhere in this prompt."
            )
        tools: List[Dict[str, Any]] = []
        if allowed_tools:
            tools = registry.llm_tools(allowed_tools)
            system_parts.append(registry.system_prompt_summary(allowed_tools))

        user_content = query
        context_for_prompt = {k: v for k, v in (context or {}).items() if k != "language"}
        if context_for_prompt:
            context_lines = "\n".join(f"{k}: {v}" for k, v in context_for_prompt.items() if v)
            user_content = f"{query}\n\n--- Patient context ---\n{context_lines}"

        result = await self.client.chat(
            messages=[{"role": "user", "content": user_content}],
            system_prompt="\n\n".join(p for p in system_parts if p),
            tools=tools,
            # Scoped, not the raw dispatcher: advertising a filtered schema list
            # does not stop a model from naming a tool outside its whitelist.
            tool_executor=registry.scoped_executor(allowed_tools) if tools else None,
            tool_choice="required" if (tools and self.capability.require_tool_call) else None,
        )
        if tools and self.capability.require_tool_call and not result.tool_calls:
            raise ToolCallOmittedError(
                f"{self.capability.id} is require_tool_call=True but completed with no tool calls"
            )
        return result


__all__ = ["Agent", "MEDICAL_DISCLAIMER", "ToolCallOmittedError"]
