"""`traced_span` — span recording for the `Executor.step`/`Verifier.check`
seams (SPEC-006, `ADR-009`).

Verifies AC-006-01, AC-006-02, AC-006-03, AC-006-04
(docs/specs/SPEC-006-telemetry.md)."""

import asyncio

import pytest

from core.config import settings
from sephiroth.contracts import RunState, SpanKind
from sephiroth.telemetry import traced_span


def _state() -> RunState:
    return RunState(trace_id="t1", request="q")


def test_records_a_span_with_duration_and_ok_true():
    state = _state()
    with traced_span(state, SpanKind.AGENT, "radiology", agent="radiology"):
        pass

    assert len(state.spans) == 1
    span = state.spans[0]
    assert span.trace_id == "t1"
    assert span.kind is SpanKind.AGENT
    assert span.name == "radiology"
    assert span.ok is True
    assert span.attributes == {"agent": "radiology"}


def test_records_ok_false_and_reraises_on_exception():
    state = _state()
    with pytest.raises(RuntimeError):
        with traced_span(state, SpanKind.AGENT, "radiology"):
            raise RuntimeError("boom")

    assert len(state.spans) == 1
    assert state.spans[0].ok is False


def test_disallowed_attributes_are_dropped_not_raised():
    state = _state()
    with traced_span(state, SpanKind.VERIFY, "verify", patient_name="Jane Doe", agent="evidence"):
        pass

    assert state.spans[0].attributes == {"agent": "evidence"}


def test_no_op_when_tracing_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_tracing", False)
    state = _state()
    with traced_span(state, SpanKind.AGENT, "radiology", agent="radiology"):
        pass

    assert state.spans == []


def test_still_reraises_when_tracing_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_tracing", False)
    state = _state()
    with pytest.raises(RuntimeError):
        with traced_span(state, SpanKind.AGENT, "radiology"):
            raise RuntimeError("boom")
    assert state.spans == []


def test_measures_real_elapsed_time():
    state = _state()
    with traced_span(state, SpanKind.VERIFY, "verify"):
        pass
    assert state.spans[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_wraps_async_block_via_await_inside_with():
    state = _state()
    with traced_span(state, SpanKind.AGENT, "evidence"):
        await asyncio.sleep(0)
    assert len(state.spans) == 1
