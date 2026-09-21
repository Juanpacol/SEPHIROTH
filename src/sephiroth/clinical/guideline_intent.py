"""The regex core shared by every "is this a guideline question?" check.

Found duplicated and already diverged during the 2026-09-20 agent-reliability
audit: `platform/api/fast_path.py::_GUIDELINE_RE` and
`sephiroth.runtime.intent_router`'s `evidence` rule each hand-maintained their
own alternation, and picked up different terms over time (`intent_router`
gained "standard of care", "indicated for", and a Spanish block; `fast_path`
never did). The two call sites have genuinely different jobs and must stay
asymmetric on purpose — `fast_path` is deliberately the *narrower* of the two
(a 0-LLM-call, verbatim top-1-document answer; its own module docstring says
it "must stay conservative about what it claims"), while `intent_router` is
deliberately the *broader* net (it only chooses which specialist reasons
about the question; a false-positive route to `evidence` is not a safety
issue the way a false-positive fast-path answer would be).

What's actually shared, and therefore lives here once: the handful of English
guideline-signal words both patterns have always agreed on. Anything either
call site wants beyond this core (phrasal patterns, Spanish, "standard of
care") stays local to that call site — this module is not trying to make the
two patterns identical, only to stop their overlapping part from being able
to drift apart unnoticed.
"""

from __future__ import annotations

#: Regex alternatives every "guideline question" check has in common.
#: `\b`-wrapped by the caller, not here, so a caller can compose this into a
#: larger alternation without doubling word-boundary anchors.
GUIDELINE_CORE_TERMS: tuple[str, ...] = (
    r"guideline\w*",
    r"first[- ]line",
    r"recommend\w*",
    r"target",
    r"threshold",
)

__all__ = ["GUIDELINE_CORE_TERMS"]
