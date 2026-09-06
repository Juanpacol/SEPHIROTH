"""Registering a browser, and the ownership rules around it.

The case worth having a test for is a shared machine, which is the normal one
in a clinic: the second person to enable push gets the same endpoint from the
browser, and the subscription has to follow them rather than keep buzzing for
whoever registered it first.

Verifies AC-025-09 (docs/specs/SPEC-025-pwa-push.md).
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import api.workflows.push as push_module
from api.routers import push as push_router_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import PushDelivery, PushSubscription

pytestmark = pytest.mark.asyncio

ENDPOINT = "https://push.example/endpoint-aaaaaaaaaaaa"
CREDS = {"email": "push-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}
OTHER = {"email": "push-other@example.org", "name": "Dr. Otro", "password": "password123"}


@pytest.fixture
def configured(monkeypatch):
    def _set(enabled: bool = True):
        import core.config as config_module
        from core.config import Settings

        overrides = {"vapid_public_key": "pub", "vapid_private_key": "priv"} if enabled else {}
        settings = Settings(_env_file=None, environment="development", **overrides)
        monkeypatch.setattr(config_module, "settings", settings)
        monkeypatch.setattr(push_module, "settings", settings)
        monkeypatch.setattr(push_router_module, "settings", settings)
        return settings

    return _set


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(push_router_module.router, prefix="/api/push")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _token(client, creds=CREDS):
    return (await client.post("/api/auth/register", json=creds)).json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _body(endpoint=ENDPOINT):
    return {"endpoint": endpoint, "p256dh": "public-key-value", "auth": "secret"}


class TestTheKey:
    async def test_it_hands_out_the_public_key(self, client, configured):
        configured()
        headers = _headers(await _token(client))

        res = await client.get("/api/push/key", headers=headers)

        assert res.json() == {"enabled": True, "public_key": "pub"}

    async def test_it_says_disabled_rather_than_404(self, client, configured):
        """The toggle needs to tell "this deployment does not do push" from
        "something is broken", and those look identical from a 404."""
        configured(enabled=False)
        headers = _headers(await _token(client))

        res = await client.get("/api/push/key", headers=headers)

        assert res.status_code == 200
        assert res.json() == {"enabled": False, "public_key": None}

    async def test_it_needs_a_session(self, client, configured):
        configured()
        assert (await client.get("/api/push/key")).status_code in (401, 403)


class TestRegistering:
    async def test_a_browser_registers_once(self, client, configured, db_session):
        configured()
        headers = _headers(await _token(client))

        res = await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        assert res.status_code == 201
        assert res.json()["enabled"] is True
        assert len((await db_session.scalars(select(PushSubscription))).all()) == 1

    async def test_registering_twice_keeps_one_row(self, client, configured, db_session):
        configured()
        headers = _headers(await _token(client))

        await client.post("/api/push/subscriptions", json=_body(), headers=headers)
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        assert len((await db_session.scalars(select(PushSubscription))).all()) == 1

    async def test_it_moves_between_users_on_a_shared_machine(self, client, configured, db_session):
        """The normal case in a clinic. The subscription has to follow whoever
        enabled it last, rather than keep buzzing for the previous person."""
        configured()
        first = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=first)
        second = _headers(await _token(client, OTHER))

        await client.post("/api/push/subscriptions", json=_body(), headers=second)

        rows = (await db_session.scalars(select(PushSubscription))).all()
        assert len(rows) == 1
        mine = (await client.get("/api/push/subscriptions", headers=second)).json()["items"]
        assert len(mine) == 1

    async def test_the_previous_owner_stops_seeing_it(self, client, configured):
        configured()
        first = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=first)
        second = _headers(await _token(client, OTHER))
        await client.post("/api/push/subscriptions", json=_body(), headers=second)

        theirs = (await client.get("/api/push/subscriptions", headers=first)).json()["items"]

        assert theirs == []

    async def test_re_registering_revives_a_disabled_subscription(self, client, configured, db_session):
        """Re-registering is the browser saying the subscription is live again,
        so the failure history that disabled it goes with it."""
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)
        subscription = (await db_session.scalars(select(PushSubscription))).one()
        subscription.disabled_at = subscription.created_at
        subscription.failure_count = 3
        await db_session.commit()

        res = await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        assert res.json()["enabled"] is True
        assert res.json()["failure_count"] == 0

    async def test_it_is_refused_when_push_is_not_configured(self, client, configured):
        configured(enabled=False)
        headers = _headers(await _token(client))

        res = await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        assert res.status_code == 503

    async def test_a_malformed_subscription_is_rejected(self, client, configured):
        configured()
        headers = _headers(await _token(client))

        res = await client.post(
            "/api/push/subscriptions", json={"endpoint": "x", "p256dh": "y", "auth": "z"}, headers=headers
        )

        assert res.status_code == 422


class TestTheDeviceList:
    async def test_it_never_returns_the_whole_endpoint(self, client, configured):
        """The endpoint is a capability URL: anyone holding it plus the keys
        can send to that browser, and a device list is not a place to hand one
        out again."""
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        (item,) = (await client.get("/api/push/subscriptions", headers=headers)).json()["items"]

        assert ENDPOINT not in str(item)
        assert item["endpoint_hint"] == ENDPOINT[-12:]

    async def test_it_shows_only_this_users_devices(self, client, configured):
        configured()
        mine = _headers(await _token(client))
        theirs = _headers(await _token(client, OTHER))
        await client.post("/api/push/subscriptions", json=_body(), headers=mine)
        await client.post(
            "/api/push/subscriptions", json=_body("https://push.example/other-bbbbbbbb"), headers=theirs
        )

        items = (await client.get("/api/push/subscriptions", headers=mine)).json()["items"]

        assert len(items) == 1

    async def test_a_disabled_device_still_appears(self, client, configured, db_session):
        """So "why did my old phone stop working" has an answer."""
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)
        subscription = (await db_session.scalars(select(PushSubscription))).one()
        subscription.disabled_at = subscription.created_at
        await db_session.commit()

        (item,) = (await client.get("/api/push/subscriptions", headers=headers)).json()["items"]

        assert item["enabled"] is False


class TestUnregistering:
    async def test_it_removes_the_row(self, client, configured, db_session):
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        res = await client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT}, headers=headers
        )

        assert res.status_code == 204
        assert (await db_session.scalars(select(PushSubscription))).all() == []

    async def test_it_drops_what_was_queued_for_that_device(self, client, configured, db_session):
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)
        subscription = (await db_session.scalars(select(PushSubscription))).one()
        from data.schemas import Notification

        notification = Notification(
            id=str(uuid4()), user_id=subscription.user_id, type="clinical_alert", message="x"
        )
        db_session.add(notification)
        await db_session.flush()
        db_session.add(
            PushDelivery(
                id=str(uuid4()),
                subscription_id=subscription.id,
                notification_id=notification.id,
                status="pending",
            )
        )
        await db_session.commit()

        await client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT}, headers=headers
        )

        (delivery,) = (await db_session.scalars(select(PushDelivery))).all()
        assert delivery.status == "dropped"

    async def test_unregistering_twice_is_not_an_error(self, client, configured):
        """The browser may have dropped the subscription before telling us."""
        configured()
        headers = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=headers)

        first = await client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT}, headers=headers
        )
        second = await client.request(
            "DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT}, headers=headers
        )

        assert (first.status_code, second.status_code) == (204, 204)

    async def test_it_cannot_remove_somebody_elses_device(self, client, configured, db_session):
        configured()
        mine = _headers(await _token(client))
        await client.post("/api/push/subscriptions", json=_body(), headers=mine)
        theirs = _headers(await _token(client, OTHER))

        await client.request("DELETE", "/api/push/subscriptions", json={"endpoint": ENDPOINT}, headers=theirs)

        assert len((await db_session.scalars(select(PushSubscription))).all()) == 1
