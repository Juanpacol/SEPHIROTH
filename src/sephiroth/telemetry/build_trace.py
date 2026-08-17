"""Projects a populated `RunState` into the persisted, replayable
`ExecutionTrace` (SPEC-006, `ADR-009`).

Token counts and cost are currently placeholders (0) — `ChatResult`/`AgentResult`
don't carry usage metadata from the model clients yet (a separate,
future change to `GeminiClient`/`GroqClient`). Span timing (`duration_ms`)
is real; token/cost accounting is out of scope for this cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sephiroth.contracts import ExecutionTrace, RunState, TokenUsage, VerificationReport


def build_trace(state: RunState, model: str = "", provider: str = "") -> ExecutionTrace:
    """Builds the trace to persist at the end of a consultation. Call once
    `RunState` is fully populated (after `_verify_and_decide` and
    `_final_answer`)."""
    tokens = TokenUsage(
        prompt_tokens=0,
        completion_tokens=sum(result.tokens for result in state.agent_results.values()),
    )
    latency_ms = sum(result.latency_ms for result in state.agent_results.values())
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
        cost_usd=0.0,
        model_versions=model_versions,
        final_answer=state.final_answer,
    )


__all__ = ["build_trace"]
