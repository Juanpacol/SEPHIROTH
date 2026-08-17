"""Recovery engine — classify a failure, then pick an action (SPEC-007,
executes `ADR-007`).

Before this module, an agent raising propagated uncaught and aborted the
whole consultation — a documented, tracked gap since Phase 3, never closed.
This is deliberately the simplest policy that satisfies the spec: a
transient failure (model unavailable, tool timeout) gets retried up to a
bound; once exhausted, the run continues without that agent's section
rather than aborting everything.

`REPLAN` is explicitly out of scope (see `docs/specs/SPEC-007-recovery.md`
NG-1) — there is no dynamic planner yet to revise a plan against; replanning
over a static, four-branch route has nothing to reconsider.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sephiroth.contracts import Failure, FailureCategory, RecoveryActionType
from sephiroth.models import LLMUnavailableError


def classify(exc: Exception, component: str, step_id: str | None = None, attempt: int = 1) -> Failure:
    """Maps an exception to a `Failure` record. `LLMUnavailableError` (rate
    limit, quota exhaustion, transient outage) is `MODEL`; anything else
    raised by an agent's turn is `AGENT` — the taxonomy is coarse by
    design, matching what's actually distinguishable at this call site."""
    category = FailureCategory.MODEL if isinstance(exc, LLMUnavailableError) else FailureCategory.AGENT
    return Failure(
        id=uuid.uuid4().hex,
        category=category,
        component=component,
        message=str(exc),
        step_id=step_id,
        attempt=attempt,
        timestamp=datetime.now(timezone.utc),
    )


def decide_recovery(failure: Failure, attempt: int, max_attempts: int) -> RecoveryActionType:
    """`RETRY` while attempts remain for a transient category
    (`MODEL`/`TOOL`); `ABSTAIN` once exhausted. `FALLBACK` doesn't apply
    today — there is one agent per capability, no alternative to fall back
    to (see SPEC-007 NG-2)."""
    transient = {FailureCategory.MODEL, FailureCategory.TOOL}
    if failure.category in transient and attempt < max_attempts:
        return RecoveryActionType.RETRY
    return RecoveryActionType.ABSTAIN


__all__ = ["classify", "decide_recovery"]
