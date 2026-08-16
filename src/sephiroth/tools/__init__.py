"""The tool runtime — capability-tagged, timeout-bounded MCP dispatch.

See `docs/specs/SPEC-002-tool-runtime.md`.
"""

from .runtime import ToolRuntime, get_tool_runtime
from .servers import SERVERS, TOOL_CAPABILITIES

__all__ = ["SERVERS", "TOOL_CAPABILITIES", "ToolRuntime", "get_tool_runtime"]
