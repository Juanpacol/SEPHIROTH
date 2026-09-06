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
from datetime import datetime, time, timedelta, timezone, tzinfo
from random import Random
from typing import Optional

from sephiroth.contracts.enums import FailureCategory, RecoveryActionType

STEP_BACKOFF_BASE_SECONDS = 30
STEP_BACKOFF_CAP_SECONDS = 60 * 60

#: Module-level so `jittered` has a default without every caller passing one.
_RNG = Random()


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


def jittered(delta: timedelta, rng: Optional[Random] = None) -> timedelta:
    """Spread a recurring interval by ±10%.

    Deliberately NOT applied to retry backoff, where the docstring above still
    holds: at a 5-minute cron cadence the tick granularity dwarfs any jitter on
    a 30-second base, and `workflow_tick_batch_size` already caps concurrency.

    It matters where the fan-out is real. A standing job enrolled once per
    patient and rescheduled at a fixed interval lands every one of those steps
    in the same tick forever; ±10% is enough to smear them across ticks so a
    clinic with more patients than `batch_size` does not permanently starve the
    tail of the list.

    `rng` is injectable so a test can be deterministic without patching the
    module's globals.
    """
    source = rng or _RNG
    factor = source.uniform(0.9, 1.1)
    return timedelta(seconds=delta.total_seconds() * factor)


def quiet_window_end(now: datetime, start_hhmm: str, end_hhmm: str, tz: "tzinfo") -> Optional[datetime]:
    """When the quiet window `now` falls inside closes, or `None` if it does
    not fall inside one.

    Quiet hours are wall-clock: "no messages between 22:00 and 08:00" means the
    patient's evening, not a UTC offset. Every datetime in this schema is naive
    UTC, so the comparison happens in local time and the answer converts back.

    The window wraps midnight far more often than not (22:00 -> 08:00 is the
    normal case, not the edge case), which is the whole reason this is a
    function rather than two comparisons at the call site.
    """
    local = now.replace(tzinfo=timezone.utc).astimezone(tz)
    start = _parse_hhmm(start_hhmm)
    end = _parse_hhmm(end_hhmm)
    if start is None or end is None or start == end:
        return None

    today = local.date()
    start_at = datetime.combine(today, start, tzinfo=tz)
    end_at = datetime.combine(today, end, tzinfo=tz)

    if start < end:
        # Same-day window, e.g. 13:00 -> 15:00.
        if not (start_at <= local < end_at):
            return None
        closes = end_at
    else:
        # Wraps midnight, e.g. 22:00 -> 08:00. Either we are after the start
        # (tonight) or before the end (this morning, from last night's window).
        if local >= start_at:
            closes = datetime.combine(today + timedelta(days=1), end, tzinfo=tz)
        elif local < end_at:
            closes = end_at
        else:
            return None

    return closes.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_hhmm(value: str) -> Optional[time]:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        # A malformed window must not silence notifications. The allow-list in
        # `workflows/memory.py` validates on write, so this only fires on a
        # hand-edited row -- and "send it" is the safe failure.
        return None


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
    "jittered",
    "quiet_window_end",
    "StepFailure",
    "classify_step_failure",
    "decide_step_recovery",
    "STEP_BACKOFF_BASE_SECONDS",
    "STEP_BACKOFF_CAP_SECONDS",
]
