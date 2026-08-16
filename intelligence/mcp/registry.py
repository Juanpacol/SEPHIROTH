"""DEPRECATED — moved to `sephiroth.tools` in Phase 2.

This module re-exports for backward compatibility only. Removed in Phase 3
per the shim schedule in `docs/00-migration-charter.md` §3. See
`docs/specs/SPEC-002-tool-runtime.md`.
"""

from sephiroth.tools import get_tool_runtime as get_registry
from sephiroth.tools.runtime import ToolRuntime as MCPRegistry

__all__ = ["MCPRegistry", "get_registry"]
