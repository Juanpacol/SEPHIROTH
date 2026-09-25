"""The executor — route, run one specialist, verify, decide. LangGraph, gone.

Replaces `intelligence/agents/workflow.py`'s compiled graph
(`docs/specs/SPEC-003-agent-runtime.md`, `ADR-001`). SPEC-029 (Phase 14)
removed the multi-agent fan-out/coordinator merge this executor originally
also supported — a consultation now always takes a single path:

    intent_router ─> one specialist ─> citation guard ─> claim verification
                                                        ─> abstention gate

Internal state is a real `sephiroth.contracts.RunState` (SPEC-004 §1) — the
deferral documented in SPEC-003 §10 ends here, now that evidence/claims/
safety are actually populated. The one friction point flagged there
(`ToolCall.tool` vs. the frozen wire's `name`) is resolved by `_tool_call_wire`,
a single projection at the SSE-yield/return boundary — nothing else changes
shape.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from core.config import settings
from sephiroth.context import context_for_agent
from sephiroth.contracts import (
    AbstentionReason,
    AgentCapability,
    AgentResult,
    LifecycleState,
    RecoveryAction,
    RecoveryActionType,
    RunContext,
    RunState,
    SafetyFlag,
    SpanKind,
    ToolCall,
    VerificationReport,
)
from sephiroth.models import ModelProvider, OllamaClient, get_llm_client
from sephiroth.safety import check_input, check_scope
from sephiroth.safety import decide as decide_abstention
from sephiroth.safety.abstention import OBSERVED_BANNER, PARTIAL_BANNER
from sephiroth.telemetry import build_trace, traced_span
from sephiroth.telemetry.explain import build_explanation
from sephiroth.verification import (
    compute_confidence,
    extract_claims,
    harvest_evidence,
    harvest_observations,
    verify_claims,
)
from sephiroth.verification.citation_guard import audit, sanitize
from sephiroth.verification.combined import extract_and_verify

from .agent import Agent
from .intent_router import route_intent
from .recovery import classify, decide_recovery
from .registry import get_capability

#: Matches PlanStep.max_attempts' default (src/sephiroth/contracts/plan.py) —
#: a specialist gets one retry before the run continues without its section.
MAX_AGENT_ATTEMPTS = 2

#: The closing disclaimer every consultation answer must carry. The one
#: selected specialist's answer is the final answer (SPEC-029: the only
#: path since the coordinator was removed), so it is appended here instead
#: of trusting a smaller model to remember an instruction. A guarantee this
#: load-bearing belongs in code, not in a prompt — the same reasoning behind
#: deterministic citation auditing rather than asking the model to self-check.
CLOSING_DISCLAIMER = "This is decision support, not a diagnosis — professional review required."


def _with_disclaimer(answer: str) -> str:
    """Idempotent: an answer that already ends with the disclaimer (a
    model that followed instructions) is returned unchanged."""
    text = (answer or "").rstrip()
    if not text:
        return text
    if "professional review required" in text:
        return text
    return f"{text}\n\n{CLOSING_DISCLAIMER}"


def _initial_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return context or {}


async def _select_and_run(
    context: Optional[Dict[str, Any]],
    client: ModelProvider,
    query: str,
    run_context: RunContext,
    state: RunState,
) -> Tuple[List[str], str]:
    """Route, then run the selected specialist, returning
    `(node_names, answer_text)`.

    `intent_router.route_intent` picks ONE specialist and its answer IS the
    final answer — no coordinator turn (SPEC-029: the only path since the
    multi-agent fan-out was removed). This is what takes a consultation from
    4-8 sequential model calls down to 1 for the answer itself.

    Everything downstream (citation guard, verification, abstention, trace)
    operates on the returned text.
    """
    node = await route_intent(query, context, client)
    node_names = [node]
    capability = get_capability(node)
    state.lifecycle[capability.id] = LifecycleState.SELECTED

    _, agent_result, tool_calls = await _run_specialist(
        capability, client, query, run_context, state, answering=True
    )
    state.agent_results[capability.id] = agent_result
    state.tool_calls.extend(tool_calls)
    return node_names, _with_disclaimer(agent_result.content)


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
    capability: AgentCapability,
    client: ModelProvider,
    query: str,
    run_context: RunContext,
    state: RunState,
    *,
    answering: bool = False,
) -> Tuple[AgentCapability, AgentResult, List[ToolCall]]:
    """Runs one specialist, classifying and retrying a transient failure up
    to `MAX_AGENT_ATTEMPTS` (SPEC-007, executes `ADR-007`). A specialist
    that exhausts its retries never raises past this function — it
    contributes an empty section rather than aborting the rest of the
    consultation; the failure and the recovery attempt are both recorded on
    `state` for later inspection (recovery success rate, etc.)."""
    # `model_hint` names an Ollama model tag chosen for this capability
    # specifically (e.g. evidence wants a tool-calling-tuned model). Only
    # swapped in when the running client is itself a real `OllamaClient` —
    # checking the *instance*, not `settings.llm_provider`, so a test's
    # injected `FakeLLMClient` is never routed through the live factory
    # singleton (which would ignore that fake and reintroduce a real,
    # unconfigured client mid-test).
    agent_client = client
    if capability.model_hint and isinstance(client, OllamaClient):
        agent_client = get_llm_client(capability.model_hint)
    agent = Agent(capability, agent_client)
    state.lifecycle[capability.id] = LifecycleState.EXECUTING

    attempt = 1
    while True:
        try:
            started = time.perf_counter()
            with traced_span(
                state,
                SpanKind.AGENT,
                capability.id,
                agent=capability.id,
                model=getattr(agent_client, "model", ""),
            ):
                result = await agent.run(
                    query, context_for_agent(capability, run_context, answering=answering)
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            failure = classify(exc, component=capability.id, attempt=attempt)
            state.failures.append(failure)
            action = decide_recovery(failure, attempt, MAX_AGENT_ATTEMPTS)

            if action is RecoveryActionType.RETRY:
                state.retries[capability.id] = state.retries.get(capability.id, 0) + 1
                state.recovery_actions.append(RecoveryAction(failure_id=failure.id, action=action))
                state.lifecycle[capability.id] = LifecycleState.RECOVERING
                attempt += 1
                continue

            state.recovery_actions.append(
                RecoveryAction(failure_id=failure.id, action=action, succeeded=False)
            )
            state.lifecycle[capability.id] = LifecycleState.FAILED
            return capability, AgentResult(agent=capability.id), []

        state.lifecycle[capability.id] = LifecycleState.COMPLETED
        tool_calls = to_tool_calls(capability.id, result.tool_calls)
        agent_result = AgentResult(
            agent=capability.id,
            content=result.content,
            tool_call_ids=[tc.id for tc in tool_calls],
            rounds=result.rounds,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=latency_ms,
        )
        return capability, agent_result, tool_calls


async def _verify_and_decide(
    state: RunState, client: ModelProvider, query: str, sanitized_answer: str
) -> None:
    """Populates `state.evidence/claims/contradictions/confidence/abstention`
    from the coordinator's (already citation-sanitized) answer. Mutates
    `state` in place — this is the one function both entry points share.

    Verification always runs. An earlier version skipped it when
    `state.patient_id` was empty, on the theory that "no specific patient"
    meant "no clinical risk to verify". That's false:
    `tests/test_runtime_executor.py::test_run_consultation_abstains_on_unsupported_high_risk_claim`
    constructs exactly this case — a patient_id-less query whose answer
    contains an unsupported high-risk claim ("double the warfarin dose")
    that must still trigger abstention. `patient_id` presence is not a
    valid proxy for risk.

    `settings.enable_combined_verification` (default on) does the
    decomposition and the judging in one model call instead of two
    sequential ones — see `verification/combined.py` for why the merge
    preserves every guarantee.

    SPEC-004 1.2.0 (ADR-018): `harvest_observations` runs alongside
    `harvest_evidence` — a perception tool's own output (vision/imaging) can
    ground a claim as OBSERVED without ever counting as independent
    corroboration. Each claim's `originating_agent` is then overwritten with
    the actual answering agent id (`state.agent_results`) rather than trust
    the extraction prompt's guess — since Phase 14 exactly one agent answers
    per consultation, so there is never ambiguity about which one that is."""
    with traced_span(state, SpanKind.VERIFY, "verify"):
        evidence = harvest_evidence(state.tool_calls)
        observations = harvest_observations(state.tool_calls)
        if settings.enable_combined_verification:
            report = await extract_and_verify(sanitized_answer, evidence, client, observations=observations)
        else:
            claims = await extract_claims(sanitized_answer, client)
            report = await verify_claims(claims, evidence, client, observations=observations)
        tool_failures = sum(1 for tc in state.tool_calls if not tc.ok)
        confidence = compute_confidence(report, state.citation_report, tool_failures)
        # `check_input`/`check_scope` already ran in `_early_reject` before
        # routing — a flagged query never reaches this function at all (see
        # `run_consultation`/`stream_consultation`), so there is nothing to
        # re-check here. `input_flags` stays empty; `decide()` still takes
        # the parameter so its priority-order contract doesn't change shape.
        input_flags: List[SafetyFlag] = []
        answering_agent = next(iter(state.agent_results), "")
        if answering_agent:
            report = report.model_copy(
                update={
                    "claims": [
                        c.model_copy(update={"originating_agent": answering_agent}) for c in report.claims
                    ]
                }
            )
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
    assert abstention is not None, "_final_answer runs after _verify_and_decide"
    if abstention.status.value == "abstain":
        return abstention.message
    if abstention.status.value == "partial":
        # SPEC-004 1.2.0 (ADR-018): a partial driven by OBSERVED claims gets
        # its own banner, distinct from the generic one — a clinician can
        # tell "moderate confidence overall" apart from "faithful to an AI
        # visual description, not independently corroborated."
        banner = (
            OBSERVED_BANNER
            if abstention.reason is AbstentionReason.OBSERVED_NOT_CORROBORATED
            else PARTIAL_BANNER
        )
        return f"{banner}\n\n{sanitized_answer}"
    return sanitized_answer


def _early_reject(query: str):
    """Input-level hard stops — prompt injection and out-of-scope — checked
    BEFORE routing, before any specialist runs, and before any model or tool
    call. Previously `check_input` ran only inside `_verify_and_decide`,
    *after* a full specialist turn (and, in multi-agent mode, the
    coordinator) had already executed — an adversarial or off-topic query
    paid for the entire pipeline before being rejected. Returns `None` when
    the query passes both checks, in which case the run proceeds normally."""
    flags = check_input(query) + check_scope(query)
    if not flags:
        return None
    return decide_abstention(VerificationReport(), confidence=0.0, input_flags=flags)


async def run_consultation(
    client: ModelProvider,
    query: str,
    patient_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Blocking entry point used by the non-streaming API and examples."""
    context = _initial_context(context)
    run_context = RunContext.from_dict(context)
    state = RunState(trace_id=uuid.uuid4().hex, request=query, patient_id=patient_id, patient_context=context)

    early = _early_reject(query)
    if early is not None:
        state.abstention = early
        state.final_answer = early.message
        trace = build_trace(state, model=getattr(client, "model", ""))
        return {
            "patient_id": patient_id,
            "query": query,
            "context": context,
            "agent_outputs": {},
            "tool_calls": [],
            "final_answer": early.message,
            "citation_report": state.citation_report.model_dump(mode="json"),
            "verification_report": {"claims": [], "contradictions": []},
            "abstention": early.model_dump(mode="json"),
            "explanation": build_explanation([], [], state.citation_report.model_dump(mode="json")),
            "trace": trace.model_dump(mode="json"),
        }

    _node_names, answer = await _select_and_run(context, client, query, run_context, state)

    citation_report = audit(answer, [_tool_call_wire(tc) for tc in state.tool_calls])
    sanitized = sanitize(answer, citation_report)
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
    context = _initial_context(context)
    run_context = RunContext.from_dict(context)
    state = RunState(trace_id=uuid.uuid4().hex, request=query, patient_id=patient_id, patient_context=context)

    early = _early_reject(query)
    if early is not None:
        # Same frozen event sequence (`routing` -> `final`) as a normal run —
        # zero agents were selected, so `routing` carries an empty list and
        # no `agent_completed` events fire before `final`. No specialist, no
        # coordinator, no verification call runs for a rejected query.
        state.abstention = early
        state.final_answer = early.message
        yield {"event": "routing", "agents": []}
        trace = build_trace(state, model=getattr(client, "model", ""))
        yield {
            "event": "final",
            "answer": early.message,
            "agents_involved": [],
            "tool_calls": [],
            "citation_report": state.citation_report.model_dump(mode="json"),
            "verification_report": {"claims": [], "contradictions": []},
            "abstention": early.model_dump(mode="json"),
            "explanation": build_explanation([], [], state.citation_report.model_dump(mode="json")),
            "trace": trace.model_dump(mode="json"),
        }
        return

    # Routes to exactly one specialist and yields its answer directly —
    # SPEC-029: the only path since the multi-agent fan-out/coordinator
    # merge was removed. See `_select_and_run`.
    node = await route_intent(query, context, client)
    node_names = [node]
    capability = get_capability(node)
    state.lifecycle[capability.id] = LifecycleState.SELECTED

    yield {"event": "routing", "agents": node_names}

    _, agent_result, tool_calls = await _run_specialist(
        capability, client, query, run_context, state, answering=True
    )
    state.agent_results[capability.id] = agent_result
    state.tool_calls.extend(tool_calls)
    node_calls_wire = [_tool_call_wire(tc) for tc in tool_calls]
    yield {
        "event": "agent_completed",
        "agent": capability.id,
        "summary": (agent_result.content or "")[:280],
        "tool_calls": [{"name": c.get("name"), "arguments": c.get("arguments")} for c in node_calls_wire],
    }

    answer = _with_disclaimer(agent_result.content)

    citation_report = audit(answer, [_tool_call_wire(tc) for tc in state.tool_calls])
    sanitized = sanitize(answer, citation_report)
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
