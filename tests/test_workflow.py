"""Executor characterization tests — end-to-end consultation with a scripted
LLM double, citation sanitization, and SSE event order.

Runs directly against `sephiroth.runtime` (the Phase 3 executor). Originally
written against the pre-Phase-3 LangGraph workflow, then kept passing
unmodified through the `intelligence.agents.workflow` shim as the parity
proof — the shim was deleted in Phase 5 (`DEBT-010`, one phase later than
scheduled) once nothing else needed it; this module's import retargeted in
the same commit and is kept permanently as the executor's characterization
test.

SPEC-029 (Phase 14) removed the multi-agent fan-out and the dynamic planner
that only ran inside it (`route_specialists`/`route_specialists_dynamic`,
`SPEC-008`) — `run_consultation`/`stream_consultation` now always take the
single-specialist path (`intent_router` → one specialist → answer), so this
file no longer parametrizes over a mode that never runs in production.
Every test below exercises that single path, which is AC-029-07
(docs/specs/SPEC-029-agent-consolidation.md).
"""

import pytest

from sephiroth.runtime import run_consultation, stream_consultation
from tests.conftest import FakeLLMClient


@pytest.mark.asyncio
async def test_run_consultation_end_to_end_with_fake_client():
    """A single-specialist consultation must produce a cited,
    disclaimer-bearing answer — the disclaimer is appended by the executor
    itself (`_with_disclaimer`), not trusted to the model's instruction
    following."""
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                (
                    "tool",
                    "search_clinical_guidelines",
                    {"query": "diabetes A1C goal", "top_k": 5},
                ),
                (
                    "answer",
                    "Target A1C is <7% [ADA Standards of Care in Diabetes, 2024].",
                ),
            ],
        }
    )
    state = await run_consultation(client, "What A1C goal is appropriate?")

    assert "evidence" in state["agent_outputs"]
    assert state["final_answer"]
    assert "professional review" in state["final_answer"]
    assert state["citation_report"]["fabricated"] == []
    assert "ADA Standards of Care in Diabetes, 2024" in state["citation_report"]["verified"]


@pytest.mark.asyncio
async def test_run_consultation_sanitizes_fabricated_citation_in_final_answer():
    """Citation sanitization is a safety guarantee — must hold for whichever
    specialist answers."""
    fabricated = "This is backed by [Totally Fabricated Journal, 2099]."
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "x", "top_k": 5}),
                ("answer", fabricated),
            ],
        }
    )
    state = await run_consultation(client, "What about an unproven remedy?")

    assert "Totally Fabricated Journal" not in state["final_answer"]
    assert "[unverified — removed]" in state["final_answer"]
    assert "Totally Fabricated Journal, 2099" in state["citation_report"]["fabricated"]


@pytest.mark.asyncio
async def test_run_consultation_tags_tool_calls_with_agent_name():
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "x", "top_k": 5}),
                ("answer", "ok"),
            ],
        }
    )
    state = await run_consultation(client, "test query")
    agent_names = {call.get("agent") for call in state["tool_calls"]}
    assert "evidence" in agent_names


@pytest.mark.asyncio
async def test_stream_consultation_event_sequence():
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "x", "top_k": 5}),
                ("answer", "Evidence found [ADA Standards of Care in Diabetes, 2024]."),
            ],
        }
    )
    events = [e async for e in stream_consultation(client, "test query")]

    assert events[0]["event"] == "routing"
    assert events[0]["agents"] == ["evidence"]
    assert any(e["event"] == "agent_completed" for e in events)
    assert events[-1]["event"] == "final"
    assert events[-1]["answer"]


@pytest.mark.asyncio
async def test_stream_consultation_agent_completed_carries_tool_call_names():
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "x", "top_k": 5}),
                ("answer", "ok"),
            ],
        }
    )
    events = [e async for e in stream_consultation(client, "test query")]
    agent_completed = [e for e in events if e["event"] == "agent_completed"]
    assert agent_completed
    assert agent_completed[0]["tool_calls"][0]["name"] == "search_clinical_guidelines"
