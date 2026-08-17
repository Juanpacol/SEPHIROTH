"""New Phase 2 capabilities on the tool runtime: per-call timeout and
capability tags.

The dispatcher itself (`load`/`llm_tools`/`system_prompt_summary`/
`scoped_executor`) is a straight relocation of `MCPRegistry` — its behavior is
characterized by `tests/test_mcp.py`, `test_mcp_extra.py`, and
`test_tool_authorization.py`, which run unmodified against the shim. This file
covers only what's new.

Verifies AC-002-01, AC-002-02 (`docs/specs/SPEC-002-tool-runtime.md`).
"""

import asyncio

import pytest
from fastmcp import FastMCP

from sephiroth.tools import ToolRuntime, get_tool_runtime

pytestmark = pytest.mark.contract

_slow_mcp = FastMCP(name="slow-test-server")


@_slow_mcp.tool
async def slow_tool(seconds: float) -> dict:
    await asyncio.sleep(seconds)
    return {"ok": True}


@pytest.fixture
async def slow_registry():
    registry = ToolRuntime(servers=[_slow_mcp])
    await registry.load()
    return registry


async def test_execute_returns_error_on_timeout_instead_of_hanging(slow_registry, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "tool_call_timeout_seconds", 0.05)

    result = await slow_registry.execute("slow_tool", {"seconds": 5})

    assert "error" in result
    assert "timed out" in result["error"]
    assert "slow_tool" in result["error"]


async def test_execute_within_timeout_succeeds(slow_registry, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "tool_call_timeout_seconds", 5.0)

    result = await slow_registry.execute("slow_tool", {"seconds": 0.01})

    assert result == {"ok": True}


async def test_timeout_does_not_raise_to_the_caller(slow_registry, monkeypatch):
    """B-1: a timeout must degrade to the same error-result shape every other
    tool failure uses, never propagate as an exception."""
    from core.config import settings

    monkeypatch.setattr(settings, "tool_call_timeout_seconds", 0.01)

    # No pytest.raises — the point is that nothing raises.
    result = await slow_registry.execute("slow_tool", {"seconds": 1})
    assert isinstance(result, dict)
    assert "error" in result


@pytest.fixture
async def real_registry():
    registry = get_tool_runtime()
    await registry.load()
    return registry


@pytest.mark.parametrize(
    "tool_name,expected_tags",
    [
        ("check_drug_interactions", ["medication_interaction", "drug_safety"]),
        ("inspect_medical_image", ["imaging_metadata"]),
        ("analyze_medical_image", ["imaging_analysis"]),
        ("describe_medical_image", ["imaging_analysis", "vision"]),
        ("extract_medical_entities", ["clinical_nlp"]),
        ("summarize_clinical_note", ["clinical_nlp"]),
        ("search_clinical_guidelines", ["evidence_retrieval"]),
        ("search_pubmed", ["evidence_retrieval"]),
    ],
)
async def test_tags_for_known_tools(real_registry, tool_name, expected_tags):
    assert real_registry.tags_for(tool_name) == expected_tags


async def test_tags_for_unknown_tool_returns_empty_list(real_registry):
    assert real_registry.tags_for("no_such_tool") == []


async def test_tags_for_never_raises_on_untagged_but_real_name(real_registry):
    """B-2: absence from the tag dict is not an error condition."""
    assert real_registry.tags_for("") == []
