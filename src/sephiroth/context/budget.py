"""Token budgeting / compression — F-035, part 2.

A character-count approximation, not a real tokenizer — consistent with
this project's "simplest that satisfies the spec" standard, and with how
`RAGPipeline` already avoids new dependencies for anything that doesn't
need one. Nothing here claims to count tokens exactly; it bounds prompt
growth, which is the actual problem (an unbounded coordinator prompt from
5 concatenated specialist answers, or an unbounded evidence passage).
"""

from __future__ import annotations

TRUNCATION_MARKER = "... [truncated]"


def truncate(text: str, max_chars: int) -> str:
    """Truncates `text` to at most `max_chars`, cutting at the last word
    boundary before the limit so `[truncated]` doesn't land mid-word."""
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind(" ", 0, max_chars)
    if cutoff <= 0:
        cutoff = max_chars
    return text[:cutoff].rstrip() + " " + TRUNCATION_MARKER


__all__ = ["TRUNCATION_MARKER", "truncate"]
