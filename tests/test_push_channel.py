"""Enqueueing: who gets a push, and when nothing is enqueued at all.

Three ways nothing happens, and each is deliberate. A duplicate in-app write
enqueues nothing, because `Notification.dedupe_key` stays the one source of
truth for "already delivered". A user who has not opted in gets nothing. And a
deployment with no VAPID keys behaves exactly as it did before this phase,
which is the state every existing deployment starts in.

Verifies AC-025-02, AC-025-03, AC-025-08 (docs/specs/SPEC-025-pwa-push.md).
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

import api.workflows.push as push_module
from api.workflows.channels import CompositeChannel, InAppChannel
from api.workflows.memory import set_memory
from data.schemas import Notification, PushDelivery, PushSubscription, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 9, 0)


@pytest.fixture
def push_configured(monkeypatch):
    """A deployment with VAPID keys, so the push paths are live."""

    def _set(enabled: bool = True):
        import core.config as config_module
        from core.config import Settings

        overrides = {"vapid_public_key": "pub", "vapid_private_key": "priv"} if enabled else {}
        settings = Settings(_env_file=None, environment="development", **overrides)
        monkeypatch.setattr(config_module, "settings", settings)
        monkeypatch.setattr(push_module, "settings", settings)
        return settings

    return _set


async def _user(session, name="Dra. Ruiz"):
    user = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name=name,
        hashed_password="x",
        role="clinician",
    )
    session.add(user)
    await session.flush()
    return user


async def _subscribe(session, user, endpoint=None):
    subscription = PushSubscription(
        id=str(uuid4()),
        user_id=user.id,
        endpoint=endpoint or f"https://push.example/{uuid4().hex}",
        p256dh="key",
        auth="secret",
        created_at=NOW,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def _deliveries(session):
    return (await session.scalars(select(PushDelivery))).all()


class TestEnqueueing:
    """AC-025-02."""

    async def test_a_new_notification_reaches_every_enabled_device(self, db_session, push_configured):
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        await _subscribe(db_session, user)

        created = await CompositeChannel().send(
            db_session, user.id, "clinical_alert", "Ana tiene un potasio de 6.2"
        )
        await db_session.flush()

        assert created is True
        assert len(await _deliveries(db_session)) == 2

    async def test_a_duplicate_in_app_write_enqueues_nothing(self, db_session, push_configured):
        """`Notification.dedupe_key` is the single source of truth for "already
        delivered". Two mechanisms for that would agree until the day they did
        not."""
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        channel = CompositeChannel()

        first = await channel.send(db_session, user.id, "clinical_alert", "x", dedupe_key="k1")
        second = await channel.send(db_session, user.id, "clinical_alert", "x", dedupe_key="k1")
        await db_session.flush()

        assert (first, second) == (True, False)
        assert len(await _deliveries(db_session)) == 1

    async def test_the_in_app_row_is_still_written(self, db_session, push_configured):
        """Push is the attempt to get attention sooner; the notification is the
        guarantee."""
        push_configured()
        user = await _user(db_session)

        await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert len((await db_session.scalars(select(Notification))).all()) == 1

    async def test_a_user_with_no_device_gets_a_notification_and_no_delivery(
        self, db_session, push_configured
    ):
        push_configured()
        user = await _user(db_session)

        await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert await _deliveries(db_session) == []

    async def test_a_disabled_device_is_skipped(self, db_session, push_configured):
        push_configured()
        user = await _user(db_session)
        subscription = await _subscribe(db_session, user)
        subscription.disabled_at = NOW

        await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert await _deliveries(db_session) == []

    async def test_the_landing_route_is_stored_on_the_row(self, db_session, push_configured):
        """Rather than in a process dictionary, which would grow without bound
        and lose every pending destination on restart."""
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)

        await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje", url="/tasks/T7")
        await db_session.flush()

        (delivery,) = await _deliveries(db_session)
        assert delivery.url == "/tasks/T7"

    async def test_enqueueing_twice_for_one_notification_does_not_double_buzz(
        self, db_session, push_configured
    ):
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        notification = Notification(id=str(uuid4()), user_id=user.id, type="clinical_alert", message="x")
        db_session.add(notification)
        await db_session.flush()

        await push_module.enqueue(db_session, notification=notification, now=NOW)
        await db_session.flush()
        await push_module.enqueue(db_session, notification=notification, now=NOW)
        await db_session.flush()

        assert len(await _deliveries(db_session)) == 1


class TestOptIn:
    """AC-025-03."""

    async def test_push_off_means_nothing_is_enqueued(self, db_session, push_configured):
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        await set_memory(db_session, "user", user.id, "push_enabled", False)

        await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert await _deliveries(db_session) == []

    async def test_a_muted_type_is_skipped(self, db_session, push_configured):
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        await set_memory(db_session, "user", user.id, "notify_types", ["alert_escalated"])

        await CompositeChannel().send(db_session, user.id, "appointment_booked", "mensaje")
        await db_session.flush()

        assert await _deliveries(db_session) == []

    async def test_a_chosen_type_gets_through(self, db_session, push_configured):
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        await set_memory(db_session, "user", user.id, "notify_types", ["alert_escalated"])

        await CompositeChannel().send(db_session, user.id, "alert_escalated", "mensaje")
        await db_session.flush()

        assert len(await _deliveries(db_session)) == 1

    async def test_no_preference_means_everything(self, db_session, push_configured):
        """A user who turned push on and never opened the type list wants what
        they turned on."""
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)

        await CompositeChannel().send(db_session, user.id, "waitlist_match", "mensaje")
        await db_session.flush()

        assert len(await _deliveries(db_session)) == 1

    async def test_an_empty_type_list_also_means_everything(self, db_session, push_configured):
        """An empty list is a person who cleared the form, not one who asked
        for silence -- `push_enabled: false` is how you ask for silence."""
        push_configured()
        user = await _user(db_session)
        await _subscribe(db_session, user)
        await set_memory(db_session, "user", user.id, "notify_types", [])

        await CompositeChannel().send(db_session, user.id, "waitlist_match", "mensaje")
        await db_session.flush()

        assert len(await _deliveries(db_session)) == 1


class TestDisabled:
    """AC-025-08 — the state every existing deployment starts in."""

    async def test_with_no_keys_nothing_is_enqueued(self, db_session, push_configured):
        push_configured(enabled=False)
        user = await _user(db_session)
        await _subscribe(db_session, user)

        created = await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert created is True, "the in-app notification still happens"
        assert await _deliveries(db_session) == []

    async def test_the_dispatcher_does_nothing(self, db_session, push_configured):
        push_configured(enabled=False)

        assert await push_module.dispatch_due(db_session, NOW) == (0, 0)

    async def test_push_enabled_reports_the_truth(self, push_configured):
        push_configured(enabled=False)
        assert push_module.push_enabled() is False

        push_configured(enabled=True)
        assert push_module.push_enabled() is True


class TestTheSignatureDidNotChange:
    """Six call sites depend on it."""

    async def test_the_in_app_channel_still_answers_the_old_call(self, db_session):
        created = await InAppChannel().send(db_session, "U1", "clinical_alert", "mensaje", dedupe_key="k")

        assert created is True

    async def test_the_composite_ignores_url_when_push_is_off(self, db_session, push_configured):
        """So a caller passing `url` never depends on push being configured."""
        push_configured(enabled=False)
        user = await _user(db_session)

        created = await CompositeChannel().send(
            db_session, user.id, "clinical_alert", "mensaje", url="/tasks"
        )

        assert created is True

    async def test_a_failure_to_enqueue_never_fails_the_send(self, db_session, push_configured, monkeypatch):
        """The in-app notification is the guarantee. Push is best effort, and
        best effort must not be able to lose the guarantee."""
        push_configured()
        user = await _user(db_session)

        async def _explode(*args, **kwargs):
            raise RuntimeError("enqueue is broken")

        monkeypatch.setattr(push_module, "enqueue", _explode)

        created = await CompositeChannel().send(db_session, user.id, "clinical_alert", "mensaje")
        await db_session.flush()

        assert created is True
        assert len((await db_session.scalars(select(Notification))).all()) == 1
