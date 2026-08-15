"""
Gemini client with a tool-calling loop.

Sends chat requests to the Google Gemini API (AI Studio free tier) using its
native ``function_declarations`` tools. When the model responds with function
calls, they are executed through the MCP registry and the results are fed
back as ``functionResponse`` parts until the model produces a plain assistant
answer. Mirrors the contract the local Ollama client used to expose, so
callers (agents, timeline extraction, vision) did not need to change shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# A tool executor receives (tool_name, arguments) and returns the tool output.
ToolExecutor = Callable[[str, Dict[str, Any]], Awaitable[Any]]

DEFAULT_MAX_TOOL_ROUNDS = 6
_HEALTH_CACHE_TTL_SECONDS = 60.0


class LLMUnavailableError(RuntimeError):
    """Raised when Gemini cannot be reached (no key, quota exhausted, network)."""


@dataclass
class ChatResult:
    """Final result of a chat exchange, including the tool-call trace."""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


def _jsonable(value: Any) -> Dict[str, Any]:
    """Coerce an arbitrary tool result into a JSON-serializable dict, as
    required by `Part.from_function_response`."""
    normalized = json.loads(json.dumps(value, default=str))
    if isinstance(normalized, dict):
        return normalized
    return {"result": normalized}


def _to_contents(messages: List[Dict[str, Any]]) -> List[types.Content]:
    """Map {"role","content"} dicts to Gemini `Content` objects.

    Gemini has no "system" role in `contents` (system prompts go in
    `config.system_instruction`) and calls the assistant role "model".
    """
    contents: List[types.Content] = []
    for message in messages:
        role = message.get("role", "user")
        if role == "system":
            continue  # handled via system_instruction by the caller
        gemini_role = "model" if role == "assistant" else "user"
        part = types.Part.from_text(text=message.get("content", ""))
        contents.append(types.Content(role=gemini_role, parts=[part]))
    return contents


def _to_gemini_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[types.Tool]]:
    """Convert OpenAI-style function schemas (as produced by the MCP
    registry) into a single Gemini `Tool` with N function declarations."""
    if not tools:
        return None
    declarations = []
    for entry in tools:
        fn = entry["function"]
        declarations.append(
            types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                # `parameters_json_schema` accepts raw JSON Schema (including
                # $defs/$ref/additionalProperties/oneOf) — no manual
                # sanitization needed, unlike the older `parameters` field.
                parameters_json_schema=_sanitize_schema(fn.get("parameters")),
            )
        )
    if not declarations:
        return None
    return [types.Tool(function_declarations=declarations)]


def _sanitize_schema(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Light cleanup for the few JSON Schema constructs Gemini's
    `*_json_schema` fields don't accept, per the field's own documentation:
    `const` (not listed), `exclusiveMinimum`/`exclusiveMaximum` (not listed),
    and a bare `$schema` marker. Everything else ($defs, $ref,
    additionalProperties, oneOf/anyOf, enum, items, required, ...) passes
    through untouched."""
    if not schema or not isinstance(schema, dict):
        return None

    def _clean(node: Any) -> Any:
        if isinstance(node, dict):
            out: Dict[str, Any] = {}
            for key, value in node.items():
                if key in ("$schema", "exclusiveMinimum", "exclusiveMaximum"):
                    continue
                if key == "const":
                    out["enum"] = [value]
                    continue
                out[key] = _clean(value)
            return out
        if isinstance(node, list):
            return [_clean(item) for item in node]
        return node

    cleaned = _clean(schema)
    if cleaned.get("type") == "object" and not cleaned.get("properties"):
        return None
    return cleaned


def _extract_text(response: types.GenerateContentResponse) -> str:
    try:
        text = response.text
    except Exception:  # some finish reasons (SAFETY, RECITATION) have no text
        text = None
    if text:
        return text
    candidate = response.candidates[0] if response.candidates else None
    finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
    if finish_reason and str(finish_reason) not in ("STOP", "FinishReason.STOP"):
        logger.warning("gemini response had no text; finish_reason=%s", finish_reason)
        return f"[No answer produced — finish_reason={finish_reason}. Professional review required.]"
    return ""


