"""Span recording — SPEC-006, executing `ADR-009`.

Real, live spans are recorded for exactly two of the four seams `ADR-009`
names: `Executor.step` (one span per agent turn — specialist or
coordinator) and `Verifier.check` (the claim-verification/abstention
pass). `ModelProvider.chat` and `ToolRuntime.execute` are **not**
independently instrumented this phase — see `docs/specs/SPEC-006-telemetry.md`
NG-1: `ToolRuntime` is a shared singleton with no per-request state, and
threading one through would change `ToolExecutor`'s `Callable` signature
that `FakeLLMClient` and every `scoped_executor()` call site already
depend on; and `Agent.run()` makes exactly one `chat()` call per turn
today, so the `Executor.step` span already bounds it tightly enough that a
nested `MODEL` span would just duplicate the same interval. Both are
flagged as real future seams once agents make multiple direct `chat()`
calls or tool timing becomes independently measurable without an API
change.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from core.config import settings
from sephiroth.contracts import ALLOWED_SPAN_ATTRIBUTES, RunState, Span, SpanKind


@contextmanager
def traced_span(state: RunState, kind: SpanKind, name: str, **attrs: Any) -> Iterator[None]:
    """Times the enclosed block and appends a `Span` to `state.spans`.

    A pure no-op (beyond running the block itself) when
    `settings.enable_tracing` is `False` — tracing on/off must produce an
    identical `RunState` apart from `.spans` (ADR-009's H6 requirement).
    Attributes outside the redaction allow-list are silently dropped rather
    than raising — instrumentation must never break a run over a stray
    keyword.
    """
    if not settings.enable_tracing:
        yield
        return

    started = time.monotonic()
    started_at = datetime.now(timezone.utc)
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        filtered = {k: v for k, v in attrs.items() if k in ALLOWED_SPAN_ATTRIBUTES}
        state.spans.append(
            Span(
                id=uuid.uuid4().hex,
                trace_id=state.trace_id,
                kind=kind,
                name=name,
                started_at=started_at,
                duration_ms=duration_ms,
                ok=ok,
                attributes=filtered,
            )
        )


__all__ = ["traced_span"]
