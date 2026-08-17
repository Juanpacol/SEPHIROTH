"""Behaviour of the domain contracts' validators and derived properties.

These models are not passive data holders — several enforce invariants that the
runtime depends on and that a hallucinating LLM planner is the expected source
of violations for. Those invariants get tests.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sephiroth.contracts import (
    AbstentionDecision,
    AbstentionReason,
    AgentResult,
    CitationReport,
    Claim,
    EvidenceRecord,
    ExecutionPlan,
    PlanStep,
    ResponseStatus,
    RiskLevel,
    RunState,
    Span,
    SpanKind,
    TokenUsage,
    VerificationReport,
    VerificationStatus,
)

pytestmark = pytest.mark.spec

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _step(sid: str, *deps: str) -> PlanStep:
    return PlanStep(id=sid, agent=f"agent-{sid}", depends_on=list(deps))


# --------------------------------------------------------------------------
# ExecutionPlan — the DAG invariants
# --------------------------------------------------------------------------


def test_plan_accepts_a_valid_dag():
    plan = ExecutionPlan(plan_id="p1", steps=[_step("a"), _step("b"), _step("c", "a", "b")])
    assert len(plan.steps) == 3


def test_plan_rejects_duplicate_step_ids():
    with pytest.raises(ValidationError, match="duplicate PlanStep ids"):
        ExecutionPlan(plan_id="p1", steps=[_step("a"), _step("a")])


def test_plan_rejects_dangling_dependency():
    """A step waiting on a nonexistent step would deadlock the executor."""
    with pytest.raises(ValidationError, match="depends on unknown steps"):
        ExecutionPlan(plan_id="p1", steps=[_step("a", "ghost")])


def test_plan_rejects_self_dependency():
    with pytest.raises(ValidationError, match="depends on itself"):
        ExecutionPlan(plan_id="p1", steps=[_step("a", "a")])


def test_plan_rejects_dependency_cycle():
    """The canonical hallucinated-plan failure: a → b → a would hang forever."""
    with pytest.raises(ValidationError, match="dependency cycle"):
        ExecutionPlan(plan_id="p1", steps=[_step("a", "b"), _step("b", "a")])


def test_execution_waves_group_by_dependency_depth():
    plan = ExecutionPlan(
        plan_id="p1",
        steps=[_step("a"), _step("b"), _step("c", "a"), _step("d", "c", "b")],
    )
    waves = [[step.id for step in wave] for wave in plan.execution_waves()]

    assert waves == [["a", "b"], ["c"], ["d"]]


def test_execution_waves_preserve_declaration_order_within_a_wave():
    """Merge order is observable on the wire (`agents_involved`, `final.tool_calls`),
    so scheduling must be deterministic rather than completion-ordered."""
    plan = ExecutionPlan(plan_id="p1", steps=[_step("z"), _step("m"), _step("a")])
    assert [s.id for s in plan.execution_waves()[0]] == ["z", "m", "a"]


def test_degenerate_plan_is_the_parity_case():
    """Phase 3a emits exactly this shape: no dependencies, one iteration. The
    dynamic planner adds values, not types."""
    plan = ExecutionPlan(plan_id="p1", steps=[_step("evidence")], max_iterations=1)
    assert plan.execution_waves() == [plan.steps]
    assert all(not s.depends_on for s in plan.steps)


# --------------------------------------------------------------------------
# AbstentionDecision — a decline must always say why
# --------------------------------------------------------------------------


def test_abstention_requires_a_reason():
    with pytest.raises(ValidationError, match="must carry a reason"):
        AbstentionDecision(status=ResponseStatus.ABSTAIN)


def test_answer_must_not_carry_a_reason():
    with pytest.raises(ValidationError, match="must not carry reason"):
        AbstentionDecision(status=ResponseStatus.ANSWER, reason=AbstentionReason.TOOL_FAILURE)


def test_valid_abstention():
    decision = AbstentionDecision(
        status=ResponseStatus.ABSTAIN,
        reason=AbstentionReason.INSUFFICIENT_EVIDENCE,
        confidence=0.32,
        supported_claim_ratio=0.41,
    )
    assert decision.reason is AbstentionReason.INSUFFICIENT_EVIDENCE


def test_confidence_is_bounded():
    with pytest.raises(ValidationError):
        AbstentionDecision(confidence=1.5)


# --------------------------------------------------------------------------
# VerificationReport — the signals that drive abstention
# --------------------------------------------------------------------------


def _claim(cid: str, status: VerificationStatus, risk: RiskLevel = RiskLevel.LOW) -> Claim:
    return Claim(id=cid, text=f"claim {cid}", status=status, risk=risk)


def test_supported_ratio_of_empty_report_is_one():
    """Nothing unsupported was asserted, so there is nothing to abstain over."""
    assert VerificationReport().supported_claim_ratio == 1.0


def test_supported_ratio_counts_only_fully_supported():
    report = VerificationReport(
        claims=[
            _claim("1", VerificationStatus.SUPPORTED),
            _claim("2", VerificationStatus.PARTIALLY_SUPPORTED),
            _claim("3", VerificationStatus.UNSUPPORTED),
            _claim("4", VerificationStatus.SUPPORTED),
        ]
    )
    assert report.supported_claim_ratio == 0.5


@pytest.mark.parametrize(
    "status,risk,expected",
    [
        (VerificationStatus.UNSUPPORTED, RiskLevel.HIGH, True),
        (VerificationStatus.CONTRADICTED, RiskLevel.CRITICAL, True),
        (VerificationStatus.UNSUPPORTED, RiskLevel.LOW, False),
        (VerificationStatus.SUPPORTED, RiskLevel.CRITICAL, False),
        (VerificationStatus.PARTIALLY_SUPPORTED, RiskLevel.HIGH, False),
    ],
)
def test_unsupported_high_risk_detection(status, risk, expected):
    """The single most important safety signal, so every corner of it is pinned."""
    report = VerificationReport(claims=[_claim("1", status, risk)])
    assert report.has_unsupported_high_risk_claim is expected


# --------------------------------------------------------------------------
# Span — redaction is a contract, not a convention
# --------------------------------------------------------------------------


def _span(**attributes) -> Span:
    return Span(
        id="s1",
        trace_id="t1",
        kind=SpanKind.AGENT,
        name="evidence",
        started_at=NOW,
        attributes=attributes,
    )


def test_span_accepts_allow_listed_attributes():
    span = _span(agent="evidence", model="gemini-flash-latest", rounds=2)
    assert span.attributes["agent"] == "evidence"


def test_span_rejects_attributes_outside_the_allow_list():
    """An allow-list fails closed. A deny-list would let the next
    clinical-content field through by default, which in this domain is PHI."""
    with pytest.raises(ValidationError, match="allow-listed"):
        _span(patient_name="Jane Doe")


def test_span_rejects_free_form_content_even_alongside_valid_keys():
    with pytest.raises(ValidationError, match="allow-listed"):
        _span(agent="evidence", query_text="patient with atrial fibrillation")


# --------------------------------------------------------------------------
# RunState — derived views the wire contract depends on
# --------------------------------------------------------------------------


def test_run_state_agent_outputs_projection():
    """`_persist` and the SSE `final` event are shaped around this projection,
    so it is derived rather than duplicated."""
    state = RunState(
        trace_id="t1",
        request="q",
        agent_results={
            "evidence": AgentResult(agent="evidence", content="evidence output"),
            "drug-safety": AgentResult(agent="drug-safety", content="interaction output"),
        },
    )
    assert state.agent_outputs == {
        "evidence": "evidence output",
        "drug-safety": "interaction output",
    }


def test_run_state_agents_involved_is_sorted():
    """Sorted matches the frozen wire contract and the persisted column."""
    state = RunState(
        trace_id="t1",
        request="q",
        agent_results={name: AgentResult(agent=name) for name in ["radiology", "evidence", "laboratory"]},
    )
    assert state.agents_involved == ["evidence", "laboratory", "radiology"]


def test_run_state_rejects_unknown_field():
    """The TypedDict this replaces silently accepted and dropped typo'd keys."""
    with pytest.raises(ValidationError):
        RunState(trace_id="t1", request="q", final_anser="typo")


def test_run_state_round_trips_through_json():
    """Serializability is what lets state be checkpointed later without
    readopting a workflow framework."""
    state = RunState(
        trace_id="t1",
        request="first-line therapy?",
        claims=[_claim("c1", VerificationStatus.SUPPORTED)],
        citation_report=CitationReport(verified=["ADA, 2024"], total_checked=1),
        agent_results={"evidence": AgentResult(agent="evidence", content="out")},
    )
    restored = RunState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_evidence_record_round_trips_with_enums_as_strings():
    record = EvidenceRecord(
        id="e1",
        source="ADA Standards of Care",
        source_type="guideline",
        retrieval_method="hybrid",
        relevance=0.91,
        citation={"label": "[ADA Standards of Care in Diabetes, 2024]"},
        originating_agent="evidence",
        timestamp=NOW,
    )
    payload = record.model_dump(mode="json")
    assert payload["source_type"] == "guideline"
    assert payload["retrieval_method"] == "hybrid"
    assert EvidenceRecord.model_validate(payload) == record


def test_token_usage_total():
    assert TokenUsage(prompt_tokens=100, completion_tokens=25).total_tokens == 125
