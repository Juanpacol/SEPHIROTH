"""Waitlist: join/list/leave, and the synchronous match-on-cancel that
notifies the earliest-waiting request without auto-booking."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from auth.security import create_access_token, hash_password
from core.db import get_session
from data.schemas import Patient, User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="wait-clin@example.org") -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. Wait", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


@pytest.fixture
async def patient_row(db_session):
    p = Patient(id="PWAIT1", name="Waiting Patient", age=35, sex="F", medical_record_number="PT-PWAIT1")
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def patient_login(db_session, patient_row):
    user = User(
        id="user-pwait1",
        email="pwait1@example.org",
        name="Waiting Patient",
        hashed_password=hash_password("password123"),
        role="patient",
        patient_id=patient_row.id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _set_up_availability(client, headers):
    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=headers,
    )


NEXT_MONDAY_ISO = "2026-08-24T09:00:00Z"  # 2026-08-24 is a Monday


async def test_patient_joins_and_lists_waitlist(client, patient_row, patient_login):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/waitlist",
            json={
                "clinician_id": clinician_id,
                "window_start": "2026-08-24T09:00:00Z",
                "window_end": "2026-08-24T11:00:00Z",
            },
            headers=patient_login,
        )
        assert res.status_code == 201
        entry_id = res.json()["id"]

        listed = await client.get("/api/scheduling/waitlist", headers=patient_login)
        assert len(listed.json()) == 1
        assert listed.json()[0]["id"] == entry_id


async def test_clinician_cannot_join_waitlist(client, patient_row):
    async with client:
        headers, clinician_id = await _clinician(client)
        res = await client.post(
            "/api/scheduling/waitlist",
            json={
                "clinician_id": clinician_id,
                "window_start": "2026-08-24T09:00:00Z",
                "window_end": "2026-08-24T11:00:00Z",
            },
            headers=headers,
        )
        assert res.status_code == 403


async def test_leave_waitlist(client, patient_row, patient_login):
    async with client:
        headers, clinician_id = await _clinician(client)
        entry_id = (
            await client.post(
                "/api/scheduling/waitlist",
                json={
                    "clinician_id": clinician_id,
                    "window_start": "2026-08-24T09:00:00Z",
                    "window_end": "2026-08-24T11:00:00Z",
                },
                headers=patient_login,
            )
        ).json()["id"]

        res = await client.delete(f"/api/scheduling/waitlist/{entry_id}", headers=patient_login)
        assert res.status_code == 204
        assert (await client.get("/api/scheduling/waitlist", headers=patient_login)).json() == []


async def test_cancel_frees_slot_and_notifies_earliest_waiter(client, patient_row, patient_login, db_session):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        # Someone else books the slot the waiter wants.
        p2 = Patient(id="PWAIT2", name="Occupant", age=40, sex="M", medical_record_number="PT-PWAIT2")
        db_session.add(p2)
        await db_session.commit()
        booked = await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": p2.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )
        appt_id = booked.json()["id"]

        await client.post(
            "/api/scheduling/waitlist",
            json={
                "clinician_id": clinician_id,
                "window_start": "2026-08-24T09:00:00Z",
                "window_end": "2026-08-24T11:00:00Z",
            },
            headers=patient_login,
        )

        # No notification yet — the slot hasn't freed up.
        before = await client.get("/api/notifications", headers=patient_login)
        assert before.json() == []

        cancel = await client.delete(f"/api/scheduling/appointments/{appt_id}", headers=headers)
        assert cancel.status_code == 204

        after = await client.get("/api/notifications", headers=patient_login)
        assert len(after.json()) == 1
        assert after.json()[0]["type"] == "waitlist_match"

        # Removed from the waitlist after the match, not auto-booked.
        assert (await client.get("/api/scheduling/waitlist", headers=patient_login)).json() == []
        appts_after = await client.get("/api/scheduling/appointments", headers=patient_login)
        assert appts_after.json() == []


async def test_booking_notifies_the_patient(client, patient_row, patient_login):
    async with client:
        headers, clinician_id = await _clinician(client)
        await _set_up_availability(client, headers)

        await client.post(
            "/api/scheduling/appointments",
            json={"clinician_id": clinician_id, "patient_id": patient_row.id, "start_at": NEXT_MONDAY_ISO},
            headers=headers,
        )

        notifications = await client.get("/api/notifications", headers=patient_login)
        assert len(notifications.json()) == 1
        assert notifications.json()[0]["type"] == "appointment_booked"

        unread = await client.get("/api/notifications/unread-count", headers=patient_login)
        assert unread.json()["count"] == 1

        notif_id = notifications.json()[0]["id"]
        await client.post(f"/api/notifications/{notif_id}/read", headers=patient_login)
        unread_after = await client.get("/api/notifications/unread-count", headers=patient_login)
        assert unread_after.json()["count"] == 0
