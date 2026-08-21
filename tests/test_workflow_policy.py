"""Pure unit tests for `sephiroth.workflows.policy` — no DB, no I/O."""

from datetime import datetime, timedelta

from sephiroth.contracts.enums import FailureCategory, RecoveryActionType
from sephiroth.workflows.policy import (
    classify_step_failure,
    decide_step_recovery,
    is_stale,
    next_run_after,
)


def test_is_stale_none_lateness_never_stale():
    due = datetime(2026, 1, 1)
    now = due + timedelta(days=365)
    assert is_stale(due, now, None) is False


def test_is_stale_within_window_is_not_stale():
    due = datetime(2026, 1, 1, 0, 0)
    now = due + timedelta(hours=5)
    assert is_stale(due, now, max_lateness_seconds=6 * 3600) is False


def test_is_stale_past_window_is_stale():
    due = datetime(2026, 1, 1, 0, 0)
    now = due + timedelta(hours=7)
    assert is_stale(due, now, max_lateness_seconds=6 * 3600) is True


def test_next_run_after_backoff_grows_and_caps():
    now = datetime(2026, 1, 1)
    first = next_run_after(1, now)
    second = next_run_after(2, now)
    tenth = next_run_after(10, now)
    assert (first - now).total_seconds() == 30
    assert (second - now).total_seconds() == 60
    assert (tenth - now).total_seconds() == 3600  # capped


def test_classify_step_failure_is_tool_category():
    failure = classify_step_failure(RuntimeError("db gone away"))
    assert failure.category == FailureCategory.TOOL
    assert "db gone away" in failure.detail


def test_decide_step_recovery_retries_then_abstains():
    assert decide_step_recovery(attempts=1, max_attempts=3) == RecoveryActionType.RETRY
    assert decide_step_recovery(attempts=2, max_attempts=3) == RecoveryActionType.RETRY
    assert decide_step_recovery(attempts=3, max_attempts=3) == RecoveryActionType.ABSTAIN
