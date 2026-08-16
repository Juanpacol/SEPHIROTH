"""
Groq client with a tool-calling loop — the fallback provider used when
Gemini's free-tier quota (RPM or, more commonly, its daily RPD cap) is
exhausted. Groq's API is OpenAI-compatible, which means the MCP registry's
existing `llm_tools()` output (already OpenAI function-calling format,
built for Gemini's `parameters_json_schema`) needs no conversion here.

Same public contract as GeminiClient: chat()/generate_json()/health(),
same ChatResult shape — see fallback_client.py for how the two compose.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from .gemini_client import ChatResult, LLMUnavailableError

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Any]]

DEFAULT_MAX_TOOL_ROUNDS = 6
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqToolUseFailedError(Exception):
    """Groq's own model malformed a tool call (its `tool_use_failed` 400) —
    distinct from LLMUnavailableError because it isn't an outage: retrying
    the same round without tools usually recovers a plain-text answer."""


class GroqClient:
    """Thin wrapper around Groq's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "llama-3.3-70b-versatile",
        base_url: str = DEFAULT_BASE_URL,
        max_output_tokens: int = 2048,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_tool_rounds = max_tool_rounds
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured.")
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await self._sleep(min(2**attempt, 10))
                    continue
                raise LLMUnavailableError(str(exc)) from exc

            if response.status_code == 429 and attempt < self.max_retries - 1:
                delay = float(response.headers.get("retry-after", min(2**attempt, 10)))
                logger.warning("groq rate-limited (429), retrying in %.1fs", delay)
                await self._sleep(delay)
                last_exc = LLMUnavailableError(response.text)
                continue
            if response.status_code >= 500 and attempt < self.max_retries - 1:
                await self._sleep(min(2**attempt, 10))
                last_exc = LLMUnavailableError(response.text)
                continue
            if response.status_code == 400:
                try:
                    code = response.json().get("error", {}).get("code")
                except (json.JSONDecodeError, AttributeError):
                    code = None
                if code == "tool_use_failed":
                    raise GroqToolUseFailedError(response.text)
                raise LLMUnavailableError(f"{response.status_code}: {response.text}")
            if response.status_code >= 400:
                raise LLMUnavailableError(f"{response.status_code}: {response.text}")
            return response.json()
        raise LLMUnavailableError(str(last_exc) if last_exc else "groq request failed")

    def _to_messages(
        self, messages: List[Dict[str, Any]], system_prompt: Optional[str]
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        out.extend(messages)
        return out

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        think: Optional[bool] = False,
    ) -> ChatResult:
        history = self._to_messages(messages, system_prompt)
        executed_calls: List[Dict[str, Any]] = []
        started = time.perf_counter()

        for round_idx in range(self.max_tool_rounds):
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": history,
                "max_tokens": self.max_output_tokens,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            try:
                data = await self._post(payload)
            except GroqToolUseFailedError:
                logger.warning(
                    "groq mangled a tool call (tool_use_failed); retrying round %s without tools",
                    round_idx + 1,
                )
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
                data = await self._post(payload)
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls or tool_executor is None:
                logger.info(
                    "llm=chat provider=groq model=%s rounds=%s tool_calls=%s duration_ms=%s",
                    self.model,
                    round_idx + 1,
                    len(executed_calls),
                    round((time.perf_counter() - started) * 1000),
                )
                return ChatResult(
                    content=message.get("content") or "",
                    tool_calls=executed_calls,
                    rounds=round_idx + 1,
                )

            history.append(message)
            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args else {}
                    except json.JSONDecodeError:
                        args = {}

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
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(result, default=str),
                    }
                )

        return ChatResult(
            content="Tool-call limit reached without a final answer.",
            tool_calls=executed_calls,
            rounds=self.max_tool_rounds,
        )

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Any:
        """One-shot structured generation via `response_format: json_object`.
        Groq's JSON mode guarantees valid JSON but not schema conformance,
        so the schema is also embedded in the prompt as an instruction."""
        instructed_prompt = (
            f"{prompt}\n\nRespond with a single JSON object matching this JSON Schema "
            f"exactly (no prose, no markdown fences):\n{json.dumps(schema)}"
        )
        messages = self._to_messages([{"role": "user", "content": instructed_prompt}], system_prompt)
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": self.max_output_tokens,
        }
        data = await self._post(payload)
        return json.loads(data["choices"][0]["message"]["content"])

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        """Not supported: Groq's hosted vision models have been deprecated/
        unreliable historically. Vision stays exclusively on Gemini —
        see fallback_client.py, which never routes describe_image here."""
        raise LLMUnavailableError("GroqClient does not support vision; use Gemini for image description.")

    async def health(self) -> bool:
        if not self.api_key:
            return False
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
