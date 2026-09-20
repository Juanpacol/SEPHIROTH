"""`/api/scheduling/agenda/today` — today's booked appointments for the
calling clinician; and a regression lock proving `/api/dashboard/stats`'s
shape is unchanged by this feature (per the plan's explicit decision not
to fold per-clinician agenda data into that global, unauthenticated-shaped
route)."""

from datetime import datetime, time, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import api.routers.scheduling as scheduling_router
from api.main import app
from core.db import get_session
from data.schemas import AvailabilityRule, Patient

pytestmark = pytest.mark.asyncio


class _FrozenDateTime(datetime):
    """A fixed, boring midday UTC instant (no midnight/DST/month-end
    adjacency). `test_agenda_counts_only_todays_booked_appointments` used
    to compute a fixed 22:30 UTC slot and assume it was "comfortably in
    the future" — it fails for real once the actual wall clock passes
    22:30 UTC each day, since the booking endpoint rejects a start_at
    that isn't strictly after `datetime.now()`. Freezing `now()` removes
    the dependency on when the suite happens to run, permanently."""

    @classmethod
    def now(cls, tz=None):
        frozen = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        return frozen if tz is not None else frozen.replace(tzinfo=None)


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="agenda-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Agenda", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def test_agenda_empty_when_no_appointments(client):
    async with client:
        headers, _ = await _clinician(client)
        res = await client.get("/api/scheduling/agenda/today", headers=headers)
        assert res.status_code == 200
        assert res.json() == {"date": res.json()["date"], "count": 0, "next_at": None, "items": []}


async def test_agenda_counts_only_todays_booked_appointments(client, db_session, monkeypatch):
    async with client:
        monkeypatch.setattr(scheduling_router, "datetime", _FrozenDateTime)
        headers, clinician_id = await _clinician(client)

        # `_FrozenDateTime` fixes "now" to a boring midday instant, so a
        # same-day slot a few hours later always exists, on the slot grid
        # (AvailabilityRule.slot_minutes default = 30, from 00:00 UTC —
        # see scheduling.expand_slots), on the one weekday that matters.
        now = _FrozenDateTime.now(timezone.utc)
        start_at = now.replace(hour=14, minute=0, second=0, microsecond=0)
        db_session.add(
            AvailabilityRule(
                id="agenda-rule",
                clinician_id=clinician_id,
                weekday=now.weekday(),
                start_time=time(0, 0),
                end_time=time(23, 59),
            )
        )
        patient = Patient(
            id="PAGENDA1", name="Agenda Patient", age=44, sex="F", medical_record_number="PT-PAGENDA1"
        )
        db_session.add(patient)
        await db_session.commit()

        booked = await client.post(
            "/api/scheduling/appointments",
            json={
                "clinician_id": clinician_id,
                "patient_id": patient.id,
                "start_at": start_at.isoformat(),
            },
            headers=headers,
        )
        assert booked.status_code == 201

        res = await client.get("/api/scheduling/agenda/today", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 1
        assert body["items"][0]["patient_name"] == "Agenda Patient"
        assert body["next_at"] == booked.json()["start_at"]


async def test_dashboard_stats_shape_unchanged_by_scheduling_feature(client, db_session):
    """Regression lock: scheduling/results must not touch
    `/api/dashboard/stats`'s response shape (last updated when the dashboard
    grew Clinical Priority Score fields alongside the risk-sorted
    critical-patients list — see tests/test_api_patients_rag.py for the
    shape's own coverage)."""
    async with client:
        headers, _ = await _clinician(client)
        res = await client.get("/api/dashboard/stats", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) == {
            "critical_patients",
            "critical_count",
            "moderate_count",
            "stable_count",
            "at_risk_count",
            "max_priority_score",
            "avg_priority_score",
        }
