"""List endpoints that stop growing with the clinic's history.

Four endpoints built a query, applied filters, and returned every matching row.
That is fine on a demo and it is an outage on a three-year-old clinic: every
alert ever raised, serialised into one response, on a 30-second poll.

The cap goes on and the count goes in a header rather than changing the body
shape, because several callers destructure the array directly and the problem
here is size, not shape (SPEC-027 NG-1).

Verifies AC-027-06 (docs/specs/SPEC-027-hardening.md).
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.paging import TOTAL_HEADER
from api.routers import alerts as alerts_module
from api.routers import followups as followups_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Alert, FollowupPlan, Patient

CREDS = {"email": "bounded-doc@example.org", "name": "Dra. Ruiz", "password": "password123"}

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(alerts_module.router, prefix="/api/alerts")
    api.include_router(followups_module.router, prefix="/api/followups")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def headers(client):
    token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def patient(db_session):
    row = Patient(id="PBR1", name="Ana", age=61, sex="F", medical_record_number="MRN-PBR1")
    db_session.add(row)
    await db_session.commit()
    return row


async def _alerts(session, patient, count, severity="high"):
    base = datetime(2026, 9, 6, 9, 0)
    for index in range(count):
        session.add(
            Alert(
                id=str(uuid4()),
                patient_id=patient.id,
                category="lab",
                severity=severity,
                title=f"Alerta {index}",
                source="risk_engine",
                created_at=base - timedelta(minutes=index),
            )
        )
    await session.commit()


class TestAlerts:
    async def test_it_returns_everything_when_there_is_little(self, client, headers, patient, db_session):
        await _alerts(db_session, patient, 5)

        res = await client.get("/api/alerts", headers=headers)

        assert len(res.json()) == 5
        assert res.headers[TOTAL_HEADER] == "5"

    async def test_it_caps_when_there_is_a_lot(self, client, headers, patient, db_session):
        await _alerts(db_session, patient, 30)

        res = await client.get("/api/alerts?limit=10", headers=headers)

        assert len(res.json()) == 10

    async def test_it_says_what_it_left_out(self, client, headers, patient, db_session):
        """A caller that reads the header can tell it was truncated. One that
        does not behaves exactly as before."""
        await _alerts(db_session, patient, 30)

        res = await client.get("/api/alerts?limit=10", headers=headers)

        assert res.headers[TOTAL_HEADER] == "30"

    async def test_the_total_respects_the_filters(self, client, headers, patient, db_session):
        """The count reuses the caller's own statement, so the two cannot
        disagree about what "total" means -- a hand-written second query is a
        filter somebody forgets to add."""
        await _alerts(db_session, patient, 8, severity="high")
        await _alerts(db_session, patient, 3, severity="low")

        res = await client.get("/api/alerts?severity=low", headers=headers)

        assert res.headers[TOTAL_HEADER] == "3"
        assert len(res.json()) == 3

    async def test_offset_walks_the_list(self, client, headers, patient, db_session):
        await _alerts(db_session, patient, 12)

        first = (await client.get("/api/alerts?limit=5", headers=headers)).json()
        second = (await client.get("/api/alerts?limit=5&offset=5", headers=headers)).json()

        assert {a["id"] for a in first}.isdisjoint({a["id"] for a in second})

    async def test_the_body_shape_did_not_change(self, client, headers, patient, db_session):
        """Still a bare array. Callers destructure it directly, and this phase
        is about size (NG-1)."""
        await _alerts(db_session, patient, 3)

        body = (await client.get("/api/alerts", headers=headers)).json()

        assert isinstance(body, list)
        assert "id" in body[0]

    async def test_an_absurd_limit_is_refused(self, client, headers):
        """Otherwise the cap is advisory: `?limit=999999` restores the
        unbounded read the cap exists to prevent."""
        res = await client.get("/api/alerts?limit=100000", headers=headers)

        assert res.status_code == 422

    async def test_the_default_is_bounded(self, client, headers, patient, db_session):
        """The endpoint has to be safe for a caller that passes nothing, which
        is every caller that exists today."""
        await _alerts(db_session, patient, 3)

        res = await client.get("/api/alerts", headers=headers)

        assert res.status_code == 200
        assert TOTAL_HEADER in res.headers


class TestFollowups:
    async def test_it_caps_and_counts(self, client, headers, patient, db_session):
        from sqlalchemy import select

        from data.schemas import User

        clinician = (await db_session.scalars(select(User))).first()
        for index in range(15):
            db_session.add(
                FollowupPlan(
                    id=str(uuid4()),
                    patient_id=patient.id,
                    created_by_user_id=clinician.id,
                    instructions=f"Control {index}",
                    status="active",
                )
            )
        await db_session.commit()

        res = await client.get("/api/followups?limit=5", headers=headers)

        assert len(res.json()) == 5
        assert res.headers[TOTAL_HEADER] == "15"
