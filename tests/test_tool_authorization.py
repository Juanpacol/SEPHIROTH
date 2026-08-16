"""Tool authorization is enforced at dispatch, not just at advertisement.

Before this gate, `MCPAgent.run()` handed the model `registry.execute` — the
raw dispatcher, which checks only that a tool *exists*. The `allowed_tools`
whitelist merely filtered which schemas the model was *shown*. A model that
named a tool outside its scope, whether through hallucination or prompt
injection in clinical text, had it executed.

In a clinical application that is a live security defect, so it is closed
ahead of the Tool Runtime phase and locked here. The design is lifted into
`sephiroth.tools` in Phase 2; these assertions move with it.
"""

from typing import Any, Dict, List

import pytest

from intelligence.agents import DrugSafetyAgent, EvidenceAgent
from sephiroth.tools import get_tool_runtime
from tests.conftest import FakeLLMClient

pytestmark = pytest.mark.contract

EVIDENCE_TOOLS = ["search_clinical_guidelines", "search_pubmed"]
OUT_OF_SCOPE = "check_drug_interactions"  # real tool, wrong agent


@pytest.fixture
async def registry():
    reg = get_tool_runtime()
    await reg.load()
    return reg


async def test_in_scope_tool_executes(registry):
    execute = registry.scoped_executor(EVIDENCE_TOOLS)
    result = await execute("search_clinical_guidelines", {"query": "type 2 diabetes"})

    assert isinstance(result, dict)
    assert "error" not in result


async def test_out_of_scope_tool_is_refused(registry):
    execute = registry.scoped_executor(EVIDENCE_TOOLS)
    result = await execute(OUT_OF_SCOPE, {"medications": ["warfarin", "aspirin"]})

    assert result == {"error": f"Tool not authorized for this agent: {OUT_OF_SCOPE}"}


async def test_out_of_scope_tool_never_reaches_its_server(registry, monkeypatch):
    """The refusal must happen *before* dispatch. Returning an error while
    still having run the tool would leak exactly what the check exists to stop."""
    dispatched: List[str] = []

    async def spy(tool_name: str, arguments: Dict[str, Any]) -> Any:
        dispatched.append(tool_name)
        return {"ok": True}

    monkeypatch.setattr(registry, "execute", spy)

    execute = registry.scoped_executor(EVIDENCE_TOOLS)
    await execute(OUT_OF_SCOPE, {})
    assert dispatched == [], f"unauthorized tool was dispatched: {dispatched}"

    await execute("search_clinical_guidelines", {"query": "x"})
    assert dispatched == ["search_clinical_guidelines"]


async def test_empty_scope_authorizes_nothing(registry, monkeypatch):
    dispatched: List[str] = []

    async def spy(tool_name: str, arguments: Dict[str, Any]) -> Any:
        dispatched.append(tool_name)
        return {}

    monkeypatch.setattr(registry, "execute", spy)

    execute = registry.scoped_executor([])
    result = await execute("search_clinical_guidelines", {"query": "x"})

    assert "error" in result
    assert dispatched == []


async def test_none_scope_is_unrestricted(registry, monkeypatch):
    """`allowed_tools = None` means "no tool whitelist declared". `LabAgent`
    uses it to work purely from patient context, and `registry.llm_tools(None)`
    already means unrestricted — the executor must agree, or the two halves of
    the contract disagree."""
    dispatched: List[str] = []

    async def spy(tool_name: str, arguments: Dict[str, Any]) -> Any:
        dispatched.append(tool_name)
        return {}

    monkeypatch.setattr(registry, "execute", spy)

    await registry.scoped_executor(None)("search_clinical_guidelines", {"query": "x"})
    assert dispatched == ["search_clinical_guidelines"]


async def test_unknown_tool_still_reports_unknown(registry):
    """An in-scope-but-nonexistent name is a different failure from an
    unauthorized one, and the model should be able to tell them apart."""
    execute = registry.scoped_executor(["no_such_tool"])
    result = await execute("no_such_tool", {})

    assert result == {"error": "Unknown tool: no_such_tool"}


async def test_agent_calling_out_of_scope_tool_degrades_gracefully():
    """End-to-end through the agent: an unauthorized call must come back as a
    tool result the model can react to, not an exception that kills the run."""
    client = FakeLLMClient(
        default_script=[
            ("tool", OUT_OF_SCOPE, {"medications": ["warfarin"]}),
            ("answer", "I could not access that tool."),
        ]
    )

    result = await EvidenceAgent(client).run("check interactions")

    assert result.content == "I could not access that tool."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["result"] == {"error": f"Tool not authorized for this agent: {OUT_OF_SCOPE}"}


async def test_each_agent_can_call_its_own_declared_tools():
    """The enforcement must not be so tight that it breaks real behaviour —
    the failure mode that would otherwise surface only in the eval job."""
    client = FakeLLMClient(
        default_script=[
            ("tool", "check_drug_interactions", {"medications": ["warfarin", "aspirin"]}),
            ("answer", "Interaction found."),
        ]
    )

    result = await DrugSafetyAgent(client).run("screen these medications")

    assert result.tool_calls[0]["result"] is not None
    assert "error" not in (result.tool_calls[0]["result"] or {})


async def test_permissive_mode_logs_but_allows(registry, monkeypatch, caplog):
    """The two-commit rollout pattern: permissive mode reports what enforcement
    *would* block, so a real dependency on the hole is discovered from logs
    rather than from a broken consultation."""
    from core.config import settings

    monkeypatch.setattr(settings, "enforce_tool_authorization", False)

    dispatched: List[str] = []

    async def spy(tool_name: str, arguments: Dict[str, Any]) -> Any:
        dispatched.append(tool_name)
        return {"ok": True}

    monkeypatch.setattr(registry, "execute", spy)

    with caplog.at_level("WARNING", logger="intelligence.mcp.registry"):
        result = await registry.scoped_executor(EVIDENCE_TOOLS)(OUT_OF_SCOPE, {})

    assert result == {"ok": True}, "permissive mode must still execute"
    assert dispatched == [OUT_OF_SCOPE]
    assert any("tool_authorization_denied" in r.message for r in caplog.records)
