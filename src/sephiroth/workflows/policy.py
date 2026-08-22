"""Staleness and retry policy for workflow steps -- pure functions, no I/O.

`decide_step_recovery` is deliberately a *new* function, not a reuse of
`sephiroth.runtime.recovery.decide_recovery`: that one only retries a
`MODEL`/`TOOL` failure category, so a step's dominant real failure mode
(a transient DB/network error, classified `AGENT` by the runtime's
`classify`) would never retry. A durable step also has a scheduling
axis (`run_after`) an in-request retry never needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sephiroth.contracts.enums import FailureCategory, RecoveryActionType

STEP_BACKOFF_BASE_SECONDS = 30
STEP_BACKOFF_CAP_SECONDS = 60 * 60


def is_stale(due_at: datetime, now: datetime, max_lateness_seconds: Optional[int]) -> bool:
    """True if a step is too late to still be meaningful. `None` means
    "never stale" (e.g. an internal catch-up-forever step)."""
    if max_lateness_seconds is None:
        return False
    return (now - due_at) > timedelta(seconds=max_lateness_seconds)


def next_run_after(attempts: int, now: datetime) -> datetime:
    """Exponential backoff, capped, no jitter -- determinism over
    thundering-herd avoidance; the batch limit already caps concurrency."""
    delay = min(STEP_BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)), STEP_BACKOFF_CAP_SECONDS)
    return now + timedelta(seconds=delay)


@dataclass(frozen=True)
class StepFailure:
    category: FailureCategory
    detail: str


def classify_step_failure(exc: Exception) -> StepFailure:
    """Every non-programmer-error exception a step handler raises is
    treated as a transient TOOL failure -- workflow steps call out to
    the DB/notification channel, not a model, so there is no MODEL
    category to distinguish here."""
    return StepFailure(category=FailureCategory.TOOL, detail=str(exc)[:300])


def decide_step_recovery(attempts: int, max_attempts: int) -> RecoveryActionType:
    """RETRY while attempts remain, ABSTAIN (-> terminal 'failed') once
    exhausted. Unlike the agent-turn recovery policy, category never
    gates this -- every step failure is presumed transient until attempts
    run out, because there is nothing else to try."""
    if attempts < max_attempts:
        return RecoveryActionType.RETRY
    return RecoveryActionType.ABSTAIN


__all__ = [
    "is_stale",
    "next_run_after",
    "StepFailure",
    "classify_step_failure",
    "decide_step_recovery",
    "STEP_BACKOFF_BASE_SECONDS",
    "STEP_BACKOFF_CAP_SECONDS",
]
