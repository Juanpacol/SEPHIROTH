"""Executor characterization tests — routing, end-to-end consultation with a
scripted LLM double, citation sanitization, and SSE event order.

Runs directly against `sephiroth.runtime` (the Phase 3 executor). Originally
written against the pre-Phase-3 LangGraph workflow, then kept passing
unmodified through the `intelligence.agents.workflow` shim as the parity
proof — the shim was deleted in Phase 5 (`DEBT-010`, one phase later than
scheduled) once nothing else needed it; this module's import retargeted in
the same commit and is kept permanently as the executor's characterization
test.

Phase 5 (SPEC-008) added the feature-flagged dynamic planner — this file
passes unmodified with the flag at its default (off), the evidence that
the change is additive. Verifies AC-008-04 (docs/specs/SPEC-008-dynamic-planner.md)."""

import pytest

from sephiroth.runtime import route_specialists, run_consultation, stream_consultation
from tests.conftest import FakeLLMClient


def test_route_specialists_evidence_always_runs():
    assert route_specialists(None) == ["evidence"]
    assert route_specialists({}) == ["evidence"]


def test_route_specialists_adds_radiology_on_image_path():
    branches = route_specialists({"image_path": "/x.png"})
    assert "evidence" in branches
    assert "radiology" in branches


def test_route_specialists_adds_laboratory_on_lab_results():
    branches = route_specialists({"lab_results": {"a1c": "7.0"}})
    assert "laboratory" in branches


def test_route_specialists_adds_drug_safety_on_medications():
    branches = route_specialists({"medications": ["metformin"]})
    assert "drug_safety" in branches


def test_route_specialists_all_four_branches():
    branches = route_specialists(
        {"image_path": "/x.png", "lab_results": {"a1c": "7.0"}, "medications": ["metformin"]}
    )
    assert set(branches) == {"evidence", "radiology", "laboratory", "drug_safety"}


@pytest.mark.asyncio
async def test_run_consultation_end_to_end_with_fake_client():
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
            "coordinating physician-assistant": [
                (
                    "answer",
                    "Summary: target A1C <7% [ADA Standards of Care in Diabetes, 2024]. "
                    "This is decision support, not a diagnosis — professional review required.",
                )
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
    client = FakeLLMClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "x", "top_k": 5}),
                ("answer", "No strong evidence found."),
            ],
            "coordinating physician-assistant": [
                ("answer", "This is backed by [Totally Fabricated Journal, 2099]."),
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
            "coordinating physician-assistant": [("answer", "Final summary.")],
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
            "coordinating physician-assistant": [
                ("answer", "Final answer [ADA Standards of Care in Diabetes, 2024]."),
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
            "coordinating physician-assistant": [("answer", "done")],
        }
    )
    events = [e async for e in stream_consultation(client, "test query")]
    agent_completed = [e for e in events if e["event"] == "agent_completed"]
    assert agent_completed
    assert agent_completed[0]["tool_calls"][0]["name"] == "search_clinical_guidelines"
