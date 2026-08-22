"""`build_trace` — projects a populated `RunState` into `ExecutionTrace`
(SPEC-006, `ADR-009`).

Verifies AC-006-05, AC-006-09 (docs/specs/SPEC-006-telemetry.md)."""

from sephiroth.contracts import AgentResult, Claim, Contradiction, RunState, VerificationStatus
from sephiroth.telemetry import build_trace


def test_builds_trace_from_minimal_state():
    state = RunState(trace_id="t1", request="what is the A1C goal?", patient_id="p1")
    trace = build_trace(state)

    assert trace.trace_id == "t1"
    assert trace.request == state.request
    assert trace.patient_id == "p1"
    assert trace.verification is None


def test_verification_report_built_from_claims_and_contradictions():
    state = RunState(trace_id="t1", request="q")
    state.claims = [Claim(id="c1", text="x", status=VerificationStatus.SUPPORTED)]
    state.contradictions = [Contradiction(id="x1", claim_id="c1")]

    trace = build_trace(state)

    assert trace.verification is not None
    assert len(trace.verification.claims) == 1
    assert len(trace.verification.contradictions) == 1


def test_latency_and_tokens_summed_from_agent_results():
    state = RunState(trace_id="t1", request="q")
    state.agent_results = {
        "evidence": AgentResult(agent="evidence", prompt_tokens=5, completion_tokens=10, latency_ms=100),
        "coordinator": AgentResult(
            agent="coordinator", prompt_tokens=7, completion_tokens=20, latency_ms=200
        ),
    }

    trace = build_trace(state)

    assert trace.tokens.prompt_tokens == 12
    assert trace.tokens.completion_tokens == 30
    assert trace.latency_ms == 300


def test_cost_estimated_from_known_model_pricing():
    state = RunState(trace_id="t1", request="q")
    state.agent_results = {
        "evidence": AgentResult(agent="evidence", prompt_tokens=1_000_000, completion_tokens=1_000_000),
    }

    trace = build_trace(state, model="gemini-flash-latest")

    assert trace.cost_usd == 0.5  # (1M * 0.10 + 1M * 0.40) / 1M


def test_cost_is_zero_for_unrecognized_model():
    state = RunState(trace_id="t1", request="q")
    state.agent_results = {
        "evidence": AgentResult(agent="evidence", prompt_tokens=1000, completion_tokens=1000)
    }

    trace = build_trace(state, model="some-future-model-nobody-has-priced-yet")

    assert trace.cost_usd == 0.0


def test_model_versions_populated_only_when_model_given():
    state = RunState(trace_id="t1", request="q")
    assert build_trace(state).model_versions == {}
    assert build_trace(state, model="gemini-flash-latest", provider="gemini").model_versions == {
        "provider": "gemini",
        "model": "gemini-flash-latest",
    }


def test_spans_carried_through():
    from sephiroth.contracts import SpanKind
    from sephiroth.telemetry import traced_span

    state = RunState(trace_id="t1", request="q")
    with traced_span(state, SpanKind.AGENT, "evidence"):
        pass

    trace = build_trace(state)
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "evidence"


def test_selected_agents_falls_back_to_agents_involved():
    state = RunState(trace_id="t1", request="q")
    state.agent_results = {"evidence": AgentResult(agent="evidence")}
    trace = build_trace(state)
    assert trace.selected_agents == ["evidence"]
