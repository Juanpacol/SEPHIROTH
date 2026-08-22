"""Operational memory (SPEC-015): allow-list enforcement + upsert
semantics, unit-level."""

import pytest
from sqlalchemy import select

from api.workflows.memory import InvalidMemoryKey, get_memory, set_memory
from data.schemas import AutomationMemory, Patient, User

pytestmark = pytest.mark.asyncio


async def test_set_and_get_roundtrip(db_session):
    db_session.add(Patient(id="P1", name="Memory Patient", age=40, sex="F", medical_record_number="PT-P1"))
    await db_session.commit()

    await set_memory(db_session, "patient", "P1", "quiet_hours", {"start": "21:00", "end": "07:00"})
    await db_session.commit()

    value = await get_memory(db_session, "patient", "P1", "quiet_hours")
    assert value == {"start": "21:00", "end": "07:00"}


async def test_get_missing_returns_default(db_session):
    value = await get_memory(db_session, "user", "U1", "reminder_lead_hours", default=24)
    assert value == 24


async def test_set_rejects_unknown_key(db_session):
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "patient", "P1", "risk_level", "high")


async def test_set_rejects_unknown_scope(db_session):
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "clinician", "U1", "reminder_lead_hours", 12)


async def test_set_rejects_malformed_value_for_known_key(db_session):
    """Security regression: only the *key* was validated before -- the
    value went into the JSON column verbatim. A clinical-shaped value
    (or any garbage) under an allowed key must now be rejected too."""
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "clinic", "default", "reminder_lead_hours", "not-an-int")
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "clinic", "default", "reminder_lead_hours", 9999)
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "clinic", "default", "quiet_hours", {"start": "9am"})
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "clinic", "default", "contact_preference", "sms")


async def test_set_rejects_nonexistent_patient_or_user(db_session):
    """Security regression: `scope_id` was previously unvalidated --
    a clinician could write unbounded rows under ids naming nothing."""
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "patient", "no-such-patient", "reminder_lead_hours", 12)
    with pytest.raises(InvalidMemoryKey):
        await set_memory(db_session, "user", "no-such-user", "reminder_lead_hours", 12)


async def test_set_accepts_clinic_scope_with_any_id(db_session):
    row = await set_memory(db_session, "clinic", "anything-at-all", "reminder_lead_hours", 12)
    await db_session.commit()
    assert row.scope_id == "anything-at-all"


async def test_set_upserts_not_duplicates(db_session):
    db_session.add(
        User(id="U2", email="memu2@example.org", name="Memory User", hashed_password="x", role="clinician")
    )
    await db_session.commit()

    await set_memory(db_session, "user", "U2", "reminder_lead_hours", 24)
    await db_session.commit()
    await set_memory(db_session, "user", "U2", "reminder_lead_hours", 12)
    await db_session.commit()

    rows = (
        await db_session.scalars(
            select(AutomationMemory).where(
                AutomationMemory.scope == "user", AutomationMemory.scope_id == "U2"
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].value == 12
