"""`classify`/`decide_recovery` — SPEC-007, executes `ADR-007`.

Verifies AC-007-01, AC-007-02 (docs/specs/SPEC-007-recovery.md)."""

from sephiroth.contracts import FailureCategory, RecoveryActionType
from sephiroth.models import LLMUnavailableError
from sephiroth.runtime.recovery import classify, decide_recovery


def test_classify_llm_unavailable_as_model():
    failure = classify(LLMUnavailableError("rate limited"), component="evidence")
    assert failure.category == FailureCategory.MODEL
    assert failure.component == "evidence"
    assert failure.message == "rate limited"


def test_classify_generic_exception_as_agent():
    failure = classify(RuntimeError("boom"), component="radiology")
    assert failure.category == FailureCategory.AGENT


def test_classify_carries_step_id_and_attempt():
    failure = classify(RuntimeError("boom"), component="radiology", step_id="s1", attempt=2)
    assert failure.step_id == "s1"
    assert failure.attempt == 2


def test_decide_retry_when_transient_and_attempts_remain():
    failure = classify(LLMUnavailableError("x"), component="evidence")
    assert decide_recovery(failure, attempt=1, max_attempts=2) == RecoveryActionType.RETRY


def test_decide_abstain_when_transient_but_exhausted():
    failure = classify(LLMUnavailableError("x"), component="evidence")
    assert decide_recovery(failure, attempt=2, max_attempts=2) == RecoveryActionType.ABSTAIN


def test_decide_abstain_immediately_for_non_transient_category():
    failure = classify(RuntimeError("boom"), component="radiology")
    assert decide_recovery(failure, attempt=1, max_attempts=2) == RecoveryActionType.ABSTAIN


def test_decide_never_returns_fallback_or_replan():
    """SPEC-007 NG-1/NG-2: FALLBACK and REPLAN are out of scope this cycle
    — one agent per capability, no dynamic planner to revise against."""
    for category in FailureCategory:
        failure = classify(RuntimeError("x"), component="c")
        failure = failure.model_copy(update={"category": category})
        for attempt in range(1, 4):
            action = decide_recovery(failure, attempt=attempt, max_attempts=2)
            assert action in {RecoveryActionType.RETRY, RecoveryActionType.ABSTAIN}
