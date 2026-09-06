"""Getting a notification onto a device that is not currently looking.

Two halves, deliberately far apart in time.

**Enqueueing** happens inside the caller's transaction and does no I/O: it
writes one `PushDelivery` row per enabled device. An HTTP call to a push service
inside a booking's transaction would tie that booking's latency and its success
to a third party.

**Dispatching** happens on the tick. The cost is up to one tick of latency —
five minutes — which is the right trade for a reminder or an escalation and the
wrong one for anything conversational, which is why the patient portal is out of
scope (SPEC-025 NG-4).

Nothing here ever raises into the tick. A push service having a bad afternoon
must not stop appointments being reminded.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from data.schemas import Notification, PushDelivery, PushSubscription

from .memory import get_memory
from .push_payload import build_payload

logger = logging.getLogger(__name__)

#: Backoff between attempts, indexed by attempt number. Short, because a push
#: service outage is usually seconds and a notification that arrives an hour
#: late has already failed at its job.
_BACKOFF_SECONDS = (60, 300, 900)


def push_enabled() -> bool:
    """Whether this deployment can send at all.

    With no keys configured every path here is inert and the product behaves
    exactly as it did before this phase -- the state every existing deployment
    starts in (SPEC-025 B-9).
    """
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def active_subscriptions(session: AsyncSession, user_id: str) -> List[PushSubscription]:
    return list(
        (
            await session.scalars(
                select(PushSubscription).where(
                    PushSubscription.user_id == user_id,
                    PushSubscription.disabled_at.is_(None),
                )
            )
        ).all()
    )


async def _wants(session: AsyncSession, user_id: str, type_: str) -> bool:
    """Whether this user has asked for this kind of push.

    Two keys rather than one: `push_enabled` is the switch a person flips, and
    `notify_types` is the narrowing they do afterwards. An absent
    `notify_types` means "all of them", because a user who turned push on and
    never opened the list wants what they turned on.
    """
    enabled = await get_memory(session, "user", user_id, "push_enabled")
    if enabled is False:
        return False
    types = await get_memory(session, "user", user_id, "notify_types")
    if isinstance(types, list) and types:
        return type_ in types
    return True


async def enqueue(
    session: AsyncSession,
    *,
    notification: Notification,
    url: Optional[str] = None,
    now: Optional[datetime] = None,
) -> int:
    """One delivery row per enabled device. No I/O. Returns how many.

    Called only after the in-app write succeeded, so `Notification.dedupe_key`
    stays the single source of truth for "already delivered" -- two mechanisms
    for that would agree until the day they did not.
    """
    if not push_enabled():
        return 0
    if not await _wants(session, notification.user_id, notification.type):
        return 0

    moment = now or _now()
    created = 0
    for subscription in await active_subscriptions(session, notification.user_id):
        exists = (
            await session.scalars(
                select(PushDelivery).where(
                    PushDelivery.subscription_id == subscription.id,
                    PushDelivery.notification_id == notification.id,
                )
            )
        ).first()
        if exists is not None:
            continue
        session.add(
            PushDelivery(
                id=str(uuid4()),
                subscription_id=subscription.id,
                notification_id=notification.id,
                url=url or "",
                status="pending",
                send_after=moment,
                created_at=moment,
                updated_at=moment,
            )
        )
        created += 1
    return created


class PushResult:
    """What one send attempt means, classified rather than uniformly retried."""

    __slots__ = ("outcome", "detail")

    def __init__(self, outcome: str, detail: str = ""):
        #: "sent" | "gone" | "permanent" | "transient"
        self.outcome = outcome
        self.detail = detail[:200]


def classify_status(status_code: int) -> str:
    """A push service's answer, turned into what to do about it.

    404/410 is the one that matters: the browser threw the subscription away,
    and no amount of retrying will bring it back.
    """
    if status_code in (200, 201, 202):
        return "sent"
    if status_code in (404, 410):
        return "gone"
    if status_code == 413:
        # A retry sends the same bytes. Retrying is only ever going to fail
        # identically, three times, on a schedule.
        return "permanent"
    if status_code == 429 or 500 <= status_code < 600:
        return "transient"
    return "transient"


def _send_blocking(subscription: PushSubscription, payload: Dict[str, Any]) -> PushResult:
    """The actual HTTP call. Synchronous, because `pywebpush` is.

    Imported inside the function so the dependency is only required by a
    deployment that configures VAPID keys -- the same posture the optional
    provider clients take.
    """
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=10,
        )
        return PushResult(classify_status(getattr(response, "status_code", 201)))
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is None:
            return PushResult("transient", str(exc))
        return PushResult(classify_status(status), str(exc))
    except Exception as exc:  # pragma: no cover - defensive; see `dispatch_due`
        return PushResult("transient", f"{type(exc).__name__}: {exc}")


async def send_one(subscription: PushSubscription, payload: Dict[str, Any]) -> PushResult:
    return await asyncio.to_thread(_send_blocking, subscription, payload)


async def _disable(session: AsyncSession, subscription: PushSubscription, now: datetime) -> None:
    """The browser threw this subscription away. Disabled, not deleted.

    A person looking at their device list should see that the phone they
    replaced stopped working, rather than find a row silently absent.
    """
    subscription.disabled_at = now
    pending = (
        await session.scalars(
            select(PushDelivery).where(
                PushDelivery.subscription_id == subscription.id,
                PushDelivery.status == "pending",
            )
        )
    ).all()
    for delivery in pending:
        delivery.status = "dropped"
        delivery.last_error = "subscription gone"
        delivery.updated_at = now


async def _due(session: AsyncSession, now: datetime, limit: int) -> List[PushDelivery]:
    return list(
        (
            await session.scalars(
                select(PushDelivery)
                .where(PushDelivery.status == "pending", PushDelivery.send_after <= now)
                .order_by(PushDelivery.send_after)
                .limit(limit)
            )
        ).all()
    )


async def dispatch_due(
    session: AsyncSession, now: Optional[datetime] = None, limit: Optional[int] = None
) -> Tuple[int, int]:
    """Send what is due. Returns `(sent, failed)`.

    Every failure is caught. A push service having a bad afternoon must not
    stop the tick, which is also reminding people about appointments.
    """
    if not push_enabled():
        return 0, 0

    moment = now or _now()
    batch = await _due(session, moment, limit or settings.push_batch_size)
    sent = failed = 0

    for delivery in batch:
        subscription = await session.get(PushSubscription, delivery.subscription_id)
        notification = await session.get(Notification, delivery.notification_id)
        if subscription is None or notification is None or subscription.disabled_at is not None:
            delivery.status = "dropped"
            delivery.last_error = "subscription or notification is gone"
            delivery.updated_at = moment
            continue

        payload = build_payload(
            notification_id=notification.id,
            type_=notification.type,
            url=delivery.url or None,
        )

        delivery.attempts += 1
        try:
            result = await send_one(subscription, payload)
        except Exception as exc:  # pragma: no cover - `send_one` catches its own
            logger.exception("push send raised")
            result = PushResult("transient", f"{type(exc).__name__}: {exc}")

        if result.outcome == "sent":
            delivery.status = "sent"
            delivery.last_error = ""
            subscription.failure_count = 0
            subscription.last_success_at = moment
            sent += 1
        elif result.outcome == "gone":
            await _disable(session, subscription, moment)
            delivery.status = "dropped"
            delivery.last_error = result.detail or "subscription gone"
            failed += 1
        elif result.outcome == "permanent" or delivery.attempts >= settings.push_max_attempts:
            delivery.status = "failed"
            delivery.last_error = result.detail or "gave up"
            subscription.failure_count += 1
            failed += 1
        else:
            index = min(delivery.attempts - 1, len(_BACKOFF_SECONDS) - 1)
            delivery.send_after = moment + timedelta(seconds=_BACKOFF_SECONDS[index])
            delivery.last_error = result.detail or "transient"
            subscription.failure_count += 1

        delivery.updated_at = moment

    return sent, failed


__all__ = [
    "PushResult",
    "active_subscriptions",
    "classify_status",
    "dispatch_due",
    "enqueue",
    "push_enabled",
    "send_one",
]
