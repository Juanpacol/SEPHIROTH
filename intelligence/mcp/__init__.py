"""MCP tool layer — FastMCP servers exposing clinical capabilities as tools.

`MCPRegistry`/`get_registry` are resolved lazily (PEP 562) rather than
imported eagerly here. `sephiroth.tools.servers` imports these five server
submodules back from this package, and `.registry` (the Phase 2 shim) imports
`sephiroth.tools` — an eager import here would make the two packages depend on
each other's fully-initialized state simultaneously. Deferring the shim's
import until `MCPRegistry`/`get_registry` are actually accessed breaks that
cycle without changing what either name resolves to.
"""

from . import drug_safety_server, imaging_server, nlp_server, rag_server, vision_server  # noqa: F401

__all__ = ["MCPRegistry", "get_registry"]


def __getattr__(name: str):
    if name in ("MCPRegistry", "get_registry"):
        from . import registry

        return getattr(registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