class GeminiClient:
    """Thin wrapper around `google-genai` with an MCP tool loop."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        vision_model: Optional[str] = None,
        max_output_tokens: int = 2048,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        rpm_limit: int = 10,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        time_source: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.model = model
        self.vision_model = vision_model or model
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.rpm_limit = rpm_limit
        self.max_tool_rounds = max_tool_rounds
        self._time_source = time_source
        self._sleep = sleep
        self._request_times: List[float] = []
        self._health_cache: Optional[bool] = None
        self._health_cache_at: float = 0.0

        self._client: Optional[genai.Client] = None
        if api_key:
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
            )

    async def _throttle(self) -> None:
        """Cooperative token bucket: block until under `rpm_limit` requests
        in the trailing 60s window."""
        window = 60.0
        while True:
            now = self._time_source()
            self._request_times = [t for t in self._request_times if now - t < window]
            if len(self._request_times) < self.rpm_limit:
                self._request_times.append(now)
                return
            wait_for = window - (now - self._request_times[0])
            await self._sleep(max(wait_for, 0.05))

    async def _generate(self, contents: List[types.Content], config: types.GenerateContentConfig):
        if self._client is None:
            raise LLMUnavailableError("GEMINI_API_KEY is not configured.")

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            await self._throttle()
            try:
                return await self._client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) + random.uniform(0, 1)
                    logger.warning("gemini rate-limited (429), retrying in %.1fs", delay)
                    await self._sleep(delay)
                    last_exc = exc
                    continue
                raise LLMUnavailableError(str(exc)) from exc
            except errors.ServerError as exc:
                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) + random.uniform(0, 1)
                    logger.warning("gemini server error, retrying in %.1fs", delay)
                    await self._sleep(delay)
                    last_exc = exc
                    continue
                raise LLMUnavailableError(str(exc)) from exc
        raise LLMUnavailableError(str(last_exc) if last_exc else "gemini request failed")

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
            system_prompt: passed as `config.system_instruction`.
            tools: tool schemas in OpenAI/Ollama function-calling format
                (as produced by the MCP registry).
            tool_executor: async callable that executes a named tool.
            think: extended-reasoning mode. Off by default — it multiplies
                latency and token usage against the free-tier quota.
        """
        contents = _to_contents(messages)
        gemini_tools = _to_gemini_tools(tools)

        config_kwargs: Dict[str, Any] = dict(
            system_instruction=system_prompt,
            max_output_tokens=self.max_output_tokens,
            tools=gemini_tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            safety_settings=[
                types.SafetySetting(category=cat, threshold="BLOCK_ONLY_HIGH")
                for cat in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )
            ],
        )
        if gemini_tools:
            config_kwargs["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )
        if think:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=-1)
        else:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        executed_calls: List[Dict[str, Any]] = []
        started = time.perf_counter()

        for round_idx in range(self.max_tool_rounds):
            try:
                response = await self._generate(contents, types.GenerateContentConfig(**config_kwargs))
            except LLMUnavailableError:
                if "thinking_config" in config_kwargs:
                    # Some models/regions reject thinking_config outright.
                    config_kwargs.pop("thinking_config")
                    response = await self._generate(contents, types.GenerateContentConfig(**config_kwargs))
                else:
                    raise

            candidate = response.candidates[0] if response.candidates else None
            parts = candidate.content.parts if candidate and candidate.content else []
            function_calls = [p.function_call for p in (parts or []) if getattr(p, "function_call", None)]

            if not function_calls or tool_executor is None:
                logger.info(
                    "llm=chat model=%s rounds=%s tool_calls=%s duration_ms=%s",
                    self.model,
                    round_idx + 1,
                    len(executed_calls),
                    round((time.perf_counter() - started) * 1000),
                )
                return ChatResult(
                    content=_extract_text(response),
                    tool_calls=executed_calls,
                    rounds=round_idx + 1,
                )

            contents.append(candidate.content)
            response_parts = []
            for call in function_calls:
                name = call.name
                args = dict(call.args or {})
                logger.info("Tool call: %s(%s)", name, args)
                try:
                    result = await tool_executor(name, args)
                except Exception as exc:  # surface tool failures to the model
                    result = {"error": str(exc)}
                    logger.exception("Tool %s failed", name)

                executed_calls.append({"name": name, "arguments": args, "result": result})
                response_parts.append(
                    types.Part.from_function_response(name=name, response=_jsonable(result))
                )

            contents.append(types.Content(role="user", parts=response_parts))

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
        """One-shot structured generation: the response is forced to match
        `schema` (JSON Schema) via Gemini's `response_json_schema`."""
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=_sanitize_schema(schema),
            max_output_tokens=max(self.max_output_tokens, 4096),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        started = time.perf_counter()
        response = await self._generate(contents, config)
        logger.info(
            "llm=generate_json model=%s duration_ms=%s",
            self.model,
            round((time.perf_counter() - started) * 1000),
        )
        return json.loads(response.text)

    async def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        max_output_tokens: int = 512,
    ) -> str:
        """One-shot multimodal description of a rendered medical image."""
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part.from_text(text=prompt),
                ],
            )
        ]
        config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if self._client is None:
            raise LLMUnavailableError("GEMINI_API_KEY is not configured.")

        last_exc: Optional[Exception] = None
        model = self.vision_model
        for attempt in range(self.max_retries):
            await self._throttle()
            try:
                response = await self._client.aio.models.generate_content(
                    model=model, contents=contents, config=config
                )
                return _extract_text(response).strip()
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) + random.uniform(0, 1)
                    await self._sleep(delay)
                    last_exc = exc
                    continue
                raise LLMUnavailableError(str(exc)) from exc
            except errors.ServerError as exc:
                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 30) + random.uniform(0, 1)
                    await self._sleep(delay)
                    last_exc = exc
                    continue
                raise LLMUnavailableError(str(exc)) from exc
        raise LLMUnavailableError(str(last_exc) if last_exc else "gemini vision request failed")

    async def health(self) -> bool:
        """Return True when Gemini is reachable, the API key is valid, and
        `self.model` exists. Cached for 60s — called on every dashboard load
        and every /consult."""
        if self._client is None:
            return False
        now = self._time_source()
        if self._health_cache is not None and (now - self._health_cache_at) < _HEALTH_CACHE_TTL_SECONDS:
            return self._health_cache
        try:
            await asyncio.wait_for(self._client.aio.models.get(model=self.model), timeout=5)
            ok = True
        except Exception:
            ok = False
        self._health_cache = ok
        self._health_cache_at = now
        return ok
