"""The executor — fan-out, merge, coordinate, verify, decide. LangGraph, gone.

Replaces `intelligence/agents/workflow.py`'s compiled graph
(`docs/specs/SPEC-003-agent-runtime.md`, `ADR-001`). The graph's shape is
preserved exactly:

    ┬─> radiology ───┐
    ├─> laboratory ──┤
    ├─> drug_safety ─┼─> coordinator ─> citation guard ─> claim verification
    └─> evidence ────┘                                  ─> abstention gate

`run_consultation` fans out with `asyncio.gather` (order doesn't matter for
its return value — nothing downstream is order-sensitive there).
`stream_consultation` uses `asyncio.as_completed` instead, so
`agent_completed` events still arrive progressively as each specialist
actually finishes — the same streaming UX the LangGraph implementation gave
for free, not something to regress on a relocation.

Internal state is a real `sephiroth.contracts.RunState` (SPEC-004 §1) — the
deferral documented in SPEC-003 §10 ends here, now that evidence/claims/
safety are actually populated. The one friction point flagged there
(`ToolCall.tool` vs. the frozen wire's `name`) is resolved by `_tool_call_wire`,
a single projection at the SSE-yield/return boundary — nothing else changes
shape.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from core.config import settings
from sephiroth.context import context_for_agent, truncate
from sephiroth.contracts import AgentCapability, AgentResult, RunContext, RunState, SpanKind, ToolCall
from sephiroth.models import ModelProvider
from sephiroth.safety import check_input
from sephiroth.safety import decide as decide_abstention
from sephiroth.safety.abstention import PARTIAL_BANNER
from sephiroth.telemetry import build_trace, traced_span
from sephiroth.verification import compute_confidence, extract_claims, harvest_evidence, verify_claims

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


def _tool_call_wire(tc: ToolCall) -> Dict[str, Any]:
    """Projects a typed `ToolCall` to the frozen wire/persistence shape
    (`{"agent", "name", "arguments", "result"}`) — the only place the
    `tool`/`name` naming mismatch (SPEC-003 §10) is resolved."""
    return {"agent": tc.agent, "name": tc.tool, "arguments": tc.arguments, "result": tc.result}


def _call_ok(result: Any) -> bool:
    return not (isinstance(result, dict) and "error" in result)


def to_tool_calls(capability_id: str, raw_calls: List[Dict[str, Any]]) -> List[ToolCall]:
    now = datetime.now(timezone.utc)
    return [
        ToolCall(
            id=uuid.uuid4().hex,
            tool=call.get("name", ""),
            agent=capability_id,
            arguments=call.get("arguments") or {},
            result=call.get("result"),
            ok=_call_ok(call.get("result")),
            timestamp=now,
        )
        for call in raw_calls
    ]


async def _run_specialist(
    capability: AgentCapability, client: ModelProvider, query: str, run_context: RunContext, state: RunState
) -> Tuple[AgentCapability, AgentResult, List[ToolCall]]:
    agent = Agent(capability, client)
    with traced_span(state, SpanKind.AGENT, capability.id, agent=capability.id):
        result = await agent.run(query, context_for_agent(capability, run_context))
    tool_calls = to_tool_calls(capability.id, result.tool_calls)
    agent_result = AgentResult(
        agent=capability.id,
        content=result.content,
        tool_call_ids=[tc.id for tc in tool_calls],
        rounds=result.rounds,
    )
    return capability, agent_result, tool_calls


async def _verify_and_decide(
    state: RunState, client: ModelProvider, query: str, sanitized_answer: str
) -> None:
    """Populates `state.evidence/claims/contradictions/confidence/abstention`
    from the coordinator's (already citation-sanitized) answer. Mutates
    `state` in place — this is the one function both entry points share."""
    with traced_span(state, SpanKind.VERIFY, "verify"):
        claims = await extract_claims(sanitized_answer, client)
        evidence = harvest_evidence(state.tool_calls)
        report = await verify_claims(claims, evidence, client)
        tool_failures = sum(1 for tc in state.tool_calls if not tc.ok)
        confidence = compute_confidence(report, state.citation_report, tool_failures)
        input_flags = check_input(query)
        abstention = decide_abstention(report, confidence, input_flags)

        state.evidence = evidence
        state.claims = report.claims
        state.contradictions = report.contradictions
        state.safety_flags = input_flags
        state.confidence = confidence
        state.abstention = abstention


def _final_answer(sanitized_answer: str, state: RunState) -> str:
    """Abstention overrides the coordinator's answer; a partial verdict keeps
    it with a caveat banner prepended. Never surface a possibly-fabricated
    answer alongside a decline. Called only after `_verify_and_decide` has
    set `state.abstention`, so it is never `None` here."""
    abstention = state.abstention
    if abstention.status.value == "abstain":
        return abstention.message
    if abstention.status.value == "partial":
        return f"{PARTIAL_BANNER}\n\n{sanitized_answer}"
    return sanitized_answer


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
    run_context = RunContext.from_dict(context)
    state = RunState(trace_id=uuid.uuid4().hex, request=query, patient_id=patient_id, patient_context=context)
    node_names = route_specialists(context)
    capabilities = resolve(node_names)

    results = await asyncio.gather(
        *(_run_specialist(cap, client, query, run_context, state) for cap in capabilities)
    )
    for capability, agent_result, tool_calls in results:
        state.agent_results[capability.id] = agent_result
        state.tool_calls.extend(tool_calls)

    sections = "\n\n".join(f"### {name} agent\n{output}" for name, output in state.agent_outputs.items())
    sections = truncate(sections, settings.max_context_chars)
    coordinator = Agent(COORDINATOR, client)
    with traced_span(state, SpanKind.AGENT, COORDINATOR.id, agent=COORDINATOR.id):
        coord_result = await coordinator.run(
            f"Clinical question: {query}\n\nSpecialist analyses:\n\n{sections}",
            context_for_agent(COORDINATOR, run_context),
        )
    coord_tool_calls = to_tool_calls(coordinator.name, coord_result.tool_calls)
    state.tool_calls.extend(coord_tool_calls)

    citation_report = audit(coord_result.content, [_tool_call_wire(tc) for tc in state.tool_calls])
    sanitized = sanitize(coord_result.content, citation_report)
    state.citation_report = state.citation_report.__class__(**citation_report.as_dict())

    await _verify_and_decide(state, client, query, sanitized)
    final_answer = _final_answer(sanitized, state)
    state.final_answer = final_answer

    agents_involved = state.agents_involved
    tool_calls_wire = [_tool_call_wire(tc) for tc in state.tool_calls]
    trace = build_trace(state, model=getattr(client, "model", ""))

    return {
        "patient_id": patient_id,
        "query": query,
        "context": context,
        "agent_outputs": state.agent_outputs,
        "tool_calls": tool_calls_wire,
        "final_answer": final_answer,
        "citation_report": citation_report.as_dict(),
        "verification_report": {
            "claims": [c.model_dump(mode="json") for c in state.claims],
            "contradictions": [c.model_dump(mode="json") for c in state.contradictions],
        },
        "abstention": state.abstention.model_dump(mode="json") if state.abstention else None,
        "explanation": build_explanation(agents_involved, tool_calls_wire, citation_report.as_dict()),
        "trace": trace.model_dump(mode="json"),
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
      {"event": "final", "answer", "agents_involved", "tool_calls", "citation_report",
       "explanation", "verification_report", "abstention", "trace"}
    """
    from intelligence.agents.citation_guard import audit, sanitize
    from intelligence.agents.explainability import build_explanation

    context = _initial_context(context)
    run_context = RunContext.from_dict(context)
    state = RunState(trace_id=uuid.uuid4().hex, request=query, patient_id=patient_id, patient_context=context)
    node_names = route_specialists(context)
    capabilities = resolve(node_names)

    yield {"event": "routing", "agents": node_names}

    tasks = [
        asyncio.ensure_future(_run_specialist(cap, client, query, run_context, state)) for cap in capabilities
    ]
    for finished in asyncio.as_completed(tasks):
        capability, agent_result, tool_calls = await finished
        state.agent_results[capability.id] = agent_result
        state.tool_calls.extend(tool_calls)
        node_calls_wire = [_tool_call_wire(tc) for tc in tool_calls]
        yield {
            "event": "agent_completed",
            "agent": capability.id,
            "summary": (agent_result.content or "")[:280],
            "tool_calls": [{"name": c.get("name"), "arguments": c.get("arguments")} for c in node_calls_wire],
        }

    sections = "\n\n".join(f"### {name} agent\n{output}" for name, output in state.agent_outputs.items())
    sections = truncate(sections, settings.max_context_chars)
    coordinator = Agent(COORDINATOR, client)
    with traced_span(state, SpanKind.AGENT, COORDINATOR.id, agent=COORDINATOR.id):
        coord_result = await coordinator.run(
            f"Clinical question: {query}\n\nSpecialist analyses:\n\n{sections}",
            context_for_agent(COORDINATOR, run_context),
        )
    coord_tool_calls = to_tool_calls(coordinator.name, coord_result.tool_calls)
    state.tool_calls.extend(coord_tool_calls)

    citation_report = audit(coord_result.content, [_tool_call_wire(tc) for tc in state.tool_calls])
    sanitized = sanitize(coord_result.content, citation_report)
    state.citation_report = state.citation_report.__class__(**citation_report.as_dict())

    await _verify_and_decide(state, client, query, sanitized)
    final_answer = _final_answer(sanitized, state)
    state.final_answer = final_answer

    agents_involved = state.agents_involved
    tool_calls_wire = [_tool_call_wire(tc) for tc in state.tool_calls]
    trace = build_trace(state, model=getattr(client, "model", ""))

    yield {
        "event": "final",
        "answer": final_answer,
        "agents_involved": agents_involved,
        "tool_calls": tool_calls_wire,
        "citation_report": citation_report.as_dict(),
        "verification_report": {
            "claims": [c.model_dump(mode="json") for c in state.claims],
            "contradictions": [c.model_dump(mode="json") for c in state.contradictions],
        },
        "abstention": state.abstention.model_dump(mode="json") if state.abstention else None,
        "explanation": build_explanation(agents_involved, tool_calls_wire, citation_report.as_dict()),
        "trace": trace.model_dump(mode="json"),
    }


__all__ = ["run_consultation", "stream_consultation", "to_tool_calls"]
