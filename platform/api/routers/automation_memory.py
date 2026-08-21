"""`/api/automation-memory` -- read/write operational preferences
(SPEC-015). Clinician-only: even `scope="patient"` memory (e.g. a
patient's preferred quiet hours) is configured by staff today, since
there's no patient-facing settings surface yet.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import require_clinician
from core.db import get_session
from data.schemas import User

from ..workflows.memory import ALLOWED_KEYS, InvalidMemoryKey, get_memory, set_memory

router = APIRouter()


@router.get("/keys")
async def list_allowed_keys(clinician: User = Depends(require_clinician)) -> Dict[str, str]:
    return dict(ALLOWED_KEYS)


@router.get("")
async def read_memory(
    scope: str,
    scope_id: str,
    key: str,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        value = await get_memory(session, scope, scope_id, key)
    except InvalidMemoryKey as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"scope": scope, "scope_id": scope_id, "key": key, "value": value}


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    scope_id: str
    key: str
    value: Any


@router.put("")
async def write_memory(
    body: MemoryWrite,
    clinician: User = Depends(require_clinician),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        await set_memory(session, body.scope, body.scope_id, body.key, body.value)
    except InvalidMemoryKey as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    return {"scope": body.scope, "scope_id": body.scope_id, "key": body.key, "value": body.value}


__all__ = ["router"]
