"""Tests for `core.db.init_db` — table creation + idempotent demo seeding.

Note: `SEED_PATIENTS` holds module-level ORM instances shared across the
whole process, so both assertions run against a single engine within one
test — reusing those instances across two independently-disposed engines
corrupts SQLAlchemy's identity map.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core import db as db_module
from data.schemas import Patient


@pytest.mark.asyncio
async def test_init_db_creates_tables_seeds_and_is_idempotent(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)

    await db_module.init_db()

    async with session_factory() as session:
        patients = (await session.scalars(select(Patient))).all()
        assert len(patients) == len(db_module.SEED_PATIENTS)

    await db_module.init_db()  # second call must not duplicate seed rows

    async with session_factory() as session:
        patients = (await session.scalars(select(Patient))).all()
        assert len(patients) == len(db_module.SEED_PATIENTS)

    await engine.dispose()
