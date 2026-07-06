"""
LangGraph workflow orchestrating the clinical agents.

Specialist agents run in parallel branches (each one only when the patient
context contains the inputs it needs), and the ClinicalCoordinator merges
their outputs into a single cited response — post-processed by the Citation
Guard so fabricated citations never reach the user.

    START ─┬─> radiology ───┐
           ├─> laboratory ──┤
           ├─> drug_safety ─┼─> coordinator ─> END
           └─> evidence ────┘
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, AsyncIterator, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from intelligence.llm import OllamaClient

from . import (
    ClinicalCoordinator,
    DrugSafetyAgent,
    EvidenceAgent,
    LabAgent,
    RadiologyAgent,
)
from .citation_guard import audit, sanitize
from .explainability import build_explanation

SPECIALISTS = ("radiology", "laboratory", "drug_safety", "evidence")


class WorkflowState(TypedDict, total=False):
    patient_id: str
    query: str
    context: Dict[str, Any]
    agent_outputs: Annotated[Dict[str, str], operator.or_]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]
    final_answer: str
    citation_report: Dict[str, Any]
    explanation: Dict[str, Any]


def route_specialists(context: Dict[str, Any] | None) -> List[str]:
    """Which specialist branches to run, based on available inputs."""
    context = context or {}
    branches = ["evidence"]  # evidence retrieval always runs
    if context.get("image_path"):
        branches.append("radiology")
    if context.get("lab_results"):
        branches.append("laboratory")
    if context.get("medications"):
        branches.append("drug_safety")
    return branches


def build_workflow(client: OllamaClient):
    """Compile the clinical multi-agent graph for a given Ollama client."""

    radiology = RadiologyAgent(client)
    laboratory = LabAgent(client)
    drug_safety = DrugSafetyAgent(client)
    evidence = EvidenceAgent(client)
    coordinator = ClinicalCoordinator(client)

    def _specialist_node(agent):
        async def node(state: WorkflowState) -> WorkflowState:
            result = await agent.run(state["query"], state.get("context"))
            return {
                "agent_outputs": {agent.name: result.content},
                "tool_calls": [
                    {"agent": agent.name, **call} for call in result.tool_calls
                ],
            }

        return node

    async def coordinator_node(state: WorkflowState) -> WorkflowState:
        sections = "\n\n".join(
            f"### {name} agent\n{output}"
            for name, output in state.get("agent_outputs", {}).items()
        )
        result = await coordinator.run(
            f"Clinical question: {state['query']}\n\n"
            f"Specialist analyses:\n\n{sections}",
            state.get("context"),
        )
        all_tool_calls = state.get("tool_calls", []) + [
            {"agent": coordinator.name, **call} for call in result.tool_calls
        ]
        report = audit(result.content, all_tool_calls)
        agents_involved = sorted(state.get("agent_outputs", {}).keys())
        return {
            "final_answer": sanitize(result.content, report),
            "citation_report": report.as_dict(),
            "explanation": build_explanation(
                agents_involved, all_tool_calls, report.as_dict()
            ),
            "tool_calls": [
                {"agent": coordinator.name, **call} for call in result.tool_calls
            ],
        }

    graph = StateGraph(WorkflowState)
    graph.add_node("radiology", _specialist_node(radiology))
    graph.add_node("laboratory", _specialist_node(laboratory))
    graph.add_node("drug_safety", _specialist_node(drug_safety))
    graph.add_node("evidence", _specialist_node(evidence))
    graph.add_node("coordinator", coordinator_node)

    graph.add_conditional_edges(
        START,
        lambda state: route_specialists(state.get("context")),
        list(SPECIALISTS),
    )
    for specialist in SPECIALISTS:
        graph.add_edge(specialist, "coordinator")
    graph.add_edge("coordinator", END)

    return graph.compile()


def _initial_state(query: str, patient_id: str, context: Dict[str, Any] | None) -> Dict[str, Any]:
    return {
        "patient_id": patient_id,
        "query": query,
        "context": context or {},
        "agent_outputs": {},
        "tool_calls": [],
    }


async def run_consultation(
    client: OllamaClient,
    query: str,
    patient_id: str = "",
    context: Dict[str, Any] | None = None,
) -> WorkflowState:
    """Blocking entry point used by the non-streaming API and examples."""
    workflow = build_workflow(client)
    return await workflow.ainvoke(_initial_state(query, patient_id, context))


async def stream_consultation(
    client: OllamaClient,
    query: str,
    patient_id: str = "",
    context: Dict[str, Any] | None = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Streaming entry point: yields one event per workflow step.

    Events:
      {"event": "routing", "agents": [...]}
      {"event": "agent_completed", "agent", "summary", "tool_calls"}
      {"event": "final", "answer", "agents_involved", "tool_calls", "citation_report"}
    """
    workflow = build_workflow(client)
    yield {"event": "routing", "agents": route_specialists(context)}

    agent_outputs: Dict[str, str] = {}
    tool_calls: List[Dict[str, Any]] = []

    async for update in workflow.astream(
        _initial_state(query, patient_id, context), stream_mode="updates"
    ):
        for node_name, node_state in update.items():
            if node_name == "coordinator":
                tool_calls.extend(node_state.get("tool_calls", []))
                yield {
                    "event": "final",
                    "answer": node_state.get("final_answer", ""),
                    "agents_involved": sorted(agent_outputs.keys()),
                    "tool_calls": tool_calls,
                    "citation_report": node_state.get("citation_report", {}),
                    "explanation": node_state.get("explanation", {}),
                }
            else:
                output = node_state.get("agent_outputs", {})
                agent_outputs.update(output)
                node_calls = node_state.get("tool_calls", [])
                tool_calls.extend(node_calls)
                agent_name = next(iter(output), node_name)
                yield {
                    "event": "agent_completed",
                    "agent": agent_name,
                    "summary": (output.get(agent_name, "") or "")[:280],
                    "tool_calls": [
                        {"name": c.get("name"), "arguments": c.get("arguments")}
                        for c in node_calls
                    ],
                }
