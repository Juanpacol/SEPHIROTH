"""
Ollama client — local model runtime for free, unlimited-iteration development
(no API key, no rate limits, no free-tier quota to exhaust).

Against a genuine local Ollama install (`_is_local_endpoint(base_url)`),
`chat()`/`generate_json()` use Ollama's *native* `/api/chat` (same endpoint
`describe_image`/`describe_image_stream` already used for vision) rather than
the OpenAI-compatible `/v1/chat/completions` shim. That shim silently drops
unknown top-level fields — `"think"` never reaches the model through it, so a
hybrid-reasoning model (e.g. `qwen3:8b`) always ran its full internal
reasoning pass even when the caller asked for `think=False`, ~30-50x slower
for no answer-quality gain on straightforward tool-calling turns (measured:
~28s/306 tokens with thinking vs ~0.5s/3 tokens without, same prompt). The
native endpoint honors `think` and also returns tool-call arguments as an
already-parsed dict instead of a JSON string.

When `base_url` is retargeted at a *hosted* OpenAI-compatible endpoint
(OpenRouter, to run this same model remotely) there is no Ollama-native
`/api/...` to fall back to, so both methods keep using the original
OpenAI-compatible request/response shape in that case — same protocol
`GeminiClient`/`GroqClient` implement (`base.py`).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from PIL import Image

from ._throttle import RateLimiter, backoff_delay
from .base import ChatResult, LLMUnavailableError, ProviderInfo, ToolExecutor, _is_local_endpoint

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ROUNDS = 6
DEFAULT_BASE_URL = "http://localhost:11434/v1"
_BACKOFF_CAP_SECONDS = 10
# Ollama's OpenAI-compatible endpoint silently drops unknown top-level
# fields — `"options": {"num_ctx": ...}` (and `"think"`) never reach the
# model, which stays on its default context window regardless of what's
# passed here. A real clinical-resolution upload (e.g. 2412x1956) alone
# tokenizes past that default and fails with `exceed_context_size_error`
# before generating anything, so the image itself has to be downscaled
# client-side — the only lever this endpoint actually honors.
_VISION_MAX_DIMENSION = 896


def _downscale_for_vision(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Shrink an image to fit comfortably in a small local VLM's context
    window. Re-encodes as JPEG regardless of input format — smaller than
    PNG for photographic/grayscale content and one predictable code path."""
    with Image.open(io.BytesIO(image_bytes)) as opened:
        # Separate name: `Image.open` yields an ImageFile, `.convert` an Image.
        rgb = opened.convert("RGB")
        if max(rgb.size) > _VISION_MAX_DIMENSION:
            rgb.thumbnail((_VISION_MAX_DIMENSION, _VISION_MAX_DIMENSION), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"


class OllamaClient:
    """Thin wrapper around Ollama's OpenAI-compatible chat completions API."""

    supports_vision = False
    supports_tools = True

    def __init__(
        self,
        model: str = "qwen2.5:14b",
        vision_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        max_output_tokens: int = 2048,
        timeout_seconds: int = 120,
        max_retries: int = 3,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        rpm_limit: int = 0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.model = model
        # Instance-level, not the class default — same opt-in pattern as
        # GroqClient's vision_model (off unless a caller names a real
        # vision-capable local model, e.g. "qwen2.5vl:7b").
        self.vision_model = vision_model
        self.supports_vision = bool(vision_model)
        # Ollama needs no key locally; set when base_url points elsewhere
        # (e.g. OpenRouter, which does require one).
        self.api_key = api_key
        self.base_url = base_url
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_tool_rounds = max_tool_rounds
        self.rpm_limit = rpm_limit
        self._sleep = sleep
        self._rate_limiter = RateLimiter(rpm_limit, sleep=sleep) if rpm_limit > 0 else None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def _post(self, payload: Dict[str, Any], *, endpoint: str = "/chat/completions") -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()
            try:
                response = await self._client.post(endpoint, json=payload)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await self._sleep(backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0))
                    continue
                raise LLMUnavailableError(
                    f"Could not reach Ollama at {self.base_url} — is `ollama serve` running? ({exc})"
                ) from exc

            if response.status_code == 429 and attempt < self.max_retries - 1:
                delay = backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0)
                logger.warning("ollama rate-limited (429), retrying in %.1fs", delay)
                await self._sleep(delay)
                last_exc = LLMUnavailableError(response.text)
                continue
            if response.status_code >= 500 and attempt < self.max_retries - 1:
                await self._sleep(backoff_delay(attempt, cap=_BACKOFF_CAP_SECONDS, jitter=lambda a, b: 0))
                last_exc = LLMUnavailableError(response.text)
                continue
            if response.status_code == 404:
                raise LLMUnavailableError(
                    f"Model '{self.model}' not found on this Ollama server — run "
                    f"`ollama pull {self.model}` first. ({response.text})"
                )
            if response.status_code >= 400:
                raise LLMUnavailableError(f"{response.status_code}: {response.text}")
            return response.json()
        raise LLMUnavailableError(str(last_exc) if last_exc else "ollama request failed")

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
        tool_choice: Optional[str] = None,
    ) -> ChatResult:
        history = self._to_messages(messages, system_prompt)
        executed_calls: List[Dict[str, Any]] = []
        started = time.perf_counter()
        prompt_tokens = 0
        completion_tokens = 0
        native = _is_local_endpoint(self.base_url)

        for round_idx in range(self.max_tool_rounds):
            # `tool_choice` (e.g. "required", from `AgentCapability.require_tool_call`
            # — small local models answer from parametric memory and fabricate a
            # citation rather than reliably calling a tool on "auto") only makes
            # sense on the first round: forcing it every round would make the
            # model call a tool forever and never emit a final answer, silently
            # burning the whole `max_tool_rounds` budget.
            round_tool_choice = tool_choice if (tools and round_idx == 0) else None
            if native:
                payload: Dict[str, Any] = {
                    "model": self.model,
                    "messages": history,
                    "stream": False,
                    "think": bool(think),
                    "options": {"num_predict": self.max_output_tokens},
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = round_tool_choice or "auto"
                data = await self._post(payload, endpoint=self._native_api_url("/api/chat"))
                message = data["message"]
                prompt_tokens += data.get("prompt_eval_count") or 0
                completion_tokens += data.get("eval_count") or 0
            else:
                payload = {
                    "model": self.model,
                    "messages": history,
                    "max_tokens": self.max_output_tokens,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = round_tool_choice or "auto"
                data = await self._post(payload)
                message = data["choices"][0]["message"]
                usage = data.get("usage") or {}
                prompt_tokens += usage.get("prompt_tokens") or 0
                completion_tokens += usage.get("completion_tokens") or 0

            tool_calls = message.get("tool_calls") or []

            if not tool_calls or tool_executor is None:
                logger.info(
                    "llm=chat provider=ollama model=%s rounds=%s tool_calls=%s duration_ms=%s "
                    "prompt_tokens=%s completion_tokens=%s",
                    self.model,
                    round_idx + 1,
                    len(executed_calls),
                    round((time.perf_counter() - started) * 1000),
                    prompt_tokens,
                    completion_tokens,
                )
                return ChatResult(
                    content=message.get("content") or "",
                    tool_calls=executed_calls,
                    rounds=round_idx + 1,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
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
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
    ) -> Any:
        """One-shot structured generation, with the schema handed to Ollama as
        a real constraint rather than prose.

        The previous version embedded the schema in the prompt ("respond with
        a JSON object matching this JSON Schema exactly") under
        `response_format: json_object`, which only guarantees *valid* JSON.
        Small local models took the instruction literally and echoed the
        schema envelope back — `{"type": "object", "properties": {"claims":
        [...]}}` instead of `{"claims": [...]}`. Callers read `payload["claims"]`,
        found nothing, and degraded to an empty report, so claim verification
        silently passed everything while appearing to run. `json_schema`
        constrains decoding to the schema, so that shape can no longer drift.

        The schema stays in the prompt as well. Dropping it (it is redundant
        for *shape* once decoding is constrained) measurably degraded the
        judgment the call is being asked for: the intent router started
        picking `drug_safety` for questions it had answered as `evidence`.
        The schema names its own enum values, so it reads as task context,
        not just formatting — worth the tokens."""
        instructed_prompt = (
            f"{prompt}\n\nRespond with a single JSON object matching this JSON Schema "
            f"exactly (no prose, no markdown fences):\n{json.dumps(schema)}"
        )
        messages = self._to_messages([{"role": "user", "content": instructed_prompt}], system_prompt)
        # Deterministic sampling (temperature 0): this is a classification/
        # extraction call (claim verification, dynamic routing), not creative
        # generation — the default sampling temperature let the same claim
        # flip between "supported" and "unsupported" across otherwise-
        # identical runs. `think: False` matters here too — the intent router
        # and claim verifier both call this on every consultation, and a
        # hybrid-reasoning model's default reasoning pass turns a one-shot
        # classification into the slowest step in the pipeline (see module
        # docstring); native `/api/chat` is the only endpoint that honors it.
        if _is_local_endpoint(self.base_url):
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": schema,
                "options": {"temperature": 0, "num_predict": self.max_output_tokens},
            }
            data = await self._post(payload, endpoint=self._native_api_url("/api/chat"))
            return json.loads(data["message"]["content"])

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema},
            },
            "max_tokens": self.max_output_tokens,
            "temperature": 0,
        }
        data = await self._post(payload)
        return json.loads(data["choices"][0]["message"]["content"])

    def _native_api_url(self, path: str) -> str:
        """Ollama's OpenAI-compat shim (`/v1/chat/completions`, used by `_post`)
        has known inconsistent support for the `image_url` content-part shape —
        against this install/model it silently drops the image and the model
        replies "I can't see any image attached", so vision goes through
        Ollama's native `/api/...` API instead, which takes images via a
        top-level `images: [base64]` array. `base_url` is the OpenAI-compat
        root (e.g. "http://localhost:11434/v1"); strip that suffix to reach
        the native root."""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}{path}"

    def _vision_payload_native(
        self, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int
    ) -> Dict[str, Any]:
        image_bytes, _ = _downscale_for_vision(image_bytes, mime_type)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        return {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "options": {
                "num_ctx": 8192,
                # Low, not creative-generation default: an unconstrained sampling
                # temperature on a small local VLM measurably increases invented
                # findings (colored "hyperintensity" regions on a grayscale MRI,
                # phantom masses) on a task that must describe only what's visible.
                "temperature": 0.1,
                "num_predict": max_output_tokens,
            },
        }

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        """Opt-in only, via `vision_model` (unset by default) — pass a
        vision-capable local model id (e.g. "qwen2.5vl:7b", pulled separately
        with `ollama pull`)."""
        if not self.vision_model:
            raise LLMUnavailableError(
                "OllamaClient has no vision_model configured — set ollama_vision_model "
                "and `ollama pull` a vision-capable model."
            )
        payload = {
            **self._vision_payload_native(image_bytes, mime_type, prompt, max_output_tokens),
            "stream": False,
        }
        try:
            response = await self._client.post(self._native_api_url("/api/chat"), json=payload)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(str(exc)) from exc
        if response.status_code >= 400:
            raise LLMUnavailableError(f"{response.status_code}: {response.text}")
        return (response.json()["message"].get("content") or "").strip()

    async def describe_image_stream(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ):
        """Streaming counterpart to `describe_image` — same opt-in
        `vision_model` gate and native-API rationale as `_native_api_url`.
        No retry loop, matching `GeminiClient.describe_image_stream`'s own
        rationale: a stream that fails mid-flight can't transparently retry
        without replaying already-yielded chunks. Native `/api/chat` streams
        newline-delimited JSON objects (no `data: ` prefix, no `[DONE]`
        sentinel) — each line is `{"message": {"content": "..."}, "done": bool}`."""
        if not self.vision_model:
            raise LLMUnavailableError(
                "OllamaClient has no vision_model configured — set ollama_vision_model "
                "and `ollama pull` a vision-capable model."
            )
        payload = {
            **self._vision_payload_native(image_bytes, mime_type, prompt, max_output_tokens),
            "stream": True,
        }
        try:
            async with self._client.stream(
                "POST", self._native_api_url("/api/chat"), json=payload
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMUnavailableError(f"{response.status_code}: {body.decode(errors='replace')}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(str(exc)) from exc

    def describe(self) -> ProviderInfo:
        """Local *unless* pointed elsewhere.

        `base_url` is documented as retargetable at OpenRouter's
        OpenAI-compatible endpoint, so locality is a property of this instance,
        not of the class. Reporting a hosted endpoint as local would be the
        same untruth SPEC-022 exists to remove, just told by a different field.
        """
        from urllib.parse import urlsplit

        return ProviderInfo(
            provider="ollama",
            model=self.model,
            vision_model=self.vision_model or "",
            local=_is_local_endpoint(self.base_url),
            endpoint=urlsplit(self.base_url).hostname or "",
        )

    async def health(self) -> bool:
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["DEFAULT_MAX_TOOL_ROUNDS", "OllamaClient"]
