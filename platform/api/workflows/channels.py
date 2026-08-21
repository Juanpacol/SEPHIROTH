"""Notification delivery seam. One implementation today (in-app,
reusing the `Notification` table `scheduling.py`/`results.py` already
write to) behind a `NotificationChannel` protocol, so a later channel
(email/SMS) is a new class, not a rewrite of every call site.
"""

from __future__ import annotations

from typing import Optional, Protocol
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Notification


class NotificationChannel(Protocol):
    async def send(
        self,
        session: AsyncSession,
        user_id: str,
        type_: str,
        message: str,
        *,
        dedupe_key: Optional[str] = None,
        related_appointment_id: Optional[str] = None,
    ) -> bool:
        """Returns True if a new notification was created, False if
        `dedupe_key` had already been used (already delivered)."""
        ...


class InAppChannel:
    """Wraps the existing `Notification` row insert
    (`platform/api/routers/scheduling.py::_notify`) with a savepoint so a
    duplicate `dedupe_key` is a no-op rather than poisoning the caller's
    transaction -- the same `IntegrityError` pattern the booking race
    already uses in that router."""

    async def send(
        self,
        session: AsyncSession,
        user_id: str,
        type_: str,
        message: str,
        *,
        dedupe_key: Optional[str] = None,
        related_appointment_id: Optional[str] = None,
    ) -> bool:
        try:
            async with session.begin_nested():
                session.add(
                    Notification(
                        id=str(uuid4()),
                        user_id=user_id,
                        type=type_,
                        message=message,
                        related_appointment_id=related_appointment_id,
                        dedupe_key=dedupe_key,
                    )
                )
                await session.flush()
            return True
        except IntegrityError:
            return False


_channel = InAppChannel()


def get_channel() -> NotificationChannel:
    return _channel


__all__ = ["NotificationChannel", "InAppChannel", "get_channel"]
