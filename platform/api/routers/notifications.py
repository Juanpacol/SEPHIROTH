"""In-app notifications — the whole delivery mechanism today (no email/
SMS/push channel exists anywhere in this codebase). Every route is scoped
to the caller's own `user.id`, never a client-supplied id — same
isolation discipline as `portal.py`."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user
from core.db import get_session
from data.schemas import Notification, User

router = APIRouter()


def _out(n: Notification) -> Dict[str, Any]:
    return {
        "id": n.id,
        "type": n.type,
        "message": n.message,
        "related_appointment_id": n.related_appointment_id,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat(),
    }


@router.get("")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    rows = (
        await session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [_out(n) for n in rows]


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return {"count": count or 0}


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    from datetime import datetime, timezone

    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
