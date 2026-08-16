"""DEPRECATED — moved to `sephiroth.runtime` in Phase 3.

This module re-exports for backward compatibility only. The LangGraph-based
implementation this file used to contain is gone — see
`docs/08-decisions/ADR-001-remove-langgraph.md` and
`docs/specs/SPEC-003-agent-runtime.md`.
"""

from sephiroth.runtime import SPECIALISTS, route_specialists, run_consultation, stream_consultation

__all__ = ["SPECIALISTS", "route_specialists", "run_consultation", "stream_consultation"]
