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

from ..workflows.engine import run_tick

router = APIRouter()


def _check_tick_token(x_internal_token: str | None) -> None:
    expected = settings.internal_tick_token or ""
    if not expected or not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Invalid tick token")


@router.post("/internal/tick")
async def tick(
    x_internal_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not settings.enable_workflow_engine:
        return {"status": "disabled"}
    _check_tick_token(x_internal_token)
    summary = await run_tick(session, tick_id=uuid4().hex[:12])
    return summary.to_dict()


__all__ = ["router"]
