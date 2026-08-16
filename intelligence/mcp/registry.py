"""
MCP registry — the bridge between FastMCP servers and Ollama tool calling.

Aggregates every FastMCP server in this package, exposes their tool schemas in
two forms:

1. Ollama's native ``tools`` parameter format (structured function-calling
   contract — what the model actually invokes), and
2. a human-readable summary injected into each agent's system prompt, so the
   model reasons in natural language about when to reach for each tool.

Tools are executed in-process through FastMCP's in-memory client transport —
no subprocesses, no sockets.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from fastmcp import Client, FastMCP

from core.config import settings

from . import drug_safety_server, imaging_server, nlp_server, rag_server, vision_server

logger = logging.getLogger("intelligence.mcp.registry")

SERVERS: List[FastMCP] = [
    nlp_server.mcp,
    imaging_server.mcp,
    rag_server.mcp,
    drug_safety_server.mcp,
    vision_server.mcp,
]


class MCPRegistry:
    """Discovers tools across all FastMCP servers and executes them by name."""

    def __init__(self, servers: Optional[List[FastMCP]] = None):
        self.servers = servers if servers is not None else SERVERS
        self._tool_index: Dict[str, FastMCP] = {}
        self._schemas: List[Dict[str, Any]] = []
        self._loaded = False

    async def load(self) -> None:
        """Discover every tool on every server (idempotent)."""
        if self._loaded:
            return
        for server in self.servers:
            async with Client(server) as client:
                for tool in await client.list_tools():
                    self._tool_index[tool.name] = server
                    self._schemas.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                            },
                        }
                    )
        self._loaded = True

    def llm_tools(self, allowed: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Tool schemas in Ollama format, optionally filtered to a whitelist."""
        if allowed is None:
            return list(self._schemas)
        return [s for s in self._schemas if s["function"]["name"] in allowed]

    def system_prompt_summary(self, allowed: Optional[List[str]] = None) -> str:
        """Natural-language tool catalog for inclusion in a system prompt."""
        lines = ["You have access to the following clinical tools:"]
        for schema in self.llm_tools(allowed):
            fn = schema["function"]
            first_sentence = fn["description"].split(".")[0].strip()
            lines.append(f"- {fn['name']}: {first_sentence}.")
        lines.append(
            "Call a tool whenever it can ground your answer in data or evidence. "
            "Never invent citations — only cite what a tool returned."
        )
        return "\n".join(lines)

    def scoped_executor(self, allowed: Optional[List[str]]) -> Callable[[str, Dict[str, Any]], Any]:
        """A tool executor bound to a whitelist.

        `llm_tools(allowed)` only controls which schemas the model is *shown*.
        Nothing stopped a model from naming a tool outside that list and having
        it executed anyway, because `execute()` checks existence and nothing
        else. Agents pass this bound executor instead of `execute` so the
        whitelist is enforced where dispatch actually happens.

        An unauthorized call returns an error *result* rather than raising: the
        model gets it back as tool output and can recover on the next round,
        which is the same shape as any other tool failure.
        """

        async def _execute(tool_name: str, arguments: Dict[str, Any]) -> Any:
            if allowed is not None and tool_name not in allowed:
                logger.warning(
                    "tool_authorization_denied tool=%s allowed=%s enforced=%s",
                    tool_name,
                    ",".join(allowed) or "-",
                    settings.enforce_tool_authorization,
                )
                if settings.enforce_tool_authorization:
                    return {"error": f"Tool not authorized for this agent: {tool_name}"}
            return await self.execute(tool_name, arguments)

        return _execute

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name through its owning server (in-memory).

        Unscoped by design — this is the raw dispatch path. Callers that expose
        tools to a model must go through `scoped_executor()` instead.
        """
        server = self._tool_index.get(tool_name)
        if server is None:
            return {"error": f"Unknown tool: {tool_name}"}

        async with Client(server) as client:
            result = await client.call_tool(tool_name, arguments)

        # Unwrap FastMCP content blocks into plain JSON-serializable data.
        if result.structured_content is not None:
            return result.structured_content
        parts = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    parts.append(json.loads(text))
                except (json.JSONDecodeError, TypeError):
                    parts.append(text)
        return parts[0] if len(parts) == 1 else parts


_registry: Optional[MCPRegistry] = None


def get_registry() -> MCPRegistry:
    """Process-wide singleton registry."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry
