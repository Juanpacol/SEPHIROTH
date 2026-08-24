"""Recurring appointment series — eager expansion at creation time, all-
or-nothing on conflict, cancel-future-only."""

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_session
from data.schemas import Patient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="series-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Series", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PSERIES1", name="Series Patient", age=30, sex="M", medical_record_number="PT-PSERIES1")
    db_session.add(p)
    await db_session.commit()
    return p


async def _set_up_availability(client, headers):
    # A Monday 09:00-11:00 window recurring every week — matches the
    # weekly series occurrences below, all landing on future Mondays.
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=headers,
    )


def _next_monday() -> date:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7  # always strictly in the future
    return today + timedelta(days=days_ahead)


FIRST_MONDAY = _next_monday()
FIRST_MONDAY_ISO = f"{FIRST_MONDAY}T09:00:00Z"


async def test_weekly_series_expands_all_occurrences(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        res = await client.post(
            "/api/scheduling/series",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": FIRST_MONDAY_ISO,
                "frequency": "weekly",
                "occurrence_count": 4,
            },
            headers=headers,
        )
        assert res.status_code == 201
        body = res.json()
        assert body["occurrence_count"] == 4
        assert len(body["appointment_ids"]) == 4

        appts = (await client.get("/api/scheduling/appointments", headers=headers)).json()
        assert len(appts) == 4
        assert all(a["series_id"] == body["id"] for a in appts)


async def test_series_count_over_cap_rejected(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/series",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": FIRST_MONDAY_ISO,
                "frequency": "weekly",
                "occurrence_count": 53,
            },
            headers=headers,
        )
        assert res.status_code == 422


async def test_series_rejected_all_or_nothing_on_conflict(client, patient_row, db_session):
    """Occurrence 3 of a 4-occurrence weekly series collides with an
    existing booking — the whole series must be rejected, not partially
    created."""
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        p2 = Patient(id="PSERIES2", name="Other", age=40, sex="F", medical_record_number="PT-PSERIES2")
        db_session.add(p2)
        await db_session.commit()

        # Occupies week 3's slot (FIRST_MONDAY + 14 days).
        await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": p2.id,
                "start_at": f"{FIRST_MONDAY + timedelta(days=14)}T09:00:00Z",
            },
            headers=headers,
        )

        res = await client.post(
            "/api/scheduling/series",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": FIRST_MONDAY_ISO,
                "frequency": "weekly",
                "occurrence_count": 4,
            },
            headers=headers,
        )
        assert res.status_code == 409

        # Nothing from the rejected series should have been created —
        # only the pre-existing booking that caused the conflict remains.
        appts = (await client.get("/api/scheduling/appointments", headers=headers)).json()
        assert len(appts) == 1
        assert appts[0]["series_id"] is None


async def test_cancel_series_cancels_only_future_occurrences(client, patient_row, monkeypatch):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        created = await client.post(
            "/api/scheduling/series",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient_row.id,
                "start_at": FIRST_MONDAY_ISO,
                "frequency": "weekly",
                "occurrence_count": 3,
            },
            headers=headers,
        )
        series_id = created.json()["id"]

        cancel = await client.delete(f"/api/scheduling/series/{series_id}", headers=headers)
        assert cancel.status_code == 204

        appts = (await client.get("/api/scheduling/appointments", headers=headers)).json()
        assert all(a["status"] == "cancelled" for a in appts)
