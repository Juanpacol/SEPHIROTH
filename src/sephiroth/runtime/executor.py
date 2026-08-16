"""The executor — fan-out, merge, coordinate. LangGraph, gone.

Replaces `intelligence/agents/workflow.py`'s compiled graph
(`docs/specs/SPEC-003-agent-runtime.md`, `ADR-001`). The graph's shape is
preserved exactly:

    ┬─> radiology ───┐
    ├─> laboratory ──┤
    ├─> drug_safety ─┼─> coordinator ─> (verify, sanitize, explain)
    └─> evidence ────┘

`run_consultation` fans out with `asyncio.gather` (order doesn't matter for
its return value — nothing downstream is order-sensitive there).
`stream_consultation` uses `asyncio.as_completed` instead, so
`agent_completed` events still arrive progressively as each specialist
actually finishes — the same streaming UX the LangGraph implementation gave
for free, not something to regress on a relocation.

Internal state is a plain dict shaped exactly like the pre-Phase-3
`WorkflowState`, not `sephiroth.contracts.RunState` — adopting that richer,
strict contract now would mean building `ToolCall`/`AgentResult` instances
only to immediately flatten them back into the frozen wire shape
(`{"agent","name","arguments","result"}`, which doesn't match `ToolCall`'s
`{"id","tool","agent","arguments","result",...}`). `RunState` gets adopted in
the phase that actually needs its extra fields (evidence, claims, safety).
See SPEC-003 §10.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from sephiroth.contracts import AgentCapability
from sephiroth.models import ModelProvider

from .agent import Agent
from .planner import route_specialists
from .registry import COORDINATOR
from .router import resolve

# Deferred imports of citation_guard/explainability happen inside the
# functions below — they still live under intelligence/agents/ (shimmed in a
# later phase, not this one) and importing them at module scope would create
# the same cross-package ordering hazard Phase 2 hit with intelligence.mcp.


def _initial_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return context or {}


async def _run_specialist(
    capability: AgentCapability, client: ModelProvider, query: str, context: Dict[str, Any]
):
    agent = Agent(capability, client)
    result = await agent.run(query, context)
    return capability, result


async def run_consultation(
    client: ModelProvider,
    query: str,
    patient_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Blocking entry point used by the non-streaming API and examples."""
    from intelligence.agents.citation_guard import audit, sanitize
    from intelligence.agents.explainability import build_explanation

    context = _initial_context(context)
    node_names = route_specialists(context)
    capabilities = resolve(node_names)

    results = await asyncio.gather(*(_run_specialist(cap, client, query, context) for cap in capabilities))

    agent_outputs: Dict[str, str] = {}
    tool_calls: List[Dict[str, Any]] = []
    for capability, result in results:
        agent_outputs[capability.id] = result.content
        tool_calls.extend({"agent": capability.id, **call} for call in result.tool_calls)

    sections = "\n\n".join(f"### {name} agent\n{output}" for name, output in agent_outputs.items())
    coordinator = Agent(COORDINATOR, client)
    coord_result = await coordinator.run(
        f"Clinical question: {query}\n\nSpecialist analyses:\n\n{sections}", context
    )
    tool_calls.extend({"agent": coordinator.name, **call} for call in coord_result.tool_calls)

    report = audit(coord_result.content, tool_calls)
    agents_involved = sorted(agent_outputs.keys())

    return {
        "patient_id": patient_id,
        "query": query,
        "context": context,
        "agent_outputs": agent_outputs,
        "tool_calls": tool_calls,
        "final_answer": sanitize(coord_result.content, report),
        "citation_report": report.as_dict(),
        "explanation": build_explanation(agents_involved, tool_calls, report.as_dict()),
    }


async def stream_consultation(
    client: ModelProvider,
    query: str,
    patient_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Streaming entry point: yields one event per specialist as it completes,
    then a final synthesis event.

    Events:
      {"event": "routing", "agents": [...]}
      {"event": "agent_completed", "agent", "summary", "tool_calls"}
      {"event": "final", "answer", "agents_involved", "tool_calls", "citation_report", "explanation"}
    """
    from intelligence.agents.citation_guard import audit, sanitize
    from intelligence.agents.explainability import build_explanation

    context = _initial_context(context)
    node_names = route_specialists(context)
    capabilities = resolve(node_names)

    yield {"event": "routing", "agents": node_names}

    agent_outputs: Dict[str, str] = {}
    tool_calls: List[Dict[str, Any]] = []

    tasks = [asyncio.ensure_future(_run_specialist(cap, client, query, context)) for cap in capabilities]
    for finished in asyncio.as_completed(tasks):
        capability, result = await finished
        agent_outputs[capability.id] = result.content
        node_calls = [{"agent": capability.id, **call} for call in result.tool_calls]
        tool_calls.extend(node_calls)
        yield {
            "event": "agent_completed",
            "agent": capability.id,
            "summary": (result.content or "")[:280],
            "tool_calls": [{"name": c.get("name"), "arguments": c.get("arguments")} for c in node_calls],
        }

    sections = "\n\n".join(f"### {name} agent\n{output}" for name, output in agent_outputs.items())
    coordinator = Agent(COORDINATOR, client)
    coord_result = await coordinator.run(
        f"Clinical question: {query}\n\nSpecialist analyses:\n\n{sections}", context
    )
    tool_calls.extend({"agent": coordinator.name, **call} for call in coord_result.tool_calls)

    report = audit(coord_result.content, tool_calls)
    agents_involved = sorted(agent_outputs.keys())
    yield {
        "event": "final",
        "answer": sanitize(coord_result.content, report),
        "agents_involved": agents_involved,
        "tool_calls": tool_calls,
        "citation_report": report.as_dict(),
        "explanation": build_explanation(agents_involved, tool_calls, report.as_dict()),
    }


__all__ = ["run_consultation", "stream_consultation"]
