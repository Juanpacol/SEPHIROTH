"""Per-run state shared by logging and tracing: which run is active, every
model call it has made, and whether the call in flight is a fallback.

Context variables rather than module globals or an object threaded through
every call: a run is one chain of asyncio tasks, concurrent requests each get
their own copy, and the model clients -- which do not know about runs -- can
record into whichever one is active without a new parameter on `chat`.

Leaf module on purpose: it imports only the contracts, so both the model
clients (`sephiroth.models`) and the platform's log formatter can use it
without an import cycle.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from sephiroth.contracts import LlmCall

_calls: ContextVar[Optional[list[LlmCall]]] = ContextVar("sephiroth_llm_calls", default=None)
_trace_id: ContextVar[str] = ContextVar("sephiroth_trace_id", default="")
#: (provider that failed, reason code) while a fallback call is in flight.
_fallback: ContextVar[Optional[tuple[str, str]]] = ContextVar("sephiroth_llm_fallback", default=None)


def current_trace_id() -> str:
    """The active run's trace id, or "" outside a run."""
    return _trace_id.get()


def current_fallback() -> Optional[tuple[str, str]]:
    """`(failed_provider, reason)` while a fallback call is in flight."""
    return _fallback.get()


def record_call(call: LlmCall) -> None:
    """Add a call to the active run. A no-op outside a run: a call made with no
    consultation around it (a timeline extraction, say) is still logged by the
    caller, it just has no trace to join."""
    calls = _calls.get()
    if calls is not None:
        calls.append(call)


@contextmanager
def llm_run_scope(trace_id: str) -> Iterator[list[LlmCall]]:
    """Open a run: every model call made inside is collected in the yielded
    list, and every log line emitted inside carries `trace_id`.

    Cleared on exit by *setting* the variables back instead of `reset(token)`:
    a streaming run is an async generator, and if it is closed from a different
    context (a cancelled request) `reset` raises instead of cleaning up.
    """
    calls: list[LlmCall] = []
    _calls.set(calls)
    _trace_id.set(trace_id)
    try:
        yield calls
    finally:
        _calls.set(None)
        _trace_id.set("")


@contextmanager
def fallback_scope(failed_provider: str, reason: str) -> Iterator[None]:
    """Mark every model call made inside as served by a fallback."""
    _fallback.set((failed_provider, reason))
    try:
        yield
    finally:
        _fallback.set(None)


__all__ = [
    "current_fallback",
    "current_trace_id",
    "fallback_scope",
    "llm_run_scope",
    "record_call",
]
