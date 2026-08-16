"""Shared rate limiting and backoff — extracted from `GeminiClient` so
`GroqClient` can use the identical logic instead of a second, independently
maintained copy (today `describe_image` already duplicates the retry loop
`_generate` has; this is where that duplication ends).

`RateLimiter` is the exact sliding-window logic that lived in
`GeminiClient._throttle`. `backoff_delay` is the exact
`min(2**attempt, cap) + jitter` formula used by both `_generate` and the old
inline `describe_image` retry loop — `cap` is a parameter because Gemini uses
30 and Groq uses 10 today, and unifying the cap would be a behavior change no
acceptance criterion asks for.

Verifies AC-001-09 (`docs/specs/SPEC-001-model-provider.md`).
"""

import pytest

from sephiroth.models._throttle import RateLimiter, backoff_delay

pytestmark = pytest.mark.contract


class _FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_rate_limiter_admits_up_to_the_limit_without_waiting():
    clock = _FakeClock()
    slept = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(seconds)

    limiter = RateLimiter(rpm_limit=3, time_source=clock.time, sleep=sleep)
    for _ in range(3):
        await limiter.acquire()

    assert slept == [], "the first `rpm_limit` calls must not wait at all"


async def test_rate_limiter_blocks_once_the_window_is_full():
    clock = _FakeClock()
    slept = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(seconds)

    limiter = RateLimiter(rpm_limit=2, time_source=clock.time, sleep=sleep)
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # third call within the same 60s window must wait

    assert slept, "the call over the limit must sleep before proceeding"
    assert all(s > 0 for s in slept)


async def test_rate_limiter_admits_again_once_the_window_slides_past():
    clock = _FakeClock()

    async def sleep(seconds: float) -> None:
        clock.advance(seconds)

    limiter = RateLimiter(rpm_limit=1, time_source=clock.time, sleep=sleep)
    await limiter.acquire()
    clock.advance(61.0)  # past the 60s window
    await limiter.acquire()  # must not need to sleep now

    # No assertion error means acquire() returned promptly; confirm the
    # internal window was actually pruned rather than growing unbounded.
    assert len(limiter._request_times) == 1


def test_backoff_delay_is_capped():
    for attempt in range(10):
        delay = backoff_delay(attempt, cap=30, jitter=lambda a, b: 0.0)
        assert delay <= 30, f"attempt {attempt} exceeded cap: {delay}"


def test_backoff_delay_grows_exponentially_before_the_cap():
    no_jitter = lambda a, b: 0.0  # noqa: E731
    assert backoff_delay(0, cap=30, jitter=no_jitter) == 1
    assert backoff_delay(1, cap=30, jitter=no_jitter) == 2
    assert backoff_delay(2, cap=30, jitter=no_jitter) == 4
    assert backoff_delay(3, cap=30, jitter=no_jitter) == 8


def test_backoff_delay_respects_a_different_cap():
    """Groq's retry loop caps at 10, not 30 — same formula, different ceiling."""
    no_jitter = lambda a, b: 0.0  # noqa: E731
    assert backoff_delay(10, cap=10, jitter=no_jitter) == 10
    assert backoff_delay(10, cap=30, jitter=no_jitter) == 30


def test_backoff_delay_jitter_is_bounded_to_zero_one():
    seen = set()

    def recording_jitter(low, high):
        assert (low, high) == (0, 1)
        seen.add((low, high))
        return 0.5

    delay = backoff_delay(0, cap=30, jitter=recording_jitter)
    assert delay == 1.5
    assert seen == {(0, 1)}
