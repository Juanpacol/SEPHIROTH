"""Tests for the Agent Auditor (Fase 6 of the runtime audit) — builds
`ExecutionTrace` fixtures directly (no live model needed) covering each
finding category: redundant tool calls, skipped tool calls, unused
selected agents, unsupported claims, and abstention."""

from datetime import datetime, timezone

from sephiroth.contracts import (
    AbstentionDecision,
    AbstentionReason,
    AgentResult,
    Claim,
    ExecutionTrace,
    ResponseStatus,
    RiskLevel,
    ToolCall,
    VerificationReport,
    VerificationStatus,
)
from sephiroth.telemetry.agent_auditor import audit_trace


def _trace(**overrides):
    base = dict(
        trace_id="t1",
        created_at=datetime.now(timezone.utc),
        request="What is the target A1C?",
    )
    base.update(overrides)
    return ExecutionTrace(**base)


def _tool_call(agent, tool, id_suffix=""):
    return ToolCall(id=f"{agent}-{tool}-{id_suffix}", tool=tool, agent=agent, arguments={}, result={})


def test_clean_run_has_no_findings():
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[_tool_call("evidence", "search_clinical_guidelines")],
        agent_calls=[AgentResult(agent="evidence", content="An answer.")],
    )
    report = audit_trace(trace)
    assert report.findings == []
    assert report.total_tool_calls == 1
    assert report.redundant_call_count == 0


def test_redundant_tool_call_detected():
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[
            _tool_call("evidence", "search_clinical_guidelines", "1"),
            _tool_call("evidence", "search_clinical_guidelines", "2"),
            _tool_call("evidence", "search_clinical_guidelines", "3"),
        ],
        agent_calls=[AgentResult(agent="evidence", content="An answer.")],
    )
    report = audit_trace(trace)
    assert report.redundant_call_count == 1
    categories = {f.category for f in report.findings}
    assert "redundant_tool_call" in categories
    msg = next(f.message for f in report.findings if f.category == "redundant_tool_call")
    assert "3x" in msg


def test_skipped_tool_call_detected_when_agent_answers_without_calling_tools():
    """The qwen2.5:14b failure mode found in the Fase 5 eval run: selected
    but never actually called its tool."""
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[],
        agent_calls=[AgentResult(agent="evidence", content="An answer from parametric knowledge.")],
    )
    report = audit_trace(trace)
    categories = {f.category for f in report.findings}
    assert "skipped_tool_call" in categories


def test_coordinator_not_flagged_for_skipping_tools():
    """Coordinator legitimately has no retrieval tools of its own — should
    never trigger skipped_tool_call."""
    trace = _trace(
        selected_agents=["coordinator"],
        tool_calls=[],
        agent_calls=[AgentResult(agent="coordinator", content="Summary.")],
    )
    report = audit_trace(trace)
    assert all(f.category != "skipped_tool_call" for f in report.findings)


def test_unused_selected_agent_detected():
    trace = _trace(
        selected_agents=["drug_safety"],
        tool_calls=[],
        agent_calls=[],
    )
    report = audit_trace(trace)
    categories = {f.category for f in report.findings}
    assert "unused_selected_agent" in categories


def test_unsupported_claims_detected():
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[_tool_call("evidence", "search_clinical_guidelines")],
        agent_calls=[AgentResult(agent="evidence", content="An answer.")],
        verification=VerificationReport(
            claims=[
                Claim(
                    id="c1",
                    text="ADA recommends <7%.",
                    originating_agent="evidence",
                    risk=RiskLevel.LOW,
                    status=VerificationStatus.SUPPORTED,
                ),
                Claim(
                    id="c2",
                    text="Relaxed target <8% for elderly.",
                    originating_agent="recommendation",
                    risk=RiskLevel.HIGH,
                    status=VerificationStatus.UNSUPPORTED,
                ),
            ]
        ),
    )
    report = audit_trace(trace)
    categories = {f.category for f in report.findings}
    assert "unsupported_claim" in categories
    assert report.supported_claim_ratio == 0.5


def test_abstention_surfaced():
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[_tool_call("evidence", "search_clinical_guidelines")],
        agent_calls=[AgentResult(agent="evidence", content="An answer.")],
        abstention=AbstentionDecision(
            status=ResponseStatus.ABSTAIN,
            reason=AbstentionReason.INSUFFICIENT_EVIDENCE,
            confidence=0.2,
            supported_claim_ratio=0.2,
            message="Can't confidently answer.",
        ),
    )
    report = audit_trace(trace)
    assert report.abstained is True
    categories = {f.category for f in report.findings}
    assert "abstention" in categories


def test_non_abstaining_run_not_flagged_as_abstained():
    trace = _trace(
        selected_agents=["evidence"],
        tool_calls=[_tool_call("evidence", "search_clinical_guidelines")],
        agent_calls=[AgentResult(agent="evidence", content="An answer.")],
        abstention=AbstentionDecision(status=ResponseStatus.ANSWER),
    )
    report = audit_trace(trace)
    assert report.abstained is False
    assert all(f.category != "abstention" for f in report.findings)


def test_as_dict_shape():
    trace = _trace(selected_agents=["evidence"], tool_calls=[], agent_calls=[])
    report = audit_trace(trace)
    d = report.as_dict()
    assert d["trace_id"] == "t1"
    assert "findings" in d and isinstance(d["findings"], list)
