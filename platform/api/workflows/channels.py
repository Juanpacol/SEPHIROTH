"""Notification delivery seam.

Two implementations behind one protocol. `InAppChannel` writes the
`Notification` row that `scheduling.py`/`results.py` already wrote;
`CompositeChannel` adds web push on top of it (SPEC-025) without changing the
signature six call sites depend on.

The composition is deliberately one-way: push is enqueued **only when the
in-app write succeeded**. `Notification.dedupe_key` stays the single source of
truth for "already delivered", rather than two mechanisms that agree until the
day they do not.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data.schemas import Notification

logger = logging.getLogger(__name__)


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
        url: Optional[str] = None,
    ) -> bool:
        """Returns True if a new notification was created, False if
        `dedupe_key` had already been used (already delivered).

        `url` is where a push tap should land. Optional and ignored by the
        in-app channel, so no existing call site changes -- a route is not
        patient content, and the destination page enforces its own auth.
        """
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
        url: Optional[str] = None,
    ) -> bool:
        return (
            await self.create(
                session,
                user_id,
                type_,
                message,
                dedupe_key=dedupe_key,
                related_appointment_id=related_appointment_id,
            )
            is not None
        )

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        type_: str,
        message: str,
        *,
        dedupe_key: Optional[str] = None,
        related_appointment_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """The row itself, or None when `dedupe_key` was already used.

        Returned rather than stashed on the instance: this channel is a
        module-level singleton, and remembering "the last notification" on it
        would be two concurrent requests racing over one attribute.
        """
        try:
            async with session.begin_nested():
                notification = Notification(
                    id=str(uuid4()),
                    user_id=user_id,
                    type=type_,
                    message=message,
                    related_appointment_id=related_appointment_id,
                    dedupe_key=dedupe_key,
                )
                session.add(notification)
                await session.flush()
            return notification
        except IntegrityError:
            return None


class CompositeChannel:
    """In-app, and then push.

    Push is enqueued only on a genuinely new notification, and enqueueing does
    no I/O -- it writes delivery rows that the tick sends later (SPEC-025 §1).
    An HTTP call to a push service inside a booking's transaction would tie
    that booking's latency and its success to a third party.

    A failure to enqueue never fails the send. The in-app notification is the
    guarantee; push is the attempt to get someone's attention sooner.
    """

    def __init__(self, in_app: Optional["InAppChannel"] = None):
        self.in_app = in_app or InAppChannel()

    async def send(
        self,
        session: AsyncSession,
        user_id: str,
        type_: str,
        message: str,
        *,
        dedupe_key: Optional[str] = None,
        related_appointment_id: Optional[str] = None,
        url: Optional[str] = None,
    ) -> bool:
        notification = await self.in_app.create(
            session,
            user_id,
            type_,
            message,
            dedupe_key=dedupe_key,
            related_appointment_id=related_appointment_id,
        )
        if notification is None:
            return False

        try:
            from .push import enqueue

            await enqueue(session, notification=notification, url=url)
        except Exception:  # pragma: no cover - defensive
            logger.exception("could not enqueue push for notification %s", notification.id)
        return True


_channel: NotificationChannel = CompositeChannel()


def get_channel() -> NotificationChannel:
    return _channel


__all__ = ["NotificationChannel", "InAppChannel", "CompositeChannel", "get_channel"]
