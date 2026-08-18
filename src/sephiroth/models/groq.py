"""
Groq client with a tool-calling loop — the fallback provider used when
Gemini's free-tier quota is exhausted. Groq's API is OpenAI-compatible, which
means the MCP registry's existing `llm_tools()` output (already OpenAI
function-calling format) needs no conversion here.

Moved from `intelligence/llm/groq_client.py` in Phase 1
(`docs/specs/SPEC-001-model-provider.md`) to implement `ModelProvider`. Retry
backoff now delegates to `sephiroth.models._throttle.backoff_delay` (capped at
10s, matching prior behavior exactly) instead of an inline formula. Rate
limiting is new: `rpm_limit=0` (the default) disables it entirely, which is
byte-identical to the pre-Phase-1 behavior of having no limiter at all.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from ._throttle import RateLimiter, backoff_delay
from .base import ChatResult, LLMUnavailableError, ToolExecutor

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ROUNDS = 6
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
_BACKOFF_CAP_SECONDS = 10


class GroqToolUseFailedError(Exception):
    """Groq's own model malformed a tool call (its `tool_use_failed` 400) —
    distinct from LLMUnavailableError because it isn't an outage: retrying
    the same round without tools usually recovers a plain-text answer. Must
    not escape `chat()`."""


class GroqClient:
    """Thin wrapper around Groq's OpenAI-compatible chat completions API."""

    supports_vision = False
    supports_tools = True

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "llama-3.3-70b-versatile",
        vision_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        max_output_tokens: int = 2048,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        rpm_limit: int = 0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.model = model
        # Instance-level, not the class default — vision only turns on when
        # a caller explicitly opts in via `vision_model` (see config.py's
        # `groq_vision_model`), since Groq's vision model lineup churns.
        self.vision_model = vision_model
        self.supports_vision = bool(vision_model)
        self.api_key = api_key
        self.base_url = base_url
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_tool_rounds = max_tool_rounds
        self.rpm_limit = rpm_limit
        self._sleep = sleep
        # 0 (the default) means no limiter at all — the exact pre-Phase-1
        # behavior, since Groq previously had no throttling whatsoever.
        self._rate_limiter = RateLimiter(rpm_limit, sleep=sleep) if rpm_limit > 0 else None
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
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await self._sleep(backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0))
                    continue
                raise LLMUnavailableError(str(exc)) from exc

            if response.status_code == 429 and attempt < self.max_retries - 1:
                retry_after = response.headers.get("retry-after")
                delay = (
                    float(retry_after)
                    if retry_after
                    else backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0)
                )
                logger.warning("groq rate-limited (429), retrying in %.1fs", delay)
                await self._sleep(delay)
                last_exc = LLMUnavailableError(response.text)
                continue
            if response.status_code >= 500 and attempt < self.max_retries - 1:
                await self._sleep(backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0))
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
        *,
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
        *,
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

    def _vision_payload(self, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int) -> Dict[str, Any]:
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        return {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": max_output_tokens,
        }

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        """Best-effort only, opt-in via `vision_model` (unset by default —
        see config.py's `groq_vision_model`). Groq's vision model lineup has
        churned before (Llama 4 Scout/Maverick both deprecated in favor of
        text-only replacements); this exists so a Gemini vision outage
        degrades to a second real attempt instead of "unavailable," for
        whoever explicitly accepts that instability."""
        if not self.vision_model:
            raise LLMUnavailableError("GroqClient has no vision_model configured; use Gemini for image description.")
        data = await self._post(self._vision_payload(image_bytes, mime_type, prompt, max_output_tokens))
        return (data["choices"][0]["message"].get("content") or "").strip()

    async def describe_image_stream(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ):
        """Streaming counterpart to `describe_image` — same opt-in
        `vision_model` gate. No retry loop, matching `GeminiClient.
        describe_image_stream`'s own rationale: a stream that fails mid-flight
        can't transparently retry without replaying already-yielded chunks."""
        if not self.vision_model:
            raise LLMUnavailableError("GroqClient has no vision_model configured; use Gemini for image description.")
        if not self.api_key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured.")

        payload = {**self._vision_payload(image_bytes, mime_type, prompt, max_output_tokens), "stream": True}
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMUnavailableError(f"{response.status_code}: {body.decode(errors='replace')}")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[len("data: ") :]
                    if raw == "[DONE]":
                        break
                    delta = json.loads(raw)["choices"][0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(str(exc)) from exc

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


__all__ = ["DEFAULT_MAX_TOOL_ROUNDS", "GroqClient", "GroqToolUseFailedError"]
