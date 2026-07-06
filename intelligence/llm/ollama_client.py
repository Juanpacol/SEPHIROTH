"""
Ollama client with a tool-calling loop.

Sends chat requests to a locally running Ollama server using its native
`tools` parameter. When the model responds with tool calls, they are executed
through the MCP registry and the results are fed back as `tool` role messages
until the model produces a plain assistant answer.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import ollama

logger = logging.getLogger(__name__)

# A tool executor receives (tool_name, arguments) and returns the tool output.
ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Any]]

MAX_TOOL_ROUNDS = 8


@dataclass
class ChatResult:
    """Final result of a chat exchange, including the tool-call trace."""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


class OllamaClient:
    """Thin wrapper around the `ollama` package with an MCP tool loop."""

    def __init__(self, host: str, model: str):
        self.model = model
        self._client = ollama.AsyncClient(host=host)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        think: Optional[bool] = False,
    ) -> ChatResult:
        """Run a chat exchange, resolving tool calls until a final answer.

        Args:
            messages: conversation messages ({"role", "content"} dicts).
            system_prompt: prepended as a system message when provided.
            tools: tool schemas in Ollama/OpenAI function-calling format.
            tool_executor: async callable that executes a named tool.
            think: extended-reasoning mode for models that support it
                (e.g. qwen3). Off by default — it multiplies latency; the
                agents rely on tools, not long hidden chains of thought.
        """
        history: List[Dict[str, Any]] = []
        if system_prompt:
            history.append({"role": "system", "content": system_prompt})
        history.extend(messages)

        executed_calls: List[Dict[str, Any]] = []
        started = time.perf_counter()

        for round_idx in range(MAX_TOOL_ROUNDS):
            try:
                response = await self._client.chat(
                    model=self.model,
                    messages=history,
                    tools=tools or [],
                    think=think,
                    options={"num_predict": 2048},
                )
            except ollama.ResponseError:
                # Some models reject the `think` parameter — retry without it.
                response = await self._client.chat(
                    model=self.model,
                    messages=history,
                    tools=tools or [],
                    options={"num_predict": 2048},
                )
            message = response["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls or tool_executor is None:
                logger.info(
                    "llm=chat model=%s rounds=%s tool_calls=%s duration_ms=%s",
                    self.model,
                    round_idx + 1,
                    len(executed_calls),
                    round((time.perf_counter() - started) * 1000),
                )
                return ChatResult(
                    content=message.get("content", ""),
                    tool_calls=executed_calls,
                    rounds=round_idx + 1,
                )

            history.append(message)
            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args)

                logger.info("Tool call: %s(%s)", name, args)
                try:
                    result = await tool_executor(name, args)
                except Exception as exc:  # surface tool failures to the model
                    result = {"error": str(exc)}
                    logger.exception("Tool %s failed", name)

                executed_calls.append({"name": name, "arguments": args, "result": result})
                history.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result, default=str),
                    }
                )

        return ChatResult(
            content="Tool-call limit reached without a final answer.",
            tool_calls=executed_calls,
            rounds=MAX_TOOL_ROUNDS,
        )

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Any:
        """One-shot structured generation: the response is forced to match
        `schema` (JSON Schema) via Ollama's `format` parameter and parsed."""
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        started = time.perf_counter()
        response = await self._client.chat(
            model=self.model,
            messages=messages,
            format=schema,
            think=False,
            options={"num_predict": 2048},
        )
        logger.info(
            "llm=generate_json model=%s duration_ms=%s",
            self.model,
            round((time.perf_counter() - started) * 1000),
        )
        return json.loads(response["message"]["content"])

    async def health(self) -> bool:
        """Return True when the Ollama server is reachable and the model exists."""
        try:
            models = await self._client.list()
            names = [m.get("model", m.get("name", "")) for m in models.get("models", [])]
            return any(self.model in name for name in names)
        except Exception:
            return False
