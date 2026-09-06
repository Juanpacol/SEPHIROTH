"""Sending, and every way it goes wrong.

A push service is a third party this product cannot fix, so the failure modes
are the design. The one that matters most is `TestNothingReachesTheTick`: the
tick is also reminding people about appointments and reconciling tasks, and a
push service having a bad afternoon must not stop any of that.

Verifies AC-025-04, AC-025-05, AC-025-06, AC-025-07
(docs/specs/SPEC-025-pwa-push.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

import api.workflows.push as push_module
from api.workflows.push import PushResult, classify_status, dispatch_due
from data.schemas import Notification, PushDelivery, PushSubscription, User

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 6, 9, 0)


@pytest.fixture
def push_configured(monkeypatch):
    def _set(**overrides):
        import core.config as config_module
        from core.config import Settings

        settings = Settings(
            _env_file=None,
            environment="development",
            vapid_public_key="pub",
            vapid_private_key="priv",
            **overrides,
        )
        monkeypatch.setattr(config_module, "settings", settings)
        monkeypatch.setattr(push_module, "settings", settings)
        return settings

    return _set


def _sends(monkeypatch, *results):
    """Script the send outcomes, and record what was sent."""
    calls = []
    queue = list(results)

    async def _fake(subscription, payload):
        calls.append((subscription.endpoint, payload))
        return queue.pop(0) if queue else PushResult("sent")

    monkeypatch.setattr(push_module, "send_one", _fake)
    return calls


async def _setup(session, *, devices=1, type_="clinical_alert", message="Ana tiene un potasio de 6.2"):
    user = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name="Dra. Ruiz",
        hashed_password="x",
        role="clinician",
    )
    session.add(user)
    await session.flush()

    notification = Notification(id=str(uuid4()), user_id=user.id, type=type_, message=message)
    session.add(notification)
    await session.flush()

    subscriptions = []
    for _ in range(devices):
        subscription = PushSubscription(
            id=str(uuid4()),
            user_id=user.id,
            endpoint=f"https://push.example/{uuid4().hex}",
            p256dh="key",
            auth="secret",
            created_at=NOW,
        )
        session.add(subscription)
        await session.flush()
        session.add(
            PushDelivery(
                id=str(uuid4()),
                subscription_id=subscription.id,
                notification_id=notification.id,
                status="pending",
                send_after=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        subscriptions.append(subscription)
    await session.flush()
    return user, notification, subscriptions


async def _delivery(session):
    return (await session.scalars(select(PushDelivery))).first()


class TestItSendsFromTheTick:
    """AC-025-04."""

    async def test_a_due_delivery_is_sent_and_marked(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session)
        calls = _sends(monkeypatch, PushResult("sent"))

        sent, failed = await dispatch_due(db_session, NOW)
        await db_session.flush()

        assert (sent, failed) == (1, 0)
        assert len(calls) == 1
        assert (await _delivery(db_session)).status == "sent"

    async def test_what_is_sent_carries_no_patient_content(self, db_session, push_configured, monkeypatch):
        """The end-to-end version of the payload guarantee: the notification's
        own message names a patient and a value, and what leaves does not."""
        push_configured()
        await _setup(db_session)
        calls = _sends(monkeypatch, PushResult("sent"))

        await dispatch_due(db_session, NOW)

        (_endpoint, payload) = calls[0]
        rendered = " ".join(str(value) for value in payload.values()).lower()
        for fragment in ("ana", "potasio", "6.2"):
            assert fragment not in rendered

    async def test_a_delivery_not_yet_due_is_left_alone(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session)
        delivery = await _delivery(db_session)
        delivery.send_after = NOW + timedelta(minutes=5)
        await db_session.flush()
        calls = _sends(monkeypatch)

        sent, _failed = await dispatch_due(db_session, NOW)

        assert (sent, calls) == (0, [])

    async def test_a_success_clears_the_device_failure_history(
        self, db_session, push_configured, monkeypatch
    ):
        push_configured()
        _user, _notification, (subscription,) = await _setup(db_session)
        subscription.failure_count = 2
        await db_session.flush()
        _sends(monkeypatch, PushResult("sent"))

        await dispatch_due(db_session, NOW)

        assert subscription.failure_count == 0
        assert subscription.last_success_at == NOW

    async def test_each_device_gets_its_own_attempt(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session, devices=3)
        calls = _sends(monkeypatch)

        sent, _failed = await dispatch_due(db_session, NOW)

        assert sent == 3
        assert len({endpoint for endpoint, _ in calls}) == 3

    async def test_the_batch_is_bounded(self, db_session, push_configured, monkeypatch):
        push_configured(push_batch_size=2)
        await _setup(db_session, devices=5)
        _sends(monkeypatch)

        sent, _failed = await dispatch_due(db_session, NOW)

        assert sent == 2


class TestAGoneSubscription:
    """AC-025-05 — the browser threw it away, and no retry will bring it back."""

    @pytest.mark.parametrize("status", [404, 410])
    def test_those_statuses_mean_gone(self, status):
        assert classify_status(status) == "gone"

    async def test_it_is_disabled_rather_than_deleted(self, db_session, push_configured, monkeypatch):
        """A person looking at their device list should see that the phone they
        replaced stopped working, not find a row silently absent."""
        push_configured()
        _user, _notification, (subscription,) = await _setup(db_session)
        _sends(monkeypatch, PushResult("gone", "410 Gone"))

        await dispatch_due(db_session, NOW)
        await db_session.flush()

        assert subscription.disabled_at == NOW
        assert (
            await db_session.scalar(select(PushSubscription.id).where(PushSubscription.id == subscription.id))
        ) is not None

    async def test_its_other_pending_deliveries_are_dropped(self, db_session, push_configured, monkeypatch):
        """Nothing will ever reach that endpoint, so leaving them pending is a
        queue that retries forever."""
        push_configured()
        _user, _notification, (subscription,) = await _setup(db_session)
        second = Notification(
            id=str(uuid4()), user_id=subscription.user_id, type="clinical_alert", message="otra"
        )
        db_session.add(second)
        await db_session.flush()
        db_session.add(
            PushDelivery(
                id=str(uuid4()),
                subscription_id=subscription.id,
                notification_id=second.id,
                status="pending",
                send_after=NOW + timedelta(hours=1),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await db_session.flush()
        _sends(monkeypatch, PushResult("gone", "410 Gone"))

        await dispatch_due(db_session, NOW)
        await db_session.flush()

        statuses = {d.status for d in (await db_session.scalars(select(PushDelivery))).all()}
        assert statuses == {"dropped"}

    async def test_a_disabled_device_is_not_retried(self, db_session, push_configured, monkeypatch):
        push_configured()
        _user, _notification, (subscription,) = await _setup(db_session)
        subscription.disabled_at = NOW
        await db_session.flush()
        calls = _sends(monkeypatch)

        await dispatch_due(db_session, NOW)

        assert calls == []
        assert (await _delivery(db_session)).status == "dropped"


class TestTransientFailure:
    """AC-025-06."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_those_statuses_are_worth_retrying(self, status):
        assert classify_status(status) == "transient"

    async def test_it_is_rescheduled_rather_than_failed(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session)
        _sends(monkeypatch, PushResult("transient", "503"))

        sent, failed = await dispatch_due(db_session, NOW)
        await db_session.flush()

        delivery = await _delivery(db_session)
        assert (sent, failed) == (0, 0), "still coming, so neither sent nor failed"
        assert delivery.status == "pending"
        assert delivery.send_after > NOW
        assert delivery.attempts == 1

    async def test_backoff_grows(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session)
        _sends(monkeypatch, PushResult("transient"), PushResult("transient"))

        await dispatch_due(db_session, NOW)
        first = (await _delivery(db_session)).send_after
        await dispatch_due(db_session, first)
        second = (await _delivery(db_session)).send_after

        assert (second - first) > (first - NOW)

    async def test_it_gives_up_after_the_cap(self, db_session, push_configured, monkeypatch):
        push_configured(push_max_attempts=3)
        await _setup(db_session)
        _sends(monkeypatch, *[PushResult("transient", "503")] * 3)

        moment = NOW
        for _ in range(3):
            await dispatch_due(db_session, moment)
            await db_session.flush()
            moment = (await _delivery(db_session)).send_after or moment

        delivery = await _delivery(db_session)
        assert delivery.status == "failed"
        assert delivery.attempts == 3

    async def test_a_payload_too_large_fails_immediately(self, db_session, push_configured, monkeypatch):
        """A retry sends the same bytes, so retrying only fails identically on
        a schedule."""
        assert classify_status(413) == "permanent"

        push_configured()
        await _setup(db_session)
        _sends(monkeypatch, PushResult("permanent", "413"))

        _sent, failed = await dispatch_due(db_session, NOW)
        await db_session.flush()

        assert failed == 1
        assert (await _delivery(db_session)).status == "failed"

    async def test_a_failure_counts_against_the_device(self, db_session, push_configured, monkeypatch):
        push_configured()
        _user, _notification, (subscription,) = await _setup(db_session)
        _sends(monkeypatch, PushResult("transient"))

        await dispatch_due(db_session, NOW)

        assert subscription.failure_count == 1


