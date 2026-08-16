"""Rate limiting and retry backoff, shared across providers.

Extracted from `GeminiClient._throttle`/`_generate`
(`intelligence/llm/gemini_client.py`, pre-Phase-1) — the only place this logic
existed. `describe_image` there duplicated its own copy of the retry loop
rather than reusing `_generate`; `GroqClient` had no rate limiter at all. Both
gaps are closed by giving every provider one shared, independently-tested
implementation instead of a second copy.

`backoff_delay` takes `cap` as a parameter rather than a constant because
Gemini's retry loop caps at 30s and Groq's caps at 10s today — parameterizing
preserves each provider's exact existing behavior rather than unifying it.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, List


class RateLimiter:
    """Cooperative sliding-window limiter: blocks until fewer than
    `rpm_limit` calls occurred in the trailing 60 seconds."""

    def __init__(
        self,
        rpm_limit: int,
        time_source: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.rpm_limit = rpm_limit
        self._time_source = time_source
        self._sleep = sleep
        self._request_times: List[float] = []

    async def acquire(self) -> None:
        window = 60.0
        while True:
            now = self._time_source()
            self._request_times = [t for t in self._request_times if now - t < window]
            if len(self._request_times) < self.rpm_limit:
                self._request_times.append(now)
                return
            wait_for = window - (now - self._request_times[0])
            await self._sleep(max(wait_for, 0.05))


def backoff_delay(attempt: int, cap: int, jitter: Callable[[float, float], float] = random.uniform) -> float:
    """`min(2**attempt, cap) + jitter(0, 1)` — the exact formula both retry
    loops used inline before this extraction."""
    return min(2**attempt, cap) + jitter(0, 1)


__all__ = ["RateLimiter", "backoff_delay"]
