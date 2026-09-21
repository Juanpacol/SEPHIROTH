"""The agent runtime — Registry, Intent Router, Executor.

Replaces `intelligence/agents/workflow.py`'s LangGraph-compiled graph. See
`docs/specs/SPEC-003-agent-runtime.md`, `docs/08-decisions/ADR-001-remove-langgraph.md`,
and `docs/specs/SPEC-029-agent-consolidation.md` (Phase 14: the multi-agent
fan-out — Planner, Router, the dynamic planner — was removed; a consultation
always routes to exactly one specialist via `intent_router`).
"""

from .executor import run_consultation, stream_consultation

__all__ = [
    "run_consultation",
    "stream_consultation",
]
