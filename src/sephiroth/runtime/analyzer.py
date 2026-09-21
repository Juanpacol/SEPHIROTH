"""Task analysis — the boolean signals routing is built from.

Moved out of the pre-Phase-3 router's inline `context.get(...)` checks
(`docs/specs/SPEC-003-agent-runtime.md`) so routing reasons over named
signals instead of reaching into a raw dict directly. `intent_router`'s
context-tier (`SPEC-029`) reads `has_image`/`has_medications`; `has_lab_results`
is kept for other consumers even though no live routing rule branches on it
since `laboratory` was removed (`ADR-016`)."""

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class Signals(TypedDict):
    has_image: bool
    has_lab_results: bool
    has_medications: bool


def analyze(context: Optional[Dict[str, Any]]) -> Signals:
    """Extract the routing-relevant signals from a request's context dict."""
    context = context or {}
    return Signals(
        has_image=bool(context.get("image_path")),
        has_lab_results=bool(context.get("lab_results")),
        has_medications=bool(context.get("medications")),
    )


__all__ = ["Signals", "analyze"]
