"""MCP tool layer — FastMCP servers exposing clinical capabilities as tools.

The registry/dispatcher itself lives in `sephiroth.tools` (`ToolRuntime`,
`get_tool_runtime`) since Phase 2; this package now holds only the five
FastMCP servers.
"""

from . import drug_safety_server, imaging_server, nlp_server, rag_server, vision_server  # noqa: F401
