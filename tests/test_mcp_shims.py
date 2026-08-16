"""`intelligence/mcp/registry.py` is a re-export shim over `sephiroth.tools`.

Mirrors `tests/test_llm_shims.py`'s pattern from Phase 1: a shim re-exports, it
never re-implements, so the class/function reachable via the old import path
must be the exact same object as the one in the new module — not a copy, not
a subclass.

Verifies AC-002-04 (`docs/specs/SPEC-002-tool-runtime.md`).
"""

import pytest

pytestmark = pytest.mark.contract


def test_mcpregistry_is_the_same_class_as_toolruntime():
    from intelligence.mcp.registry import MCPRegistry
    from sephiroth.tools.runtime import ToolRuntime

    assert MCPRegistry is ToolRuntime


def test_get_registry_is_the_same_function_as_get_tool_runtime():
    from intelligence.mcp.registry import get_registry
    from sephiroth.tools import get_tool_runtime

    assert get_registry is get_tool_runtime


def test_get_registry_is_defined_in_the_new_module():
    """The identity check that makes the shim strategy safe — same shape as
    `tests/test_llm_shims.py::test_factory_get_llm_client_is_defined_in_the_new_module`."""
    from intelligence.mcp.registry import get_registry

    assert get_registry.__module__ == "sephiroth.tools.runtime"


def test_legacy_import_surface_matches_what_call_sites_use():
    """Every call site in the repo does `from intelligence.mcp import get_registry`
    (via `intelligence/mcp/__init__.py`, unaffected by this phase) or
    `from intelligence.mcp.registry import MCPRegistry, get_registry` directly
    (the four test modules and two example scripts). Both must keep working."""
    from intelligence.mcp.registry import MCPRegistry, get_registry

    assert callable(get_registry)
    assert isinstance(get_registry(), MCPRegistry)


def test_singleton_returned_by_either_name_is_the_same_instance():
    from intelligence.mcp.registry import get_registry as legacy_get
    from sephiroth.tools import get_tool_runtime

    assert legacy_get() is get_tool_runtime()
