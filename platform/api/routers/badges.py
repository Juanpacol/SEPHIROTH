"""Every counter the chrome shows, in one request.

The frontend polled twice on a 30-second interval for these: the dashboard
bootstrap for its stats, and `NotificationBell` for the unread count. Adding a
third poll for the task badge would have made three requests every 30 seconds
per open tab, all of them counting rows.

Deliberately not part of `/api/dashboard`: that router is clinician-only and
returns aggregates over patient data, while the unread-notification count
belongs to whoever is asking, patient included. Keeping them apart is what lets
this route carry `get_current_user` instead of `require_clinician`.

No PHI: counters only, never a title or a patient name — which is also what
makes it safe to poll from a tab left open on a shared screen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user
from core.db import get_session
from data.schemas import Alert, Notification, Task, User

from ..services.task_service import OPEN_STATUSES

router = APIRouter()


@router.get("", summary="Counters for the navigation badges")
async def badges(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    unread = int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )

    # A patient has no inbox and no alerts; returning zeros keeps the response
    # shape stable so the frontend needs no role branch to read it.
    if user.role == "patient":
        return {"tasks_open": 0, "tasks_overdue": 0, "alerts_active": 0, "notifications_unread": unread}

    tasks_open = int(
        await session.scalar(select(func.count()).select_from(Task).where(Task.status.in_(OPEN_STATUSES)))
        or 0
    )
    tasks_overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status.in_(OPEN_STATUSES), Task.due_at.is_not(None), Task.due_at < now)
        )
        or 0
    )
    alerts_active = int(
        await session.scalar(select(func.count()).select_from(Alert).where(Alert.status == "active")) or 0
    )

    return {
        "tasks_open": tasks_open,
        "tasks_overdue": tasks_overdue,
        "alerts_active": alerts_active,
        "notifications_unread": unread,
    }


__all__ = ["router"]
