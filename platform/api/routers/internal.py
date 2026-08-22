"""The workflow tick — the one entry point that lets something happen
without a human initiating an HTTP request. Deliberately NOT under
`/api` and NOT guarded by any of the JWT-based deps in `auth/deps.py`:
every one of those resolves a `User`, and cron has no user. Minting a
service JWT for a third-party cron config would park a permanent
clinician-role credential outside this system's control. Guarded
instead by a single shared-secret header, same trust model as
`render.yaml`'s other `sync: false` secrets.

See SPEC-009 for the full tick algorithm; `platform/api/workflows/engine.py`
is the only module that actually touches the DB for it.
"""

from __future__ import annotations

import hmac
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_session

from ..workflows.engine import TickSummary, run_tick
from ..workflows.ops_notify import get_ops_notifier

router = APIRouter()

#: Cap on how many failed-step entries a single Slack message names --
#: a batch of 25 failures shouldn't become a 25-line message.
_MAX_NAMED_FAILURES = 5


def _check_tick_token(x_internal_token: str | None) -> None:
    expected = settings.internal_tick_token or ""
    if not expected or not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid tick token")


def _ops_notify_fields(summary: TickSummary) -> dict:
    """Builds the Slack payload from a `TickSummary` -- counters plus, on a
    tick with failures, enough to look the step up (`workflow_id`/
    `step_id`), never `patient_id`. Keys are the allow-listed subset
    `ops_notify._format_text` will accept; anything else would raise."""
    fields: dict = {
        "tick_id": summary.tick_id,
        "claimed": summary.claimed,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "remaining": summary.remaining,
        "events_dispatched": summary.events_dispatched,
    }
    if summary.failed_steps:
        shown = summary.failed_steps[:_MAX_NAMED_FAILURES]
        step_ids = ",".join(s["step_id"] for s in shown)
        extra = len(summary.failed_steps) - len(shown)
        if extra > 0:
            step_ids += f",+{extra} more"
        fields["step_id"] = step_ids
        fields["workflow_id"] = ",".join(s["workflow_id"] for s in shown)
        fields["step_type"] = ",".join(s["step_type"] for s in shown)
    return fields


@router.post("/internal/tick")
async def tick(
    x_internal_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not settings.enable_workflow_engine:
        return {"status": "disabled"}
    _check_tick_token(x_internal_token)
    summary = await run_tick(session, tick_id=uuid4().hex[:12])
    # Fires after run_tick returns, never inside it: run_tick has no
    # try/except of its own, so a Slack outage must never be able to turn
    # a healthy tick into a 500. Silent on an empty tick (nothing claimed,
    # nothing failed) -- see ops_notify.py; at one tick per 5 minutes a
    # "still alive, did nothing" message every time would drown real signal.
    if summary.succeeded or summary.failed:
        await get_ops_notifier().notify(_ops_notify_fields(summary))
    return summary.to_dict()


__all__ = ["router"]
