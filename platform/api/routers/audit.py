"""Read-only review of the PHI access log — clinician-only (guarded at the
router-include level in `api/main.py`, same as `patients`/`dashboard`)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from data.schemas import PhiAccessLog

router = APIRouter()


def _entry(row: PhiAccessLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "patient_id": row.patient_id,
        "route": row.route,
        "method": row.method,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/access-log")
async def list_access_log(
    patient_id: Optional[str] = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    stmt = select(PhiAccessLog).order_by(PhiAccessLog.created_at.desc()).limit(min(limit, 500))
    if patient_id:
        stmt = stmt.where(PhiAccessLog.patient_id == patient_id)
    rows = (await session.scalars(stmt)).all()
    return [_entry(r) for r in rows]
