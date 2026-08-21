"""End-to-end: booking an appointment through the real API -> NEW_APPOINTMENT
event -> tick dispatch -> appointment_reminder workflow enrolled with both
steps, through the actual register_subscriptions() wiring."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.main import app
from api.workflows.engine import run_tick
from api.workflows.subscriptions import register_subscriptions
from core.db import get_session
from data.schemas import Patient, Workflow, WorkflowStep

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session):
    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


async def test_booking_through_real_api_enrolls_reminder_workflow(client, db_session):
    register_subscriptions()

    patient = Patient(id="PE2E2", name="Booking E2E Patient", age=29, sex="F", medical_record_number="PT-PE2E2")
    db_session.add(patient)
    await db_session.commit()

    clin_res = await client.post(
        "/api/auth/register",
        json={"email": "e2e-booking-clin@example.org", "name": "Dr. E2E", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {clin_res.json()['access_token']}"}
    clinician_id = clin_res.json()["user"]["id"]

    await client.post(
        "/api/scheduling/availability",
        json={"weekday": 0, "start_time": "09:00", "end_time": "11:00", "slot_minutes": 30},
        headers=headers,
    )
    book_res = await client.post(
        "/api/scheduling/appointments",
        json={"clinician_id": clinician_id, "patient_id": patient.id, "start_at": "2026-08-24T09:00:00Z"},
        headers=headers,
    )
    assert book_res.status_code == 201
    appt_id = book_res.json()["id"]

    summary = await run_tick(db_session, tick_id="booking-e2e-tick")
    assert summary.events_dispatched >= 1

    workflow = (await db_session.scalars(select(Workflow).where(Workflow.appointment_id == appt_id))).one()
    steps = (await db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))).all()
    assert {s.step_key for s in steps} == {"reminder_t24", "unconfirmed_check"}
