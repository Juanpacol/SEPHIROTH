"""Projects a populated `RunState` into the persisted, replayable
`ExecutionTrace` (SPEC-006, `ADR-009`).

Token counts (SPEC-016, closing NG-2) are real usage from
`GeminiClient`/`GroqClient`, summed across every specialist + the
coordinator's `AgentResult`. Cost is a best-effort estimate from a
hand-maintained price table (`pricing.py`) -- not a billing source of
truth, and 0.0 for a model this codebase doesn't recognize. NOT covered:
`generate_json` calls (claim extraction, verification, the dynamic
planner) don't go through `ChatResult` and report no usage yet -- a
real, separate gap, not silently rolled into this number. Span timing
(`duration_ms`) is real.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sephiroth.contracts import ExecutionTrace, RunState, TokenUsage, VerificationReport

from .pricing import estimate_cost_usd


def build_trace(state: RunState, model: str = "", provider: str = "") -> ExecutionTrace:
    """Builds the trace to persist at the end of a consultation. Call once
    `RunState` is fully populated (after `_verify_and_decide` and
    `_final_answer`)."""
    # `agent_calls` (persisted, below) stays exactly `state.agent_results` --
    # the coordinator is deliberately excluded from that dict (see
    # `RunState.coordinator_result`'s docstring); folded in here only for
    # the aggregate token/latency numbers, which have no such contract.
    all_results = list(state.agent_results.values())
    if state.coordinator_result is not None:
        all_results.append(state.coordinator_result)

    prompt_tokens = sum(result.prompt_tokens for result in all_results)
    completion_tokens = sum(result.completion_tokens for result in all_results)
    tokens = TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    latency_ms = sum(result.latency_ms for result in all_results)
    model_versions = {"provider": provider, "model": model} if model else {}
    verification = (
        VerificationReport(claims=state.claims, contradictions=state.contradictions)
        if state.claims or state.contradictions
        else None
    )

    return ExecutionTrace(
        trace_id=state.trace_id,
        created_at=datetime.now(timezone.utc),
        request=state.request,
        patient_id=state.patient_id,
        task=state.task,
        risk_level=state.risk_level,
        plan=state.plan,
        selected_agents=state.selected_agents or state.agents_involved,
        agent_calls=list(state.agent_results.values()),
        tool_calls=list(state.tool_calls),
        spans=list(state.spans),
        evidence=list(state.evidence),
        claims=list(state.claims),
        contradictions=list(state.contradictions),
        verification=verification,
        citation_report=state.citation_report,
        safety_flags=list(state.safety_flags),
        abstention=state.abstention,
        failures=list(state.failures),
        retries=dict(state.retries),
        recovery_actions=list(state.recovery_actions),
        latency_ms=latency_ms,
        tokens=tokens,
        cost_usd=cost_usd,
        model_versions=model_versions,
        final_answer=state.final_answer,
    )


__all__ = ["build_trace"]