class TestNothingReachesTheTick:
    """AC-025-07 — the tick is also reminding people about appointments."""

    async def test_a_send_that_raises_is_caught(self, db_session, push_configured, monkeypatch):
        push_configured()
        await _setup(db_session)

        async def _explode(subscription, payload):
            raise RuntimeError("the push library exploded")

        monkeypatch.setattr(push_module, "send_one", _explode)

        sent, failed = await dispatch_due(db_session, NOW)
        await db_session.flush()

        assert (sent, failed) == (0, 0)
        assert (await _delivery(db_session)).status == "pending", "retried, not lost"

    async def test_a_notification_deleted_underneath_is_dropped(
        self, db_session, push_configured, monkeypatch
    ):
        push_configured()
        _user, notification, _subs = await _setup(db_session)
        await db_session.delete(notification)
        await db_session.flush()
        calls = _sends(monkeypatch)

        await dispatch_due(db_session, NOW)
        await db_session.flush()

        assert calls == []
        assert (await _delivery(db_session)).status == "dropped"

    async def test_the_tick_reports_what_it_sent(self, db_session, push_configured, monkeypatch):
        """Counted on the summary but deliberately absent from `to_dict()` --
        the cron response shape is frozen."""
        from api.workflows.engine import TickSummary

        summary = TickSummary(tick_id="T1")
        assert summary.push_sent == 0
        assert "push_sent" not in summary.to_dict()


class TestClassification:
    @pytest.mark.parametrize("status", [200, 201, 202])
    def test_success_is_success(self, status):
        assert classify_status(status) == "sent"

    def test_an_unknown_status_is_retried_rather_than_discarded(self):
        """Being wrong in the direction of trying again costs a retry; being
        wrong the other way loses a notification."""
        assert classify_status(418) == "transient"
