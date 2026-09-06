"""Registering a browser for push, and listing the ones already registered.

Available to every authenticated user, not only clinicians: the subscription
belongs to whoever is signed in, and every handler derives the user from the
token rather than taking an id. There is no parameter here a caller could
tamper with, which is the same posture `portal.py` takes.

The device list exists so a person can recognise their own phone and turn it
off. Without it, "why am I getting these on a tablet I gave away" has no answer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.workflows.push import push_enabled
from auth.deps import get_current_user
from core.config import settings
from core.db import get_session
from data.schemas import PushDelivery, PushSubscription, User

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=500)
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=500)


def _out(subscription: PushSubscription) -> Dict[str, Any]:
    return {
        "id": subscription.id,
        # Never the whole endpoint: it is a capability URL. Anyone holding it
        # plus the keys can send to that browser, and a device list is not a
        # place to hand one out again.
        "endpoint_hint": subscription.endpoint[-12:],
        "user_agent": subscription.user_agent,
        "enabled": subscription.disabled_at is None,
        "failure_count": subscription.failure_count,
        "last_success_at": (
            subscription.last_success_at.isoformat() if subscription.last_success_at else None
        ),
        "created_at": subscription.created_at.isoformat(),
    }


@router.get("/key", summary="The VAPID public key a browser needs to subscribe")
async def public_key(_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """`enabled: false` rather than a 404 when no keys are configured.

    The toggle needs to tell the difference between "this deployment does not
    do push" and "something is broken", and those look identical from a 404.
    """
    return {"enabled": push_enabled(), "public_key": settings.vapid_public_key or None}


@router.post("/subscriptions", status_code=201, summary="Register this browser")
async def subscribe(
    body: SubscribeRequest,
    user_agent: Optional[str] = Header(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Idempotent on the endpoint, and it moves between users.

    A shared machine is the normal case in a clinic: the second person to
    enable push on it gets the same endpoint from the browser, and the
    subscription has to follow them rather than keep buzzing for whoever
    registered it first.
    """
    if not push_enabled():
        raise HTTPException(status_code=503, detail="Push is not configured on this deployment")

    now = _now()
    existing = (
        await session.scalars(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    ).first()

    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        existing.user_agent = (user_agent or "")[:200]
        # Re-registering is how a browser says the subscription is live again,
        # so the failure history that disabled it is cleared with it.
        existing.disabled_at = None
        existing.failure_count = 0
        await session.commit()
        return _out(existing)

    subscription = PushSubscription(
        id=str(uuid4()),
        user_id=user.id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=(user_agent or "")[:200],
        created_at=now,
    )
    session.add(subscription)
    await session.commit()
    return _out(subscription)


@router.get("/subscriptions", summary="This user's registered devices")
async def list_subscriptions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, List[Dict[str, Any]]]:
    rows = (
        await session.scalars(
            select(PushSubscription)
            .where(PushSubscription.user_id == user.id)
            .order_by(PushSubscription.created_at.desc())
        )
    ).all()
    return {"items": [_out(row) for row in rows]}


@router.delete("/subscriptions", status_code=204, summary="Unregister this browser")
async def unsubscribe(
    body: UnsubscribeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deletes the row rather than disabling it.

    A person turning push off on their own device is not the same event as a
    subscription going stale: there is nothing for them to see afterwards, and
    a disabled row would reappear in their device list looking like a fault.
    """
    subscription = (
        await session.scalars(
            select(PushSubscription).where(
                PushSubscription.endpoint == body.endpoint,
                PushSubscription.user_id == user.id,
            )
        )
    ).first()
    if subscription is None:
        # Already gone. Unsubscribing twice is not an error -- the browser may
        # have dropped the subscription before telling us.
        return

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
        delivery.last_error = "unsubscribed"

    await session.delete(subscription)
    await session.commit()


__all__ = ["router"]
