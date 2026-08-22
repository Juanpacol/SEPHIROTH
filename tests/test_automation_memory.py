"""Operational memory (SPEC-015): allow-list enforcement + upsert
semantics, unit-level."""

import pytest
from sqlalchemy import select

from api.workflows.memory import InvalidMemoryKey, get_memory, set_memory
from data.schemas import AutomationMemory

pytestmark = pytest.mark.asyncio


async def test_set_and_get_roundtrip(db_session):
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


async def test_set_upserts_not_duplicates(db_session):
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
