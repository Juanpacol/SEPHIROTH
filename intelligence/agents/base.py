"""DEPRECATED — moved to `sephiroth.runtime.agent` in Phase 3.

This module re-exports for backward compatibility only. See
`docs/specs/SPEC-003-agent-runtime.md` and
`docs/00-migration-charter.md` §3 for the shim schedule.
"""

from sephiroth.runtime.agent import MEDICAL_DISCLAIMER, Agent

MCPAgent = Agent

__all__ = ["MCPAgent", "MEDICAL_DISCLAIMER"]
