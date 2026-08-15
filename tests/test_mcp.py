"""MCP registry + tool tests — registry discovery/dispatch and the
offline-safe tools (guideline search, drug interactions, PubMed fallback)."""

import httpx
import pytest

from intelligence.mcp import rag_server
from intelligence.mcp.drug_safety_server import find_interactions
from intelligence.mcp.registry import MCPRegistry, get_registry


@pytest.mark.asyncio
async def test_registry_singleton_returns_same_instance():
    assert get_registry() is get_registry()


@pytest.mark.asyncio
async def test_registry_load_is_idempotent():
    registry = MCPRegistry()
    await registry.load()
    tool_count = len(registry._schemas)
    await registry.load()
    assert len(registry._schemas) == tool_count


@pytest.mark.asyncio
async def test_registry_discovers_expected_tools():
    registry = MCPRegistry()
    await registry.load()
    names = {s["function"]["name"] for s in registry.llm_tools()}
    assert "search_clinical_guidelines" in names
    assert "check_drug_interactions" in names
    assert "search_pubmed" in names


@pytest.mark.asyncio
async def test_llm_tools_filters_to_allowed():
    registry = MCPRegistry()
    await registry.load()
    filtered = registry.llm_tools(["check_drug_interactions"])
    assert len(filtered) == 1
    assert filtered[0]["function"]["name"] == "check_drug_interactions"


@pytest.mark.asyncio
async def test_system_prompt_summary_mentions_tool_names():
    registry = MCPRegistry()
    await registry.load()
    summary = registry.system_prompt_summary(["check_drug_interactions"])
    assert "check_drug_interactions" in summary


@pytest.mark.asyncio
async def test_execute_search_clinical_guidelines_real_offline():
    registry = MCPRegistry()
    await registry.load()
    result = await registry.execute(
        "search_clinical_guidelines", {"query": "A1C goal type 2 diabetes", "top_k": 1}
    )
    assert result["results"]
    assert result["results"][0]["id"] == "ada-2024-hba1c"


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error():
    registry = MCPRegistry()
    await registry.load()
    result = await registry.execute("not_a_real_tool", {})
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_check_drug_interactions_known_pair():
    registry = MCPRegistry()
    await registry.load()
    result = await registry.execute("check_drug_interactions", {"medications": ["warfarin", "aspirin"]})
    assert result["interactions_found"] == 1
    assert result["interactions"][0]["severity"] == "major"


def test_find_interactions_known_pair():
    # warfarin+aspirin is hand-curated (major); warfarin+metformin is a real,
    # additional pair merged in from the DDInter 2.0 real-data extension
    # (real_data/drug_interactions/ddinter_subset.json) — both are expected.
    findings = find_interactions(["warfarin", "aspirin", "metformin"])
    pairs = {frozenset(f["pair"]) for f in findings}
    assert frozenset(["warfarin", "aspirin"]) in pairs
    assert frozenset(["warfarin", "metformin"]) in pairs
    assert len(findings) == 2


def test_find_interactions_no_known_pair():
    # Neither drug appears in the hand-curated table nor in the DDInter
    # real-data subset — guaranteed no match regardless of dataset growth.
    assert find_interactions(["biotin", "folic acid"]) == []


def test_find_interactions_case_insensitive():
    findings = find_interactions(["Warfarin", "ASPIRIN"])
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_search_pubmed_falls_back_gracefully_when_unreachable(monkeypatch):
    class _BoomClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            raise httpx.ConnectError("network unreachable")

    monkeypatch.setattr(rag_server.httpx, "AsyncClient", lambda **kwargs: _BoomClient())

    result = await rag_server.search_pubmed("diabetes treatment")
    assert result["results"] == []
    assert "error" in result
