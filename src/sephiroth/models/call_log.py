"""Records every call a provider client makes: one log line, and one `LlmCall`
on the active run's trace.

Applied to the public methods of the *leaf* clients (Gemini, Groq, Ollama), not
to the composites. `FallbackLLMClient` and `VisionSplitClient` only delegate, so
decorating them would record each call twice and, worse, attribute it to the
composite: the whole point is to say which provider actually answered.

Metadata only. The log line and the record carry the provider, the model, the
timing, the token counts and a reason *code*; never the prompt, the answer, the
tool arguments or the provider's error text.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, Optional

from sephiroth.contracts import LlmCall
from sephiroth.telemetry.context import current_fallback, record_call

from .base import LLMUnavailableError, classify_unavailable

logger = logging.getLogger("sephiroth.llm")

_VISION_KINDS = frozenset({"describe_image", "describe_image_stream"})


def _identify(client: Any, kind: str) -> tuple[str, str]:
    """(provider, model) this call is served by. A vision call uses the
    client's vision model, which can differ from its chat model."""
    info = client.describe()
    model = (info.vision_model or info.model) if kind in _VISION_KINDS else info.model
    return info.provider, model


def _emit(
    client: Any,
    kind: str,
    started: float,
    *,
    ok: bool,
    error: str = "",
    result: Optional[Any] = None,
) -> None:
    provider, model = _identify(client, kind)
    fallback = current_fallback()
    prompt_tokens = int(getattr(result, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(result, "completion_tokens", 0) or 0)
    duration_ms = round((time.perf_counter() - started) * 1000)

    record_call(
        LlmCall(
            kind=kind,  # type: ignore[arg-type]
            provider=provider,
            model=model,
            ok=ok,
            error=error,
            fallback=fallback is not None,
            fallback_from=fallback[0] if fallback else "",
            fallback_reason=fallback[1] if fallback else "",
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )

    parts = [
        f"llm={kind}",
        f"provider={provider}",
        f"model={model}",
        f"fallback={'true' if fallback else 'false'}",
        f"status={'ok' if ok else 'error'}",
        f"duration_ms={duration_ms}",
        f"prompt_tokens={prompt_tokens}",
        f"completion_tokens={completion_tokens}",
    ]
    if kind == "chat" and result is not None:
        parts += [
            f"rounds={getattr(result, 'rounds', 0)}",
            f"tool_calls={len(getattr(result, 'tool_calls', []) or [])}",
        ]
    if fallback:
        parts += [f"fallback_from={fallback[0]}", f"fallback_reason={fallback[1]}"]
    if not ok:
        parts.append(f"reason={error}")
    logger.log(logging.INFO if ok else logging.WARNING, " ".join(parts))


def _failure_code(exc: BaseException) -> str:
    if isinstance(exc, LLMUnavailableError):
        return classify_unavailable(exc)
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    return "internal_error"


def record_llm_call(kind: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a client method (`chat`, `generate_json`, `describe_image`,
    `describe_image_stream`) so each call is recorded once, success or not.

    The original exception always propagates unchanged: recording must never
    change what a caller sees, since `FallbackLLMClient` depends on
    `LLMUnavailableError` reaching it.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.isasyncgenfunction(fn):

            @functools.wraps(fn)
            async def stream(self: Any, *args: Any, **kwargs: Any):
                started = time.perf_counter()
                ok, error = True, ""
                try:
                    async for chunk in fn(self, *args, **kwargs):
                        yield chunk
                except GeneratorExit:
                    # The consumer stopped reading. Nothing failed.
                    raise
                except BaseException as exc:
                    ok, error = False, _failure_code(exc)
                    raise
                finally:
                    _emit(self, kind, started, ok=ok, error=error)

            return stream

        @functools.wraps(fn)
        async def call(self: Any, *args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                result = await fn(self, *args, **kwargs)
            except BaseException as exc:
                _emit(self, kind, started, ok=False, error=_failure_code(exc))
                raise
            _emit(self, kind, started, ok=True, result=result)
            return result

        return call

    return decorate


__all__ = ["record_llm_call"]
