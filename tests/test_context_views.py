"""`context_for_agent`/`log_filtered_fields` — per-agent context projection
(F-034, SPEC-005). The enforcing rollout is validated indirectly by the
full existing suite (`tests/test_workflow.py`, `test_sse_contract.py`,
`test_api_agents.py`, `test_runtime_executor.py`) passing unmodified after
`src/sephiroth/runtime/executor.py` switched to calling `context_for_agent`
— no agent depended on a field outside its declared `context_fields`.

Verifies AC-005-01 (docs/specs/SPEC-005-context-engine.md)."""

from sephiroth.context.views import context_for_agent, log_filtered_fields
from sephiroth.contracts import AgentCapability, RunContext


def _capability(context_fields):
    return AgentCapability(id="x", node_name="x", name="X", context_fields=context_fields)


def _context():
    return RunContext(
        medications=["metformin"],
        lab_results={"a1c": "7.0"},
        image_path="/x.png",
        conditions=["diabetes"],
        history="past history",
        recent_consultations=["Q: x -> A: y"],
    )


def test_empty_context_fields_returns_every_field():
    capability = _capability([])
    result = context_for_agent(capability, _context())
    assert set(result.keys()) == set(RunContext.model_fields)


def test_declared_context_fields_filters_to_only_those():
    capability = _capability(["image_path", "conditions"])
    result = context_for_agent(capability, _context())
    assert set(result.keys()) == {"image_path", "conditions"}
    assert result["image_path"] == "/x.png"
    assert result["conditions"] == ["diabetes"]


def test_filtered_out_fields_are_absent_not_just_empty():
    capability = _capability(["medications"])
    result = context_for_agent(capability, _context())
    assert "lab_results" not in result
    assert "image_path" not in result
    assert result == {"medications": ["metformin"]}


def test_log_filtered_fields_does_not_raise_and_is_a_noop_for_full_view(caplog):
    capability = _capability([])
    log_filtered_fields(capability, _context())  # no context_fields declared -> nothing to log
    assert not any("context_fields_would_drop" in r.message for r in caplog.records)


def test_log_filtered_fields_logs_dropped_nonempty_fields(caplog):
    import logging

    capability = _capability(["conditions"])
    with caplog.at_level(logging.INFO, logger="sephiroth.context.views"):
        log_filtered_fields(capability, _context())
    messages = [r.message for r in caplog.records]
    assert any("context_fields_would_drop" in m and "agent=x" in m for m in messages)
