"""Which model served a consultation, read from its persisted trace.

Shared by the review endpoint (`routers/review.py`) and the quality queue
(`routers/quality.py`) so both say the same thing about the same row.
"""

from __future__ import annotations

from typing import Any, Optional


def llm_calls(trace: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    return list((trace or {}).get("llm_calls") or [])


def answering_call(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """The last successful chat call, else the last call, else nothing."""
    chats = [c for c in calls if c.get("kind") == "chat" and c.get("ok")]
    return (chats or calls or [{}])[-1]


def provenance(trace: Optional[dict[str, Any]]) -> dict[str, Any]:
    calls = llm_calls(trace)
    answering = answering_call(calls)
    return {
        "provider": answering.get("provider", ""),
        "model": answering.get("model", ""),
        "fallback": any(c.get("fallback") for c in calls),
    }


__all__ = ["answering_call", "llm_calls", "provenance"]
