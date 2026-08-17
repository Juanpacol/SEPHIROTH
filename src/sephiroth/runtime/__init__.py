"""The agent runtime — Analyzer, Planner, Router, Executor.

Replaces `intelligence/agents/workflow.py`'s LangGraph-compiled graph. See
`docs/specs/SPEC-003-agent-runtime.md` and `docs/08-decisions/ADR-001-remove-langgraph.md`.
"""

from .executor import run_consultation, stream_consultation
from .planner import SPECIALISTS, route_specialists, route_specialists_dynamic

__all__ = [
    "SPECIALISTS",
    "route_specialists",
    "route_specialists_dynamic",
    "run_consultation",
    "stream_consultation",
]
