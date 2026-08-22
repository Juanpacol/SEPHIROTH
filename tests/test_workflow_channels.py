"""`InAppChannel` — the one `NotificationChannel` implementation
(SPEC-009 §F). A duplicate `dedupe_key` must be a no-op, not an error."""

from uuid import uuid4

import pytest

from api.workflows.channels import InAppChannel
from data.schemas import Patient, User

pytestmark = pytest.mark.asyncio


async def _user(session, patient_id):
    u = User(
        id=str(uuid4()),
        email=f"{uuid4().hex[:8]}@example.org",
        name="Notify Target",
        hashed_password="x",
        role="patient",
        patient_id=patient_id,
    )
    session.add(u)
    await session.commit()
    return u


async def test_send_creates_a_notification(db_session):
    patient = Patient(id="PCH1", name="Chan Patient", age=30, sex="F", medical_record_number="PT-PCH1")
    db_session.add(patient)
    await db_session.commit()
    user = await _user(db_session, patient.id)

    channel = InAppChannel()
    created = await channel.send(db_session, user.id, "workflow_reminder", "hello", dedupe_key="k1")

    assert created is True


async def test_send_is_idempotent_on_dedupe_key(db_session):
    patient = Patient(id="PCH2", name="Chan Patient 2", age=31, sex="M", medical_record_number="PT-PCH2")
    db_session.add(patient)
    await db_session.commit()
    user = await _user(db_session, patient.id)

    channel = InAppChannel()
    first = await channel.send(db_session, user.id, "workflow_reminder", "hello", dedupe_key="same-key")
    second = await channel.send(
        db_session, user.id, "workflow_reminder", "hello again", dedupe_key="same-key"
    )

    assert first is True
    assert second is False


async def test_send_without_dedupe_key_always_creates(db_session):
    patient = Patient(id="PCH3", name="Chan Patient 3", age=32, sex="F", medical_record_number="PT-PCH3")
    db_session.add(patient)
    await db_session.commit()
    user = await _user(db_session, patient.id)

    channel = InAppChannel()
    first = await channel.send(db_session, user.id, "workflow_reminder", "a")
    second = await channel.send(db_session, user.id, "workflow_reminder", "b")

    assert first is True
    assert second is True
