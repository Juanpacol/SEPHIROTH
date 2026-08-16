"""Task analysis — the boolean signals a plan is built from.

Moved out of `route_specialists`'s inline `context.get(...)` checks
(`docs/specs/SPEC-003-agent-runtime.md`) so the planner reasons over named
signals instead of reaching into a raw dict directly. The three signals are
exactly the three conditions `route_specialists` checked before this phase —
no new signal is added here; that is `planner.py`'s job when a dynamic planner
is introduced in a later phase.
"""

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
